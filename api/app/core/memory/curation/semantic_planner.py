"""Use an LLM only to propose one schema-constrained memory curation operation.

The model never receives entity IDs and cannot set risk, confirmation policy, snapshots,
tokens, or Cypher. Those fields are derived by deterministic code after validation.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.llm.client import LLMClient
from app.core.memory.curation.models import CurationOperation, CurationPlan
from app.core.memory.json_utils import parse_json_object

SemanticOperationKind = Literal[
    "set_self_display_name",
    "add_self_alias",
    "remove_self_alias",
    "correct_entity",
    "merge_entities",
    "invalidate_fact",
]

_SYSTEM_PROMPT = """你是 Meme 的记忆整理意图解析器。你的唯一任务是把用户的明确修改请求转换成一个受控操作。

只允许以下操作：
- set_self_display_name：设置用户本人的展示名，value 是新名字。
- add_self_alias：增加用户本人的别名，value 是别名。
- remove_self_alias：移除用户本人的别名，value 是别名。
- correct_entity：把已有实体改名，target_name 是旧名，value 是新名。
- merge_entities：合并两个已有实体，target_name 是保留方，secondary_target_name 是被合并方。
- invalidate_fact：让某个实体及其关联事实不再参与后续召回，target_name 是实体名；保留来源和审计。

规则：
1. 只能返回 JSON，不要 Markdown、解释或 Cypher。
2. 一次只生成一个操作；包含多个互相依赖的修改、主体不清、目标不清时必须 rejected。
3. 查询、闲聊、添加新事实、批量清理、物理删除来源、修改关系内容等不属于本接口，必须 rejected。
4. “我不叫 X”但没有给出正确名字或明确要求移除别名时必须 rejected，不能猜测。
5. 不得输出实体 ID、用户 ID、风险、确认策略、签名或数据库语句。

返回格式：
{"status":"ready|rejected","message":"简短说明","operation":{"kind":"操作名","target_name":null,"secondary_target_name":null,"value":null,"reason":"解析依据"}}
rejected 时 operation 必须为 null。
"""

_TECHNICAL_ID_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:[0-9a-fA-F]{32}|"
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})(?![A-Za-z0-9])"
)


class SemanticOperationCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: SemanticOperationKind
    target_name: str | None = Field(default=None, max_length=80)
    secondary_target_name: str | None = Field(default=None, max_length=80)
    value: str | None = Field(default=None, max_length=80)
    reason: str | None = Field(default=None, max_length=300)


class SemanticPlanCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ready", "rejected"]
    message: str = Field(default="", max_length=300)
    operation: SemanticOperationCandidate | None = None


def _clean_value(value: str | None) -> str | None:
    cleaned = (value or "").strip().strip("\"'“”‘’「」『』")
    if not cleaned or len(cleaned) > 80 or any(ch in cleaned for ch in "\r\n\x00"):
        return None
    return cleaned


def _rejected(request: str, message: str) -> CurationPlan:
    return CurationPlan(
        request=request,
        status="rejected",
        message=message,
        planner_source="llm",
        executable=False,
    )


def _operation_from_candidate(
    request: str, candidate: SemanticOperationCandidate
) -> CurationPlan:
    kind = candidate.kind
    target = _clean_value(candidate.target_name)
    secondary = _clean_value(candidate.secondary_target_name)
    value = _clean_value(candidate.value)
    reason = (candidate.reason or "").strip()[:300] or None

    if kind == "set_self_display_name" and value:
        operation = CurationOperation(
            kind=kind,
            summary=f"将个人展示名设为「{value}」",
            risk="medium",
            requires_confirmation=True,
            patch={"name": value},
            reason=reason,
            target_status="will_create",
        )
    elif kind in {"add_self_alias", "remove_self_alias"} and value:
        adding = kind == "add_self_alias"
        operation = CurationOperation(
            kind=kind,
            summary=f"{'增加' if adding else '移除'}个人身份别名「{value}」",
            risk="low" if adding else "medium",
            requires_confirmation=not adding,
            patch={"alias": value},
            reason=reason,
            target_status="will_create",
        )
    elif kind == "correct_entity" and target and value and target.casefold() != value.casefold():
        operation = CurationOperation(
            kind=kind,
            summary=f"把实体「{target}」改名为「{value}」",
            risk="high",
            requires_confirmation=True,
            target_name=target,
            patch={"name": value},
            reason=reason,
        )
    elif kind == "merge_entities" and target and secondary and target.casefold() != secondary.casefold():
        operation = CurationOperation(
            kind=kind,
            summary=f"保留实体「{target}」，合并实体「{secondary}」",
            risk="high",
            requires_confirmation=True,
            target_name=target,
            secondary_target_name=secondary,
            reason=reason,
        )
    elif kind == "invalidate_fact" and target:
        operation = CurationOperation(
            kind=kind,
            summary=f"停止在后续召回中使用实体「{target}」及其关联事实",
            risk="high",
            requires_confirmation=True,
            target_name=target,
            reason=reason,
        )
    else:
        return _rejected(request, "模型返回的整理目标不完整或相互冲突，请换一种更明确的说法。")

    return CurationPlan(
        request=request,
        status="ready",
        message=f"已理解为：{operation.summary}。请检查预览后再执行。",
        planner_source="llm",
        operations=[operation],
        risk=operation.risk,
        requires_confirmation=operation.requires_confirmation,
    )


async def build_semantic_curation_plan(
    client: LLMClient, request: str
) -> CurationPlan:
    """Convert one natural-language request into a validated white-list plan."""
    if _TECHNICAL_ID_RE.search(request):
        return _rejected(
            request,
            "请使用实体名称描述整理目标，不要输入内部实体 ID。",
        )
    answer = await client.chat(
        [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": request},
        ],
        temperature=0.0,
        # 推理模型可能先消耗一部分输出预算生成 reasoning_content；预算过小会让
        # OpenAI 兼容接口最终返回空 content，导致本可执行的计划解析失败。
        max_tokens=1200,
    )
    data = parse_json_object(answer)
    if not data:
        return _rejected(request, "未能从模型响应中得到有效整理计划，请换一种明确说法。")
    try:
        candidate = SemanticPlanCandidate.model_validate(data)
    except ValidationError:
        return _rejected(request, "模型返回的整理计划不符合安全格式，请换一种明确说法。")
    if candidate.status == "rejected" or candidate.operation is None:
        return _rejected(
            request,
            candidate.message or "这条请求存在歧义，记忆管家没有执行任何修改。",
        )
    return _operation_from_candidate(request, candidate.operation)


__all__ = ["build_semantic_curation_plan"]

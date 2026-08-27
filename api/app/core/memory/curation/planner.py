"""把高置信度的中文记忆整理请求转换为安全计划。

这是第一阶段的规则层，不追求覆盖所有自然语言。无法确认主体、目标或意图时，
宁可拒绝生成动作，也不猜测用户想修改哪条记忆。
"""
from __future__ import annotations

import re

from app.core.memory.curation.models import CurationOperation, CurationPlan
from app.core.memory.extraction.identity import extract_identity_signals

_NAME = r"[A-Za-z\u4e00-\u9fff][A-Za-z0-9_\-·\u4e00-\u9fff]{0,31}"


def _clean_name(value: str) -> str:
    value = (value or "").strip().strip("\"'“”‘’「」『』")
    value = re.split(r"[，。！？；;、,\n]|(?:并且|然后|但是)", value, 1)[0]
    return value.strip()[:32]


def _rejected(request: str, message: str) -> CurationPlan:
    return CurationPlan(
        request=request,
        status="rejected",
        message=message,
        executable=False,
    )


def _add_self_alias_plan(request: str, alias: str) -> CurationPlan:
    """为确定性识别出的本人别名请求生成统一计划。"""
    return CurationPlan(
        request=request,
        status="ready",
        message=f"为个人身份增加别名「{alias}」，无需修改其他记忆。",
        risk="low",
        operations=[
            CurationOperation(
                kind="add_self_alias",
                summary=f"增加个人身份别名「{alias}」",
                risk="low",
                requires_confirmation=False,
                patch={"alias": alias},
                target_status="will_create",
            )
        ],
    )


def _self_name_operation(request: str) -> CurationPlan | None:
    # “把我的名字改成 X”不在身份抽取器的范围内，这里单独支持。
    match = re.fullmatch(
        rf"\s*把(?:我|本人)的(?:名字|姓名)改(?:成|为)\s*({_NAME})\s*[。.!！]?\s*",
        request,
        flags=re.IGNORECASE,
    )
    if match:
        name = _clean_name(match.group(1))
        return CurationPlan(
            request=request,
            status="ready",
            message=f"将个人展示名改为「{name}」，请确认后执行。",
            risk="medium",
            requires_confirmation=True,
            operations=[
                CurationOperation(
                    kind="set_self_display_name",
                    summary=f"将个人展示名改为「{name}」",
                    risk="medium",
                    requires_confirmation=True,
                    patch={"name": name},
                    target_status="will_create",
                )
            ],
        )

    signals = extract_identity_signals(request)
    if signals.invalid_names:
        return _rejected(request, "检测到否定身份表达，当前版本不会自动把它解释为改名或别名操作。")
    if signals.current_names and not signals.alias_names and len(signals.current_names) == 1:
        name = signals.current_names[0]
        return CurationPlan(
            request=request,
            status="ready",
            message=f"将个人展示名设为「{name}」，请确认后执行。",
            risk="medium",
            requires_confirmation=True,
            operations=[
                CurationOperation(
                    kind="set_self_display_name",
                    summary=f"将个人展示名设为「{name}」",
                    risk="medium",
                    requires_confirmation=True,
                    patch={"name": name},
                    target_status="will_create",
                )
            ],
        )
    if signals.alias_names and not signals.current_names and len(signals.alias_names) == 1:
        alias = signals.alias_names[0]
        return CurationPlan(
            request=request,
            status="ready",
            message=f"为个人身份增加别名「{alias}」，请确认后执行。",
            risk="low",
            requires_confirmation=False,
            operations=[
                CurationOperation(
                    kind="add_self_alias",
                    summary=f"增加个人身份别名「{alias}」",
                    risk="low",
                    requires_confirmation=False,
                    patch={"alias": alias},
                    target_status="will_create",
                )
            ],
        )
    return None


def build_curation_plan(request: str) -> CurationPlan:
    """生成只读整理计划；复杂、歧义或未支持表达直接拒绝。"""
    request = (request or "").strip()
    if not request:
        return _rejected(request, "整理请求不能为空。")

    self_plan = _self_name_operation(request)
    if self_plan is not None:
        return self_plan

    # “把小舟作为我的另一个称呼”表达的是新增别名，不应依赖模型自由解析。
    match = re.fullmatch(
        rf"\s*(?:请)?把\s*({_NAME})\s*(?:作为|设为|当作)\s*"
        rf"(?:我|本人)的(?:另一个|其他)?(?:称呼|别名)\s*[。.!！]?\s*",
        request,
        flags=re.IGNORECASE,
    )
    if match:
        return _add_self_alias_plan(request, _clean_name(match.group(1)))

    match = re.fullmatch(
        rf"\s*(?:给我|为我)?(?:增加|添加|新增)别名\s*({_NAME})\s*[。.!！]?\s*",
        request,
        flags=re.IGNORECASE,
    )
    if match:
        return _add_self_alias_plan(request, _clean_name(match.group(1)))

    match = re.fullmatch(
        rf"\s*(?:删除|移除)别名\s*({_NAME})\s*[。.!！]?\s*", request, flags=re.IGNORECASE
    )
    if match:
        alias = _clean_name(match.group(1))
        return CurationPlan(
            request=request,
            status="ready",
            message=f"移除个人身份别名「{alias}」，这是可逆性较弱的操作，请确认。",
            risk="medium",
            requires_confirmation=True,
            operations=[
                CurationOperation(
                    kind="remove_self_alias",
                    summary=f"移除个人身份别名「{alias}」",
                    risk="medium",
                    requires_confirmation=True,
                    patch={"alias": alias},
                    target_status="will_create",
                )
            ],
        )

    match = re.fullmatch(
        rf"\s*(?:合并|把)\s*({_NAME})\s*(?:和|与|、)\s*({_NAME})\s*(?:合并)?\s*[。.!！]?\s*",
        request,
        flags=re.IGNORECASE,
    )
    if match:
        first, second = map(_clean_name, match.groups())
        if first.casefold() == second.casefold():
            return _rejected(request, "合并目标是同一个名称，不生成无意义操作。")
        return CurationPlan(
            request=request,
            status="ready",
            message=f"合并实体「{first}」和「{second}」，需要确认后执行。",
            risk="high",
            requires_confirmation=True,
            operations=[
                CurationOperation(
                    kind="merge_entities",
                    summary=f"合并实体「{first}」和「{second}」",
                    risk="high",
                    requires_confirmation=True,
                    target_name=first,
                    secondary_target_name=second,
                )
            ],
        )

    match = re.fullmatch(
        rf"\s*把\s*({_NAME})\s*(?:的名称|的名字|名字|名称)\s*改(?:成|为)\s*({_NAME})\s*[。.!！]?\s*",
        request,
        flags=re.IGNORECASE,
    )
    if match:
        old_name, new_name = map(_clean_name, match.groups())
        return CurationPlan(
            request=request,
            status="ready",
            message=f"把实体「{old_name}」改名为「{new_name}」，需要确认后执行。",
            risk="high",
            requires_confirmation=True,
            operations=[
                CurationOperation(
                    kind="correct_entity",
                    summary=f"把实体「{old_name}」改名为「{new_name}」",
                    risk="high",
                    requires_confirmation=True,
                    target_name=old_name,
                    patch={"name": new_name},
                )
            ],
        )

    match = re.fullmatch(
        rf"\s*(?:删除|忘记|撤销)(?:关于|实体)?\s*({_NAME})(?:的记忆|这条记忆)?\s*[。.!！]?\s*",
        request,
        flags=re.IGNORECASE,
    )
    if match:
        target = _clean_name(match.group(1))
        return CurationPlan(
            request=request,
            status="ready",
            message=f"使与「{target}」相关的事实失效，需要确认后执行。",
            risk="high",
            requires_confirmation=True,
            operations=[
                CurationOperation(
                    kind="invalidate_fact",
                    summary=f"使与「{target}」相关的事实失效",
                    risk="high",
                    requires_confirmation=True,
                    target_name=target,
                )
            ],
        )

    return _rejected(
        request,
        "暂不支持这种整理表达。请明确说明：改个人名字、增加/删除别名、修改实体名称、合并两个实体，或忘记某个实体相关事实。",
    )


__all__ = ["build_curation_plan"]

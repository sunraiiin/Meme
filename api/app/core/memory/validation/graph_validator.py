"""记忆图谱质量规则。

规则函数只接受查询结果并返回确定性报告，不包含 Neo4j 写操作，因此可以用于
迁移前 dry-run、CI 回归和后续 Memory Curator Agent 的修复建议。
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


class GraphFinding(BaseModel):
    rule_id: str
    severity: Literal["info", "warning", "error"]
    message: str
    recommendation: str
    entity_ids: list[str] = Field(default_factory=list)
    relation_ids: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class GraphValidationReport(BaseModel):
    user_id: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    entity_count: int
    relation_count: int
    findings: list[GraphFinding] = Field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(item.severity == "error" for item in self.findings)

    @property
    def warning_count(self) -> int:
        return sum(item.severity == "warning" for item in self.findings)

    def as_dict(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        data["summary"] = {
            "errors": self.error_count,
            "warnings": self.warning_count,
            "infos": len(self.findings) - self.error_count - self.warning_count,
        }
        return data


def _active(entity: dict[str, Any]) -> bool:
    return bool(entity.get("is_active", True)) and not bool(entity.get("is_invalidated", False))


def validate_graph(
    *, user_id: str, entities: list[dict[str, Any]], relations: list[dict[str, Any]]
) -> GraphValidationReport:
    """对一个用户图谱运行只读质量规则。"""
    active = [entity for entity in entities if _active(entity)]
    findings: list[GraphFinding] = []

    self_candidates = [
        entity
        for entity in active
        if entity.get("identity_key")
        or entity.get("is_self")
        or (entity.get("name") == "用户" and entity.get("type") == "生命体")
    ]
    if not self_candidates:
        findings.append(
            GraphFinding(
                rule_id="SELF_MISSING",
                severity="warning",
                message="当前图谱没有明确的 canonical self 实体。",
                recommendation="通过身份声明或记忆整理计划建立稳定 self identity_key。",
            )
        )
    elif len(self_candidates) > 1:
        findings.append(
            GraphFinding(
                rule_id="SELF_MULTIPLE_ACTIVE",
                severity="error",
                message=f"发现 {len(self_candidates)} 个可能代表用户本人的活动实体。",
                recommendation="先预览身份合并，再由用户确认后收敛到一个 canonical self。",
                entity_ids=sorted(str(entity.get("id")) for entity in self_candidates),
                details={
                    "names": sorted(str(entity.get("name") or "") for entity in self_candidates)
                },
            )
        )
    if len(self_candidates) == 1 and not self_candidates[0].get("identity_key"):
        findings.append(
            GraphFinding(
                rule_id="SELF_IDENTITY_KEY_MISSING",
                severity="warning",
                message="唯一 self 候选缺少稳定 identity_key。",
                recommendation="迁移前先生成 self:<user_id>，不要继续用展示名作为身份键。",
                entity_ids=[str(self_candidates[0].get("id"))],
            )
        )

    alias_entities = [entity for entity in active if entity.get("type") == "称呼别名"]
    if alias_entities:
        findings.append(
            GraphFinding(
                rule_id="ALIAS_ENTITY_PRESENT",
                severity="warning",
                message=f"发现 {len(alias_entities)} 个把称呼别名建成独立实体的节点。",
                recommendation="迁移到 canonical self.aliases 属性，并保留原节点作为迁移审计依据。",
                entity_ids=sorted(str(entity.get("id")) for entity in alias_entities),
                details={"names": sorted(str(entity.get("name") or "") for entity in alias_entities)},
            )
        )

    duplicate_groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for entity in active:
        key = (str(entity.get("name") or "").casefold().strip(), str(entity.get("type") or ""))
        if key[0]:
            duplicate_groups[key].append(str(entity.get("id")))
    for (name, type_), ids in sorted(duplicate_groups.items()):
        if len(ids) > 1:
            findings.append(
                GraphFinding(
                    rule_id="DUPLICATE_ACTIVE_ENTITY",
                    severity="warning",
                    message=f"发现同名同类型活动实体：{name}（{type_}）。",
                    recommendation="生成合并预览，确认保留节点后再执行逻辑合并。",
                    entity_ids=sorted(ids),
                    details={"name": name, "type": type_, "count": len(ids)},
                )
            )

    inactive = [entity for entity in entities if not _active(entity)]
    if inactive:
        findings.append(
            GraphFinding(
                rule_id="INACTIVE_ENTITY_PRESENT",
                severity="info",
                message=f"图谱中保留了 {len(inactive)} 个逻辑失效或已合并实体。",
                recommendation="保留用于审计；检索和新写入应过滤 inactive 节点。",
                entity_ids=sorted(str(entity.get("id")) for entity in inactive),
            )
        )

    for relation in relations:
        source_text = str(relation.get("source_text") or "").strip()
        has_statement = bool(relation.get("statement_exists"))
        if source_text or has_statement:
            continue
        findings.append(
            GraphFinding(
                rule_id="RELATION_EVIDENCE_MISSING",
                severity="warning",
                message="关系缺少原始陈述或可追溯 Statement。",
                recommendation="下次萃取写入 source_text，并为历史关系生成证据补全任务。",
                relation_ids=[str(relation.get("id"))],
                entity_ids=sorted(
                    item
                    for item in (str(relation.get("source_id")), str(relation.get("target_id")))
                    if item and item != "None"
                ),
                details={"statement_id": relation.get("statement_id")},
            )
        )

    return GraphValidationReport(
        user_id=user_id,
        entity_count=len(entities),
        relation_count=len(relations),
        findings=findings,
    )


__all__ = ["GraphFinding", "GraphValidationReport", "validate_graph"]

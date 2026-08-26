"""Memory Curator Agent 的稳定操作契约。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


OperationKind = Literal[
    "set_self_display_name",
    "add_self_alias",
    "remove_self_alias",
    "correct_entity",
    "merge_entities",
    "invalidate_fact",
    "forget_source",
]
RiskLevel = Literal["low", "medium", "high"]
PlanStatus = Literal["ready", "rejected"]
PlannerSource = Literal["rules", "llm"]


class CurationOperation(BaseModel):
    """单个经过白名单约束的整理动作；它不是 Cypher，也不能直接执行。"""

    operation_id: str = Field(default_factory=lambda: uuid4().hex)
    kind: OperationKind
    summary: str
    risk: RiskLevel
    requires_confirmation: bool
    target_name: str | None = None
    target_id: str | None = None
    target_snapshot: dict[str, Any] | None = None
    secondary_target_name: str | None = None
    secondary_target_id: str | None = None
    secondary_target_snapshot: dict[str, Any] | None = None
    patch: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None
    target_status: Literal["not_needed", "resolved", "will_create", "not_found"] = (
        "not_needed"
    )


class CurationPlan(BaseModel):
    """一次自然语言请求的只读预览结果。"""

    plan_id: str = Field(default_factory=lambda: uuid4().hex)
    request: str
    status: PlanStatus
    message: str
    planner_source: PlannerSource = "rules"
    operations: list[CurationOperation] = Field(default_factory=list)
    risk: RiskLevel = "low"
    requires_confirmation: bool = False
    executable: bool = True
    blocking_reasons: list[str] = Field(default_factory=list)
    side_effects: Literal["none"] = "none"
    expires_at: datetime | None = None
    confirmation_token: str | None = None


__all__ = [
    "CurationOperation",
    "CurationPlan",
    "OperationKind",
    "PlannerSource",
    "RiskLevel",
]

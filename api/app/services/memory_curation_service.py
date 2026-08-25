"""Memory Curator Agent 的计划服务。

服务层只读取 Neo4j 目标快照并丰富计划，不执行任何修改；后续执行器必须接收
这份白名单操作，而不能把自然语言直接交给 Cypher。
"""
from __future__ import annotations

import uuid
from typing import Any

from app.core.memory.curation.planner import build_curation_plan
from app.core.memory.extraction.identity import self_identity_key
from app.repositories.neo4j.memory_graph_repository import MemoryGraphRepository


def _snapshot(entity: dict[str, Any] | None) -> dict[str, Any] | None:
    if not entity:
        return None
    keys = (
        "id",
        "name",
        "type",
        "description",
        "aliases",
        "identity_key",
        "is_self",
        "confidence",
        "importance",
    )
    return {key: entity.get(key) for key in keys if key in entity}


class MemoryCurationService:
    """生成安全的记忆整理预览。"""

    def __init__(self, repo: MemoryGraphRepository | None = None):
        self.repo = repo or MemoryGraphRepository()

    async def plan(self, user_id: uuid.UUID, request: str) -> dict[str, Any]:
        plan = build_curation_plan(request)
        if plan.status == "rejected" or not plan.operations:
            return plan.model_dump(mode="json")

        uid = str(user_id)
        self_entity = None
        self_key = self_identity_key(uid)

        async def get_self() -> dict[str, Any] | None:
            nonlocal self_entity
            if self_entity is None:
                self_entity = await self.repo.get_self_entity(uid, self_key)
            return self_entity

        for operation in plan.operations:
            if operation.kind in {
                "set_self_display_name",
                "add_self_alias",
                "remove_self_alias",
            }:
                entity = await get_self()
                if entity:
                    operation.target_id = entity.get("id")
                    operation.target_snapshot = _snapshot(entity)
                    operation.target_status = "resolved"
                elif operation.kind == "remove_self_alias":
                    operation.target_status = "not_found"
                    plan.blocking_reasons.append("当前还没有可移除别名的 canonical self 实体。")
                else:
                    # 首次建立 self 身份时，后续执行器可以安全创建固定 identity_key。
                    operation.target_status = "will_create"
                continue

            target = await self.repo.get_entity_by_name(uid, operation.target_name or "")
            if target:
                operation.target_id = target.get("id")
                operation.target_snapshot = _snapshot(target)
                operation.target_status = "resolved"
            else:
                operation.target_status = "not_found"
                plan.blocking_reasons.append(
                    f"未找到目标实体「{operation.target_name or ''}」。"
                )

            if operation.kind == "merge_entities":
                secondary = await self.repo.get_entity_by_name(
                    uid, operation.secondary_target_name or ""
                )
                if secondary:
                    operation.secondary_target_id = secondary.get("id")
                    operation.secondary_target_snapshot = _snapshot(secondary)
                else:
                    operation.target_status = "not_found"
                    plan.blocking_reasons.append(
                        f"未找到第二个目标实体「{operation.secondary_target_name or ''}」。"
                    )

        if plan.blocking_reasons:
            plan.executable = False
            plan.message = "计划已生成，但目标不完整，暂不能进入执行阶段。"

        return plan.model_dump(mode="json")


__all__ = ["MemoryCurationService"]

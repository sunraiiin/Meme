"""canonical self 身份迁移：只读预览与显式确认后的执行。"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from typing import Any

from app.core.exceptions import BizError
from app.core.memory.extraction.identity import SELF_SURFACE_NAMES, self_identity_key
from app.core.memory.validation.identity_migration import build_identity_migration_preview
from app.repositories.memory_curation_repository import MemoryCurationRepository
from app.repositories.neo4j.memory_graph_repository import MemoryGraphRepository


def _entity_snapshot(entity: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "id", "name", "type", "description", "aliases", "identity_key", "is_self",
        "is_active", "is_invalidated", "merged_into",
    )
    return {key: entity.get(key) for key in keys}


def _relation_count(relations: list[dict[str, Any]], entity_id: str) -> int:
    return sum(
        1 for relation in relations
        if entity_id in {str(relation.get("source_id")), str(relation.get("target_id"))}
    )


def _operation_id(
    user_id: str, canonical_id: str, alias_ids: list[str], display_name: str
) -> str:
    payload = "|".join([user_id, canonical_id, display_name.strip(), *sorted(alias_ids)])
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:40]
    return f"identity-migration-{digest}"


def _audit_dict(record: Any) -> dict[str, Any]:
    def serializable(value: Any) -> Any:
        if isinstance(value, (datetime, uuid.UUID)):
            return value.isoformat() if isinstance(value, datetime) else str(value)
        if isinstance(value, dict):
            return {str(k): serializable(v) for k, v in value.items()}
        if isinstance(value, list):
            return [serializable(item) for item in value]
        return value

    return serializable({
        "id": record.id, "user_id": record.user_id, "plan_id": record.plan_id,
        "operation_id": record.operation_id, "request": record.request,
        "operation_kind": record.operation_kind, "risk": record.risk,
        "status": record.status, "before": record.before, "after": record.after,
        "error": record.error, "confirmed_at": record.confirmed_at,
        "executed_at": record.executed_at, "created_at": record.created_at,
    })


class MemoryIdentityMigrationService:
    def __init__(
        self,
        repo: MemoryGraphRepository | None = None,
        session: object | None = None,
    ):
        self.repo = repo or MemoryGraphRepository()
        self.session = session

    async def preview(self, user_id: uuid.UUID) -> dict[str, Any]:
        uid = str(user_id)
        entities = await self.repo.validator_entities(uid)
        relations = await self.repo.validator_relations(uid)
        return build_identity_migration_preview(
            user_id=uid, entities=entities, relations=relations
        ).as_dict()

    async def execute(
        self,
        user_id: uuid.UUID,
        *,
        canonical_entity_id: str,
        alias_entity_ids: list[str],
        display_name: str,
        confirmed: bool,
    ) -> dict[str, Any]:
        """执行显式目标的身份迁移；不会根据名称自动选择实体。"""
        if not confirmed:
            raise BizError("身份迁移需要明确确认", code=3100, status_code=409)
        if not display_name.strip():
            raise BizError("canonical self 展示名不能为空", code=3101, status_code=400)

        uid = str(user_id)
        alias_ids = sorted({item for item in alias_entity_ids if item and item != canonical_entity_id})
        entities = await self.repo.validator_entities(uid)
        relations = await self.repo.validator_relations(uid)
        active = {
            str(entity.get("id")): entity for entity in entities
            if bool(entity.get("is_active", True))
            and not bool(entity.get("is_invalidated", False))
        }
        canonical = active.get(canonical_entity_id)
        if canonical is None:
            raise BizError("canonical self 目标不存在或已失效，请重新预览", code=3102, status_code=409)
        if canonical.get("type") != "生命体" and not canonical.get("is_self"):
            raise BizError("canonical self 必须是生命体或已有 self 实体", code=3103, status_code=409)

        existing_self_ids = {
            entity_id for entity_id, entity in active.items()
            if entity.get("identity_key") == self_identity_key(uid)
            or bool(entity.get("is_self", False))
        }
        if existing_self_ids - {canonical_entity_id}:
            raise BizError("存在另一个 active canonical self，请先重新预览", code=3104, status_code=409)

        aliases: list[str] = []
        for value in [*(canonical.get("aliases") or []), *SELF_SURFACE_NAMES]:
            if value and value.casefold() != display_name.casefold() and value not in aliases:
                aliases.append(value)
        for alias_id in alias_ids:
            alias = active.get(alias_id)
            if alias is None or alias.get("type") != "称呼别名":
                raise BizError(
                    f"别名目标 {alias_id} 不存在、已失效或不是称呼别名",
                    code=3105, status_code=409,
                )
            for value in [alias.get("name"), *(alias.get("aliases") or [])]:
                if value and value.casefold() != display_name.casefold() and value not in aliases:
                    aliases.append(value)

        before = {
            "canonical": _entity_snapshot(canonical),
            "aliases": [_entity_snapshot(active[alias_id]) for alias_id in alias_ids],
            "relation_counts": {
                entity_id: _relation_count(relations, entity_id)
                for entity_id in [canonical_entity_id, *alias_ids]
            },
        }
        operation_id = _operation_id(uid, canonical_entity_id, alias_ids, display_name)
        if self.session is None:
            raise BizError("身份迁移执行缺少数据库会话", code=3106, status_code=500)

        audit_repo = MemoryCurationRepository(self.session)
        existing = await audit_repo.get_for_user(user_id, operation_id)
        if existing and existing.status in {"executed", "undone"}:
            return {"status": existing.status, "audit": _audit_dict(existing)}
        if existing and existing.status == "confirmed":
            raise BizError("该身份迁移正在执行或已被占用", code=3107, status_code=409)

        record = await audit_repo.create_confirmed(
            user_id=user_id,
            plan_id=operation_id,
            operation_id=operation_id,
            request=(
                f"将实体 {canonical_entity_id} 设为本人，展示名为「{display_name}」，"
                f"并合并别名实体 {', '.join(alias_ids) or '无'}"
            ),
            operation_kind="migrate_canonical_self",
            risk="high",
            requires_confirmation=True,
            before=before,
        )
        try:
            result = await self.repo.migrate_canonical_self(
                user_id=uid,
                canonical_entity_id=canonical_entity_id,
                alias_entity_ids=alias_ids,
                identity_key=self_identity_key(uid),
                display_name=display_name.strip(),
                aliases=sorted(aliases),
            )
            if result is None:
                raise BizError("迁移目标在执行前发生变化，请重新预览", code=3108, status_code=409)

            after_entities = await self.repo.validator_entities(uid)
            after_relations = await self.repo.validator_relations(uid)
            after = {
                "migration": result,
                "canonical": next(
                    (_entity_snapshot(item) for item in after_entities if item.get("id") == canonical_entity_id),
                    None,
                ),
                "aliases": [
                    _entity_snapshot(item) for item in after_entities
                    if item.get("id") in alias_ids
                ],
                "relation_count": len(after_relations),
            }
            await audit_repo.mark_executed(record, after)
            return {"status": "executed", "audit": _audit_dict(record), "after": after}
        except Exception as exc:  # noqa: BLE001
            await audit_repo.mark_failed(record, str(exc))
            if isinstance(exc, BizError):
                raise
            raise BizError("身份迁移执行失败", code=3109, status_code=500) from exc


__all__ = ["MemoryIdentityMigrationService"]

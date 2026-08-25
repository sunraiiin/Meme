"""Memory Curator Agent：计划、确认执行、审计与安全撤销。"""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import settings
from app.core.exceptions import BizError
from app.core.memory.curation.models import CurationOperation, CurationPlan
from app.core.memory.curation.planner import build_curation_plan
from app.core.memory.extraction.identity import self_identity_key
from app.repositories.memory_curation_repository import MemoryCurationRepository
from app.repositories.neo4j.memory_graph_repository import MemoryGraphRepository

_PLAN_TTL = timedelta(minutes=10)


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
        "is_active",
        "is_invalidated",
        "merged_into",
        "confidence",
        "importance",
        "memory_layer",
    )
    return {key: entity.get(key) for key in keys if key in entity}


def _serializable(value: Any) -> Any:
    if isinstance(value, (datetime, uuid.UUID)):
        return value.isoformat() if isinstance(value, datetime) else str(value)
    if isinstance(value, dict):
        return {str(k): _serializable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serializable(v) for v in value]
    return value


def _same_snapshot(planned: dict[str, Any] | None, current: dict[str, Any] | None) -> bool:
    """只比较计划中存在的稳定字段，避免 Neo4j 默认属性造成误报。"""
    if planned is None or current is None:
        return planned == current
    comparable = (
        "id",
        "name",
        "type",
        "description",
        "aliases",
        "identity_key",
        "is_self",
        "is_active",
        "is_invalidated",
        "merged_into",
    )
    return all(
        key not in planned or planned.get(key) == current.get(key)
        for key in comparable
    )


def _canonical_plan(plan: CurationPlan) -> str:
    payload = plan.model_dump(mode="json", exclude={"confirmation_token"})
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _confirmation_token(plan: CurationPlan) -> str:
    digest = hmac.new(
        settings.jwt_secret.encode("utf-8"),
        _canonical_plan(plan).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest


def _audit_dict(record: Any) -> dict[str, Any]:
    return _serializable({
        "id": record.id,
        "user_id": record.user_id,
        "plan_id": record.plan_id,
        "operation_id": record.operation_id,
        "request": record.request,
        "operation_kind": record.operation_kind,
        "risk": record.risk,
        "requires_confirmation": record.requires_confirmation,
        "status": record.status,
        "before": record.before,
        "after": record.after,
        "error": record.error,
        "confirmed_at": record.confirmed_at,
        "executed_at": record.executed_at,
        "undone_at": record.undone_at,
        "created_at": record.created_at,
    })


class MemoryCurationService:
    """把自然语言整理请求限制在可审阅的白名单操作内。"""

    def __init__(
        self,
        repo: MemoryGraphRepository | None = None,
        session: object | None = None,
    ):
        self.repo = repo or MemoryGraphRepository()
        self.session = session

    async def plan(self, user_id: uuid.UUID, request: str) -> dict[str, Any]:
        """读取目标快照并签发短期确认令牌；此方法本身不写数据。"""
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
        plan.expires_at = datetime.now(timezone.utc) + _PLAN_TTL
        plan.confirmation_token = _confirmation_token(plan)
        return plan.model_dump(mode="json")

    def _require_session(self) -> object:
        if self.session is None:
            raise BizError("记忆整理执行缺少数据库会话", code=3080, status_code=500)
        return self.session

    async def execute(
        self,
        user_id: uuid.UUID,
        plan_payload: dict[str, Any],
        confirmation_token: str,
        confirmed: bool,
    ) -> dict[str, Any]:
        """验证签名计划并执行白名单操作。"""
        session = self._require_session()
        try:
            plan = CurationPlan.model_validate(plan_payload)
        except Exception as exc:  # noqa: BLE001
            raise BizError("整理计划格式无效，请重新预览", code=3081, status_code=400) from exc

        if not hmac.compare_digest(_confirmation_token(plan), confirmation_token):
            raise BizError("整理计划确认令牌无效，请重新预览", code=3082, status_code=409)
        if plan.expires_at is None or plan.expires_at <= datetime.now(timezone.utc):
            raise BizError("整理计划已过期，请重新预览", code=3083, status_code=409)
        if plan.status != "ready" or not plan.executable:
            raise BizError("整理计划未满足执行条件", code=3084, status_code=409)
        if plan.requires_confirmation and not confirmed:
            raise BizError("此整理计划需要明确确认后才能执行", code=3085, status_code=409)

        audit_repo = MemoryCurationRepository(session)
        results: list[dict[str, Any]] = []
        for operation in plan.operations:
            existing = await audit_repo.get_for_user(user_id, operation.operation_id)
            if existing and existing.status in {"executed", "undone"}:
                results.append(_audit_dict(existing))
                continue
            if existing and existing.status == "confirmed":
                raise BizError("该整理操作正在执行或已被占用", code=3086, status_code=409)

            before_target = None
            before_secondary = None
            if operation.target_status == "resolved":
                before_target = _snapshot(
                    await self.repo.entity_snapshot(str(user_id), operation.target_id or "")
                )
                if not _same_snapshot(operation.target_snapshot, before_target):
                    raise BizError("目标记忆在预览后发生变化，请重新生成计划", code=3087, status_code=409)
            if operation.kind == "merge_entities":
                before_secondary = _snapshot(
                    await self.repo.entity_snapshot(
                        str(user_id), operation.secondary_target_id or ""
                    )
                )
                if not _same_snapshot(operation.secondary_target_snapshot, before_secondary):
                    raise BizError("合并目标在预览后发生变化，请重新生成计划", code=3088, status_code=409)

            before = {"target": before_target, "secondary": before_secondary}
            record = await audit_repo.create_confirmed(
                user_id=user_id,
                plan_id=plan.plan_id,
                operation_id=operation.operation_id,
                request=plan.request,
                operation_kind=operation.kind,
                risk=operation.risk,
                requires_confirmation=operation.requires_confirmation,
                before=_serializable(before),
            )
            try:
                after = await self._apply_operation(user_id, operation, before_target)
                await audit_repo.mark_executed(record, _serializable(after))
            except Exception as exc:  # noqa: BLE001
                await audit_repo.mark_failed(record, str(exc))
                if isinstance(exc, BizError):
                    raise
                raise BizError("记忆整理执行失败，未确认后续操作", code=3089, status_code=500) from exc
            results.append(_audit_dict(record))
        return {"plan_id": plan.plan_id, "status": "executed", "operations": results}

    async def _apply_operation(
        self,
        user_id: uuid.UUID,
        operation: CurationOperation,
        before_target: dict[str, Any] | None,
    ) -> dict[str, Any]:
        uid = str(user_id)
        if operation.kind == "set_self_display_name":
            name = operation.patch["name"]
            if before_target:
                aliases = list(before_target.get("aliases") or [])
                old_name = before_target.get("name")
                if old_name and old_name != name and old_name not in aliases:
                    aliases.append(old_name)
                await self.repo.correct_entity(
                    uid, before_target["id"], name=name, aliases=aliases
                )
                return _snapshot(await self.repo.entity_snapshot(uid, before_target["id"])) or {}
            return _snapshot(
                await self.repo.ensure_self_entity(uid, self_identity_key(uid), name, ["用户"])
            ) or {}

        if operation.kind in {"add_self_alias", "remove_self_alias"}:
            alias = operation.patch["alias"]
            if before_target:
                aliases = list(before_target.get("aliases") or [])
                if operation.kind == "add_self_alias" and alias not in aliases:
                    aliases.append(alias)
                if operation.kind == "remove_self_alias":
                    aliases = [item for item in aliases if item != alias]
                await self.repo.correct_entity(uid, before_target["id"], aliases=aliases)
                return _snapshot(await self.repo.entity_snapshot(uid, before_target["id"])) or {}
            if operation.kind == "add_self_alias":
                return _snapshot(
                    await self.repo.ensure_self_entity(
                        uid, self_identity_key(uid), "用户", [alias]
                    )
                ) or {}
            raise BizError("当前没有可移除的个人别名", code=3090, status_code=409)

        if operation.kind == "correct_entity":
            if not before_target:
                raise BizError("修正目标不存在", code=3091, status_code=404)
            await self.repo.correct_entity(
                uid, before_target["id"], name=operation.patch.get("name")
            )
            return _snapshot(await self.repo.entity_snapshot(uid, before_target["id"])) or {}

        if operation.kind == "merge_entities":
            if not operation.target_id or not operation.secondary_target_id:
                raise BizError("合并目标不完整", code=3092, status_code=409)
            ok = await self.repo.merge_entities(
                uid, operation.target_id, operation.secondary_target_id
            )
            if not ok:
                raise BizError("合并目标不存在或已变化", code=3093, status_code=409)
            return {
                "keeper": _snapshot(await self.repo.entity_snapshot(uid, operation.target_id)),
                "duplicate": _snapshot(
                    await self.repo.entity_snapshot(uid, operation.secondary_target_id)
                ),
            }

        if operation.kind == "invalidate_fact":
            if not before_target:
                raise BizError("失效目标不存在", code=3094, status_code=404)
            await self.repo.correct_entity(
                uid,
                before_target["id"],
                is_active=False,
                is_invalidated=True,
            )
            return _snapshot(await self.repo.entity_snapshot(uid, before_target["id"])) or {}

        raise BizError("此操作类型尚未开放执行", code=3095, status_code=400)

    async def undo(self, user_id: uuid.UUID, operation_id: str) -> dict[str, Any]:
        session = self._require_session()
        audit_repo = MemoryCurationRepository(session)
        record = await audit_repo.get_for_user(user_id, operation_id)
        if record is None:
            raise BizError("整理操作不存在", code=3096, status_code=404)
        if record.status == "undone":
            return _audit_dict(record)
        if record.status != "executed":
            raise BizError("只有已执行的整理操作可以撤销", code=3097, status_code=409)
        if record.operation_kind == "merge_entities":
            raise BizError("合并操作暂不支持自动撤销，请通过审计记录人工处理", code=3098, status_code=409)

        before = (record.before or {}).get("target") or {}
        after = record.after or {}
        target_id = before.get("id") or after.get("id")
        if not target_id:
            raise BizError("缺少撤销所需的原始实体快照", code=3099, status_code=409)
        if not before.get("name") and record.operation_kind in {
            "set_self_display_name",
            "add_self_alias",
        }:
            await self.repo.correct_entity(
                str(user_id), target_id, is_active=False, is_invalidated=True
            )
        else:
            await self.repo.correct_entity(
                str(user_id),
                target_id,
                name=before.get("name"),
                type_=before.get("type"),
                description=before.get("description"),
                aliases=before.get("aliases"),
                is_active=before.get("is_active", True),
                is_invalidated=before.get("is_invalidated", False),
                merged_into=before.get("merged_into"),
                clear_merged=True,
            )
        await audit_repo.mark_undone(record)
        return _audit_dict(record)

    async def audit(self, user_id: uuid.UUID, limit: int = 50) -> list[dict[str, Any]]:
        session = self._require_session()
        records = await MemoryCurationRepository(session).list_recent(user_id, limit)
        return [_audit_dict(record) for record in records]


__all__ = ["MemoryCurationService"]

"""Memory Curator Agent 执行审计仓储。"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory_curation_model import MemoryCurationOperation


class MemoryCurationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_confirmed(
        self,
        *,
        user_id: uuid.UUID,
        plan_id: str,
        operation_id: str,
        request: str,
        operation_kind: str,
        risk: str,
        requires_confirmation: bool,
        before: dict,
    ) -> MemoryCurationOperation:
        record = MemoryCurationOperation(
            user_id=user_id,
            plan_id=plan_id,
            operation_id=operation_id,
            request=request,
            operation_kind=operation_kind,
            risk=risk,
            requires_confirmation=requires_confirmation,
            status="confirmed",
            before=before or {},
        )
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def get_for_user(
        self, user_id: uuid.UUID, operation_id: str
    ) -> MemoryCurationOperation | None:
        result = await self.session.execute(
            select(MemoryCurationOperation).where(
                MemoryCurationOperation.user_id == user_id,
                MemoryCurationOperation.operation_id == operation_id,
            )
        )
        return result.scalar_one_or_none()

    async def mark_executed(
        self, record: MemoryCurationOperation, after: dict
    ) -> MemoryCurationOperation:
        record.status = "executed"
        record.after = after or {}
        record.executed_at = datetime.now(timezone.utc)
        record.error = None
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def mark_failed(
        self, record: MemoryCurationOperation, error: str
    ) -> MemoryCurationOperation:
        record.status = "failed"
        record.error = error[:2000]
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def mark_undone(
        self, record: MemoryCurationOperation
    ) -> MemoryCurationOperation:
        record.status = "undone"
        record.undone_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def list_recent(
        self, user_id: uuid.UUID, limit: int = 50
    ) -> list[MemoryCurationOperation]:
        result = await self.session.execute(
            select(MemoryCurationOperation)
            .where(MemoryCurationOperation.user_id == user_id)
            .order_by(desc(MemoryCurationOperation.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())


__all__ = ["MemoryCurationRepository"]

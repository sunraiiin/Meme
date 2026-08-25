"""身份迁移预览服务（只读）。"""
import uuid
from typing import Any

from app.core.memory.validation.identity_migration import (
    build_identity_migration_preview,
)
from app.repositories.neo4j.memory_graph_repository import MemoryGraphRepository


class MemoryIdentityMigrationService:
    def __init__(self, repo: MemoryGraphRepository | None = None):
        self.repo = repo or MemoryGraphRepository()

    async def preview(self, user_id: uuid.UUID) -> dict[str, Any]:
        uid = str(user_id)
        entities = await self.repo.validator_entities(uid)
        relations = await self.repo.validator_relations(uid)
        return build_identity_migration_preview(
            user_id=uid, entities=entities, relations=relations
        ).as_dict()


__all__ = ["MemoryIdentityMigrationService"]

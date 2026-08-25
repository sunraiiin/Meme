"""记忆图谱 dry-run 校验服务。"""
import uuid
from typing import Any

from app.core.memory.validation.graph_validator import validate_graph
from app.repositories.neo4j.memory_graph_repository import MemoryGraphRepository


class MemoryGraphValidationService:
    def __init__(self, repo: MemoryGraphRepository | None = None):
        self.repo = repo or MemoryGraphRepository()

    async def validate(self, user_id: uuid.UUID) -> dict[str, Any]:
        uid = str(user_id)
        entities = await self.repo.validator_entities(uid)
        relations = await self.repo.validator_relations(uid)
        return validate_graph(
            user_id=uid, entities=entities, relations=relations
        ).as_dict()


__all__ = ["MemoryGraphValidationService"]

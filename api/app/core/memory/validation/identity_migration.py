"""canonical self 身份迁移的只读预览。"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class IdentityMigrationCandidate(BaseModel):
    entity_id: str
    name: str
    type: str
    role: Literal["existing_self", "life_entity", "alias_entity"]
    relation_count: int = 0


class IdentityMigrationPreview(BaseModel):
    user_id: str
    status: Literal["ready_for_confirmation", "needs_user_confirmation", "no_candidate"]
    identity_key: str
    recommended_display_name: str | None = None
    candidate_self_entities: list[IdentityMigrationCandidate] = Field(default_factory=list)
    alias_candidates: list[IdentityMigrationCandidate] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    side_effects: Literal["none"] = "none"

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def build_identity_migration_preview(
    *, user_id: str, entities: list[dict[str, Any]], relations: list[dict[str, Any]]
) -> IdentityMigrationPreview:
    active = [
        entity
        for entity in entities
        if bool(entity.get("is_active", True)) and not bool(entity.get("is_invalidated", False))
    ]
    relation_counts: dict[str, int] = {}
    for relation in relations:
        for key in ("source_id", "target_id"):
            entity_id = relation.get(key)
            if entity_id:
                relation_counts[str(entity_id)] = relation_counts.get(str(entity_id), 0) + 1

    self_entities: list[IdentityMigrationCandidate] = []
    alias_entities: list[IdentityMigrationCandidate] = []
    for entity in sorted(active, key=lambda item: (str(item.get("name") or ""), str(item.get("id")))):
        entity_id = str(entity.get("id"))
        name = str(entity.get("name") or "")
        type_ = str(entity.get("type") or "")
        if entity.get("identity_key") or entity.get("is_self"):
            role = "existing_self"
            self_entities.append(
                IdentityMigrationCandidate(
                    entity_id=entity_id,
                    name=name,
                    type=type_,
                    role=role,
                    relation_count=relation_counts.get(entity_id, 0),
                )
            )
        elif type_ == "生命体":
            self_entities.append(
                IdentityMigrationCandidate(
                    entity_id=entity_id,
                    name=name,
                    type=type_,
                    role="life_entity",
                    relation_count=relation_counts.get(entity_id, 0),
                )
            )
        elif type_ == "称呼别名":
            alias_entities.append(
                IdentityMigrationCandidate(
                    entity_id=entity_id,
                    name=name,
                    type=type_,
                    role="alias_entity",
                    relation_count=relation_counts.get(entity_id, 0),
                )
            )

    identity_key = f"self:{user_id}"
    blocking: list[str] = []
    recommended = None
    status: Literal["ready_for_confirmation", "needs_user_confirmation", "no_candidate"]
    if not self_entities:
        status = "no_candidate"
        blocking.append("没有可供用户确认的 self/生命体候选，需要用户提供展示名。")
    elif len(self_entities) == 1:
        status = "ready_for_confirmation"
        recommended = self_entities[0].name
        blocking.append("仍需用户确认展示名，并确认是否把下列称呼迁移为 aliases。")
    else:
        status = "needs_user_confirmation"
        blocking.append("存在多个身份候选，不能根据实体类型自动选择本人。")
        blocking.append("请提供展示名和需要保留的别名，系统再生成执行计划。")

    return IdentityMigrationPreview(
        user_id=user_id,
        status=status,
        identity_key=identity_key,
        recommended_display_name=recommended,
        candidate_self_entities=self_entities,
        alias_candidates=alias_entities,
        blocking_reasons=blocking,
    )


__all__ = [
    "IdentityMigrationCandidate",
    "IdentityMigrationPreview",
    "build_identity_migration_preview",
]

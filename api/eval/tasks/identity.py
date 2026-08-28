"""稳定本人身份规则评测。

这项只评价确定性的身份归一化安全层，不把 LLM 实体抽取质量混入分数；
实体抽取由 ``tasks/extraction.py`` 单独评估。
"""
from __future__ import annotations

import json
from pathlib import Path

from app.core.memory.extraction.identity import (
    normalize_entity_pool,
    self_identity_key,
)
from app.core.memory.graph_models import EntityNode
from eval.eval_config import EVAL_USER_ID

_GOLD = Path(__file__).parent.parent / "fixtures" / "gold" / "memory_identity.json"


class _StatefulIdentityRepo:
    """模拟图中唯一 self 节点，覆盖改名、否定和幂等重放。"""

    def __init__(self) -> None:
        self.self_entity: dict | None = None

    async def get_self_entity(self, user_id: str, identity_key: str):
        del user_id
        if self.self_entity and self.self_entity.get("identity_key") == identity_key:
            return dict(self.self_entity)
        return None

    async def get_entity_by_name(self, user_id: str, name: str):
        del user_id
        if not self.self_entity:
            return None
        names = {self.self_entity.get("name"), *(self.self_entity.get("aliases") or [])}
        return dict(self.self_entity) if name in names else None

    def persist(self, entity: EntityNode | None) -> None:
        if entity is None:
            return
        self.self_entity = {
            "id": entity.id,
            "name": entity.name,
            "type": entity.type,
            "description": entity.description,
            "aliases": list(entity.aliases),
            "identity_key": entity.identity_key,
            "is_self": entity.is_self,
            "importance": entity.importance,
            "confidence": entity.confidence,
        }


def _has_redirect_to_self(
    entities: list[EntityNode], redirect: dict[str, str], name: str, self_id: str
) -> bool:
    return any(
        entity.name == name and redirect.get(entity.id) == self_id for entity in entities
    )


async def eval_identity() -> tuple[dict, list]:
    data = json.loads(_GOLD.read_text(encoding="utf-8"))
    uid = str(EVAL_USER_ID)
    stable_id = self_identity_key(uid)
    repo = _StatefulIdentityRepo()
    details: list[dict] = []
    unsafe_total = 0
    unsafe_links = 0
    stable_checks = 0
    stable_passes = 0

    for item in data:
        original = [
            EntityNode(user_id=uid, name=name, type="生命体")
            for name in item.get("candidate_entities", [])
        ]
        normalized, redirect = await normalize_entity_pool(
            repo=repo,
            user_id=uid,
            text=item["text"],
            entities=original,
        )
        self_nodes = [entity for entity in normalized if entity.is_self]
        self_node = self_nodes[0] if self_nodes else None
        assertions: dict[str, bool] = {}

        if item.get("expected_target") == "self":
            assertions["has_canonical_self"] = self_node is not None
        if expected := item.get("expected_display_name"):
            assertions["display_name"] = bool(self_node and self_node.name == expected)
        if expected_alias := item.get("expected_alias"):
            assertions["alias_added"] = bool(
                self_node and expected_alias in set(self_node.aliases)
            )
        if historical := item.get("expected_historical_alias"):
            assertions["historical_alias_kept"] = bool(
                self_node and historical in set(self_node.aliases)
            )
        if invalid := item.get("must_not_add_active_alias"):
            assertions["invalid_alias_removed"] = bool(
                self_node
                and self_node.name != invalid
                and invalid not in set(self_node.aliases)
            )
        if item.get("must_not_auto_link_self"):
            unsafe_total += 1
            candidate_name = item["candidate_entities"][0]
            linked = _has_redirect_to_self(original, redirect, candidate_name, stable_id)
            unsafe_links += int(linked)
            assertions["external_entity_not_linked"] = not linked
        if item.get("must_not_create_second_self"):
            stable_checks += 1
            stable = len(self_nodes) == 1 and self_node.id == stable_id
            stable_passes += int(stable)
            assertions["single_stable_self"] = stable

        passed = bool(assertions) and all(assertions.values())
        details.append(
            {
                "id": item["id"],
                "scenario": item["scenario"],
                "passed": passed,
                "assertions": assertions,
                "self": (
                    {
                        "id": self_node.id,
                        "name": self_node.name,
                        "aliases": self_node.aliases,
                    }
                    if self_node
                    else None
                ),
                "redirected_names": sorted(
                    entity.name for entity in original if entity.id in redirect
                ),
            }
        )
        repo.persist(self_node)

    passed_count = sum(1 for row in details if row["passed"])
    total = len(details)
    table = {
        "确定性身份安全层": {
            "CaseAccuracy": round(passed_count / total, 4) if total else 0.0,
            "UnsafeSelfLinkRate": round(unsafe_links / unsafe_total, 4)
            if unsafe_total
            else 0.0,
            "StableSelfRate": round(stable_passes / stable_checks, 4)
            if stable_checks
            else 0.0,
            "Cases": total,
        }
    }
    return table, details

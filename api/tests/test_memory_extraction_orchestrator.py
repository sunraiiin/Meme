import unittest
from unittest.mock import AsyncMock, patch

from app.core.memory.extraction.models import ExtractedStatement, TripletExtractionResult
from app.core.memory.graph_models import EntityNode


class MemoryExtractionOrchestratorTests(unittest.IsolatedAsyncioTestCase):
    async def test_identity_redirect_reaches_mentions_relations_and_involves(self):
        statement = ExtractedStatement(statement="林舟正在照顾多多。")
        triplets = TripletExtractionResult(
            entities=[
                {"entity_idx": 1, "name": "林舟", "type": "生命体"},
                {"entity_idx": 2, "name": "多多", "type": "生命体"},
            ],
            triplets=[
                {
                    "subject_name": "林舟",
                    "subject_id": 1,
                    "predicate": "照顾",
                    "object_name": "多多",
                    "object_id": 2,
                    "predicate_surface": "正在照顾",
                }
            ],
            events=[{"title": "照顾多多", "participants": ["林舟", "多多"]}],
        )
        statement_mock = AsyncMock(return_value=[statement])
        triplet_mock = AsyncMock(return_value=[triplets])

        async def normalize(*, repo, user_id, text, entities):
            del repo, user_id, text
            original_self = next(entity for entity in entities if entity.name == "林舟")
            ordinary = next(entity for entity in entities if entity.name == "多多")
            canonical_self = EntityNode(
                id="canonical-self",
                user_id="user-1",
                name="林舟",
                type="生命体",
                identity_key="self:user-1",
                is_self=True,
            )
            return [canonical_self, ordinary], {original_self.id: canonical_self.id}

        async def embed(_client, names):
            return [[float(index)] for index, _name in enumerate(names)]

        async def dedup_batch(_client, entities):
            return entities, {}

        async def merge_graph(_client, _repo, _user_id, entities):
            return entities, {}

        persisted = AsyncMock()
        fake_repo = object()
        fake_engine = type("FakeEngine", (), {"run": AsyncMock()})()

        with (
            patch(
                "app.core.memory.extraction.orchestrator.MemoryGraphRepository",
                return_value=fake_repo,
            ),
            patch(
                "app.core.memory.extraction.orchestrator.chunker.split_chunks",
                return_value=["林舟正在照顾多多。"],
            ),
            patch(
                "app.core.memory.extraction.orchestrator.statement_extractor.extract_statements",
                new=statement_mock,
            ),
            patch(
                "app.core.memory.extraction.orchestrator.triplet_extractor.extract_triplets_batch",
                new=triplet_mock,
            ),
            patch(
                "app.core.memory.extraction.orchestrator.normalize_entity_pool",
                new=normalize,
            ),
            patch(
                "app.core.memory.extraction.orchestrator.embedder.embed_texts",
                new=embed,
            ),
            patch(
                "app.core.memory.extraction.orchestrator.dedup.dedup_within_batch",
                new=dedup_batch,
            ),
            patch(
                "app.core.memory.extraction.orchestrator.dedup.merge_with_graph",
                new=merge_graph,
            ),
            patch(
                "app.core.memory.extraction.orchestrator._persist",
                new=persisted,
            ),
            patch(
                "app.core.memory.clustering.label_propagation.LabelPropagationEngine",
                return_value=fake_engine,
            ),
            patch(
                "app.core.memory.extraction.orchestrator._maybe_trigger_reflection",
                new=AsyncMock(),
            ),
        ):
            from app.core.memory.extraction.orchestrator import run_extraction

            stats = await run_extraction(
                chat_client=object(),
                embed_client=object(),
                user_id="user-1",
                text="林舟正在照顾多多。",
            )

        payload = persisted.await_args.kwargs
        entities_by_name = {entity.name: entity for entity in payload["entities"]}
        ordinary_id = entities_by_name["多多"].id
        entity_ids = {entity.id for entity in entities_by_name.values()}
        self.assertEqual(
            entity_ids,
            {"canonical-self", ordinary_id},
        )
        self.assertEqual(
            {mention.entity_id for mention in payload["mentions"]},
            {"canonical-self", ordinary_id},
        )
        self.assertEqual(len(payload["relations"]), 1)
        relation = payload["relations"][0]
        self.assertEqual(relation.source_id, "canonical-self")
        self.assertEqual(relation.target_id, ordinary_id)
        self.assertEqual(relation.source_text, "林舟正在照顾多多。")
        self.assertEqual(
            {edge.entity_id for edge in payload["involves"]},
            {"canonical-self", ordinary_id},
        )
        self.assertEqual(stats.entity_ids, ["canonical-self", ordinary_id])
        self.assertEqual(stats.relation_count, 1)
        self.assertEqual(stats.event_count, 1)


if __name__ == "__main__":
    unittest.main()

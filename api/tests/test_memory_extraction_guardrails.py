"""记忆陈述与结构化抽取防护的纯单元测试。"""
import json
import unittest

from app.core.memory.extraction.models import ExtractedStatement
from app.core.memory.extraction.triplet_extractor import extract_triplets
from app.core.memory.preprocessing.statement_extractor import extract_statements


class _ChatClient:
    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.calls: list[tuple[list[dict], dict]] = []

    async def chat(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return self.responses.pop(0)


def _valid_triplet_response() -> str:
    return json.dumps(
        {
            "entities": [
                {
                    "entity_idx": 0,
                    "name": "用户",
                    "type": "生命体",
                    "description": "观看演唱会的用户",
                },
                {
                    "entity_idx": 1,
                    "name": "周杰伦",
                    "type": "生命体",
                    "description": "用户观看其演唱会的歌手",
                },
            ],
            "triplets": [],
            "events": [
                {
                    "title": "观看演唱会",
                    "description": "用户这个月观看了一场演唱会",
                    "event_time": "NULL",
                    "participants": ["用户", "周杰伦"],
                }
            ],
        },
        ensure_ascii=False,
    )


class StatementExtractionGuardrailTests(unittest.IsolatedAsyncioTestCase):
    async def test_pure_self_name_question_skips_llm(self):
        client = _ChatClient([])

        result = await extract_statements(client, "我叫什么名字？")

        self.assertEqual(result, [])
        self.assertEqual(client.calls, [])

    async def test_identity_question_paraphrase_is_filtered_from_llm_result(self):
        client = _ChatClient(
            [json.dumps({"statements": [{"statement": "用户的名字是什么"}]}, ensure_ascii=False)]
        )

        result = await extract_statements(client, "请回忆一下之前的身份信息。")

        self.assertEqual(result, [])
        self.assertEqual(len(client.calls), 1)

    async def test_identity_question_does_not_drop_a_separate_assertion(self):
        client = _ChatClient(
            [json.dumps({"statements": [{"statement": "用户喜欢音乐"}]}, ensure_ascii=False)]
        )

        result = await extract_statements(client, "我喜欢音乐，你知道我叫什么名字吗？")

        self.assertEqual([statement.statement for statement in result], ["用户喜欢音乐"])
        self.assertEqual(len(client.calls), 1)

    async def test_empty_assertion_retries_once_and_uses_second_result(self):
        client = _ChatClient(
            [
                '{"statements": []}',
                json.dumps(
                    {
                        "statements": [
                            {
                                "statement": "用户这个月观看了三位歌手的演唱会",
                                "statement_type": "FACT",
                                "temporal_type": "STATIC",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
            ]
        )

        result = await extract_statements(client, "我这个月看了三位歌手的演唱会")

        self.assertEqual(len(client.calls), 2)
        self.assertEqual(result[0].statement_type, "FACT")
        self.assertIn("空结果复核", client.calls[1][0][0]["content"])

    async def test_empty_question_result_does_not_retry(self):
        client = _ChatClient(['{"statements": []}'])

        result = await extract_statements(client, "我这个月看了谁的演唱会")

        self.assertEqual(result, [])
        self.assertEqual(len(client.calls), 1)


class TripletExtractionGuardrailTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_result_retries_once_and_uses_second_result(self):
        client = _ChatClient(
            [
                '{"entities": [], "triplets": [], "events": []}',
                _valid_triplet_response(),
            ]
        )
        statement = ExtractedStatement(
            statement="用户这个月看了周杰伦林俊杰的演唱会"
        )

        result = await extract_triplets(client, statement)

        self.assertEqual(len(client.calls), 2)
        self.assertEqual([entity.name for entity in result.entities], ["用户", "周杰伦"])
        self.assertEqual(result.events[0].title, "观看演唱会")
        self.assertIn("空结果复核", client.calls[1][0][0]["content"])

    async def test_non_empty_result_does_not_retry(self):
        client = _ChatClient([_valid_triplet_response()])

        result = await extract_triplets(
            client, ExtractedStatement(statement="用户这个月观看了一场演唱会")
        )

        self.assertEqual(len(client.calls), 1)
        self.assertTrue(result.entities)

    async def test_empty_non_fact_result_does_not_retry(self):
        client = _ChatClient(['{"entities": [], "triplets": [], "events": []}'])
        statement = ExtractedStatement(
            statement="用户认为这个方案不错",
            statement_type="OPINION",
        )

        result = await extract_triplets(client, statement)

        self.assertEqual(len(client.calls), 1)
        self.assertFalse(result.entities or result.triplets or result.events)

    async def test_unsolved_reference_skips_llm(self):
        client = _ChatClient([])
        statement = ExtractedStatement(
            statement="他这个月观看了一场演唱会",
            has_unsolved_reference=True,
        )

        result = await extract_triplets(client, statement)

        self.assertEqual(client.calls, [])
        self.assertFalse(result.entities or result.triplets or result.events)


if __name__ == "__main__":
    unittest.main()

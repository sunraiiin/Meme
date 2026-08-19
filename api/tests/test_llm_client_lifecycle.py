import asyncio
import unittest

from app.core.llm.client import _get_shared_client, close_llm_client


class LLMClientLifecycleTests(unittest.TestCase):
    def test_reuses_client_within_one_event_loop(self):
        async def run() -> bool:
            first = _get_shared_client()
            second = _get_shared_client()
            await close_llm_client()
            return first is second and first.is_closed

        self.assertTrue(asyncio.run(run()))

    def test_isolates_clients_between_event_loops(self):
        async def run():
            client = _get_shared_client()
            await close_llm_client()
            return client

        first = asyncio.run(run())
        second = asyncio.run(run())

        self.assertIsNot(first, second)
        self.assertTrue(first.is_closed)
        self.assertTrue(second.is_closed)

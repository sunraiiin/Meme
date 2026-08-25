"""聊天执行轨迹可靠性回归测试。"""

import uuid
import unittest
from datetime import datetime
from unittest.mock import patch

from app.core.agent.tracing.models import TraceRecord
from app.core.agent.tracing.span_recorder import SpanRecorder
from app.core.agent.tracing.tracer import Tracer
from app.models.agent_trace_model import AgentTrace
from app.services.chat_service import ChatService, bus


def _trace_record() -> TraceRecord:
    return TraceRecord(
        user_id=uuid.uuid4(),
        task_type="chat",
        task_id=uuid.uuid4(),
        task_name="测试执行轨迹",
        started_at=datetime.now(),
    )


class _FakeSession:
    def __init__(self) -> None:
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    def add(self, value) -> None:
        self.added.append(value)

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


class TraceReliabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_trace_main_record_is_persisted_before_context_yields(self):
        session = _FakeSession()

        async def fake_get_session():
            yield session

        with patch(
            "app.core.agent.tracing.span_recorder.get_session",
            return_value=fake_get_session(),
        ):
            await SpanRecorder().ensure_trace_persisted(_trace_record())

        self.assertEqual(session.commits, 1)
        self.assertEqual(session.rollbacks, 0)
        self.assertIsInstance(session.added[0], AgentTrace)
        self.assertEqual(session.added[0].task_type, "chat")

    async def test_tracer_awaits_durable_create_before_yield(self):
        record = _trace_record()

        class RecorderStub:
            def __init__(self) -> None:
                self.persisted = []
                self.updated = []

            async def ensure_trace_persisted(self, trace) -> None:
                self.persisted.append(trace)

            def push_trace_update(self, trace) -> None:
                self.updated.append(trace)

            def push_trace_create(self, trace) -> None:
                raise AssertionError("durable create succeeded; async fallback is unexpected")

        recorder = RecorderStub()
        with patch("app.core.agent.tracing.tracer.get_recorder", return_value=recorder):
            with patch("app.core.agent.tracing.tracer.settings.tracing_enabled", True):
                with patch("app.core.agent.tracing.tracer.settings.tracing_sample_rate", 1.0):
                    async with Tracer().trace(
                        user_id=record.user_id,
                        task_type=record.task_type,
                        task_id=record.task_id,
                        task_name=record.task_name,
                    ) as trace_ctx:
                        self.assertEqual(len(recorder.persisted), 1)
                        self.assertEqual(recorder.persisted[0].trace_id, trace_ctx.trace_id)

        self.assertEqual(len(recorder.updated), 1)

    async def test_chat_relay_forwards_trace_and_resume_events(self):
        events = [
            {"event": "trace", "data": {"trace_id": "trace-1"}},
            {"event": "resume", "data": {"content": "已生成", "trace_id": "trace-1"}},
            {"event": "done", "data": {"trace_id": "trace-1"}},
        ]

        async def fake_iter_channel(_pubsub, _cid):
            for event in events:
                yield event

        with patch.object(bus, "iter_channel", fake_iter_channel):
            output = [
                sse
                async for sse in ChatService(None)._relay(object(), "conversation-1")
            ]

        self.assertIn('event: trace\ndata: {"trace_id": "trace-1"}\n\n', output)
        self.assertIn(
            'event: resume\ndata: {"content": "已生成", "trace_id": "trace-1"}\n\n',
            output,
        )
        self.assertIn('event: done\ndata: {"trace_id": "trace-1"}\n\n', output)


if __name__ == "__main__":
    unittest.main()

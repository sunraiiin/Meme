"""原子陈述抽取：把一段文本切成带类型/时间属性的原子陈述句。

调用对话模型，按受控的陈述类型（FACT/OPINION/PREDICTION/SUGGESTION）和
时间类型（STATIC/DYNAMIC/ATEMPORAL）标注，并标记指代是否未解析。
失败返回空列表，不中断流水线。
"""
import re

from app.core.llm.client import LLMClient
from app.core.logging import get_logger
from app.core.memory.extraction.models import (
    ExtractedStatement,
    StatementExtractionResult,
)
from app.core.memory.extraction.identity import is_self_identity_question
from app.core.memory.json_utils import parse_json_object
from app.core.memory.prompt_renderer import render_prompt

logger = get_logger(__name__)

_QUESTION_MARKERS_RE = re.compile(
    r"(?:谁|什么|啥|哪(?:个|些|里|位|一天)?|多少|几(?:个|次|点)?|"
    r"怎么|为什么|为何|是否|能否|可不可以|吗|呢)"
)
_NON_MEMORY_RE = re.compile(
    r"^(?:你好|您好|嗨|谢谢|好的|好|再见|早上好|晚上好)[。！!]*$"
)
_NON_ASSERTION_REQUEST_RE = re.compile(
    r"^(?:请)?(?:帮我)?(?:回忆|查询|查找|告诉我|回答|解释|总结)"
)


def _filter_statements(result: StatementExtractionResult) -> list[ExtractedStatement]:
    return [
        statement
        for statement in result.statements
        if statement.statement
        and statement.statement.strip()
        and not is_self_identity_question(statement.statement)
    ]


def _should_retry_empty(content: str) -> bool:
    content = (content or "").strip()
    if (
        not content
        or _NON_MEMORY_RE.fullmatch(content)
        or _NON_ASSERTION_REQUEST_RE.match(content)
    ):
        return False
    if content.endswith(("?", "？")):
        return False
    return _QUESTION_MARKERS_RE.search(content) is None


async def _extract_once(
    client: LLMClient,
    content: str,
    context: str | None,
    *,
    retry: bool,
) -> tuple[list[ExtractedStatement], int]:
    prompt = render_prompt(
        "extract_statement.jinja2",
        content=content,
        context=context,
        retry=retry,
    )
    answer = await client.chat(
        [{"role": "user", "content": prompt}],
        temperature=0.0 if retry else 0.2,
        max_tokens=2048,
    )
    data = parse_json_object(answer)
    result = StatementExtractionResult.model_validate(data)
    return _filter_statements(result), len(answer or "")


async def extract_statements(
    client: LLMClient, content: str, context: str | None = None
) -> list[ExtractedStatement]:
    """从一段文本抽取原子陈述句。"""
    if is_self_identity_question(content):
        return []
    try:
        statements, answer_length = await _extract_once(
            client, content, context, retry=False
        )
    except Exception as e:
        logger.warning("陈述抽取失败（忽略该块）: %r", e)
        return []

    if statements or not _should_retry_empty(content):
        return statements

    logger.warning(
        "陈述抽取首次返回空结果，执行一次复核: content_chars=%d response_chars=%d",
        len(content),
        answer_length,
    )
    try:
        retry_statements, retry_answer_length = await _extract_once(
            client, content, context, retry=True
        )
    except Exception as e:
        logger.warning("陈述抽取复核失败（忽略该块）: %r", e)
        return []

    if not retry_statements:
        logger.warning(
            "陈述抽取复核仍为空: content_chars=%d response_chars=%d",
            len(content),
            retry_answer_length,
        )
    return retry_statements


__all__ = ["extract_statements"]

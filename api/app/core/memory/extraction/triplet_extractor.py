"""三元组萃取：从单条陈述抽取实体与 (主语, 谓词, 宾语) 三元组。

按受控词表（13 类实体 + 13 类谓词）约束 LLM 输出。指代未解析的陈述直接跳过。
失败返回空结果，不中断流水线。
"""
import asyncio

from app.core.llm.client import LLMClient
from app.core.logging import get_logger
from app.core.memory.extraction.models import (
    ExtractedStatement,
    TripletExtractionResult,
)
from app.core.memory.json_utils import parse_json_object
from app.core.memory.ontology import ENTITY_TYPES, PREDICATES
from app.core.memory.prompt_renderer import render_prompt

logger = get_logger(__name__)


def _norm_time(value: str | None) -> str:
    """时间字段空值统一成 NULL 字面量，供 prompt 复制。"""
    if not value or str(value).strip().upper() in {"NULL", "NONE", ""}:
        return "NULL"
    return str(value)


def _is_empty(result: TripletExtractionResult) -> bool:
    return not (result.entities or result.triplets or result.events)


async def _extract_once(
    client: LLMClient,
    statement: ExtractedStatement,
    context: str | None,
    dialog_at: str | None,
    *,
    retry: bool,
) -> tuple[TripletExtractionResult, int]:
    prompt = render_prompt(
        "extract_triplet.jinja2",
        statement=statement.statement,
        context=context,
        entity_types=ENTITY_TYPES,
        predicates=PREDICATES,
        valid_at="NULL",
        invalid_at="NULL",
        dialog_at=_norm_time(dialog_at),
        retry=retry,
    )
    answer = await client.chat(
        [{"role": "user", "content": prompt}],
        temperature=0.0 if retry else 0.1,
        max_tokens=2048,
    )
    data = parse_json_object(answer)
    return TripletExtractionResult.model_validate(data), len(answer or "")


async def extract_triplets(
    client: LLMClient,
    statement: ExtractedStatement,
    context: str | None = None,
    dialog_at: str | None = None,
) -> TripletExtractionResult:
    """从单条陈述抽取实体与三元组。"""
    if statement.has_unsolved_reference or not statement.statement.strip():
        return TripletExtractionResult()
    try:
        result, answer_length = await _extract_once(
            client, statement, context, dialog_at, retry=False
        )
    except Exception as e:
        logger.warning("三元组萃取失败（忽略该句）: %r", e)
        return TripletExtractionResult()

    if not _is_empty(result) or statement.statement_type.upper() != "FACT":
        return result

    logger.warning(
        "三元组萃取首次返回空结果，执行一次复核: statement_chars=%d response_chars=%d",
        len(statement.statement),
        answer_length,
    )
    try:
        retry_result, retry_answer_length = await _extract_once(
            client, statement, context, dialog_at, retry=True
        )
    except Exception as e:
        logger.warning("三元组萃取复核失败（忽略该句）: %r", e)
        return TripletExtractionResult()

    if _is_empty(retry_result):
        logger.warning(
            "三元组萃取复核仍为空: statement_chars=%d response_chars=%d",
            len(statement.statement),
            retry_answer_length,
        )
    return retry_result


async def extract_triplets_batch(
    client: LLMClient,
    statements: list[ExtractedStatement],
    context: str | None = None,
    dialog_at: str | None = None,
    concurrency: int = 4,
) -> list[TripletExtractionResult]:
    """并发对多条陈述做三元组萃取，限并发避免 LLM 限流。"""
    sem = asyncio.Semaphore(concurrency)

    async def _one(stmt: ExtractedStatement) -> TripletExtractionResult:
        async with sem:
            return await extract_triplets(client, stmt, context, dialog_at)

    return await asyncio.gather(*[_one(s) for s in statements])


__all__ = ["extract_triplets", "extract_triplets_batch"]

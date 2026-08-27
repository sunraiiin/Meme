"""评测模型配置。

默认从 ``.env.eval`` 构建独立客户端；本地开发也可以显式指定一个应用用户，
仅复用其加密模型配置，不复制 API Key、不读取该用户的业务数据。无论哪种方式，
评测数据始终写入固定 ``EVAL_USER_ID`` 命名空间，可整体清理。
"""
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from app.core.llm.client import LLMClient

# 加载评测专用环境变量（与 app 的 .env 隔离）
load_dotenv(Path(__file__).parent / ".env.eval")

# 固定评测命名空间：所有评测数据写在此 user_id 下，便于隔离与一键清理
EVAL_USER_ID = uuid.UUID("eee00000-0000-0000-0000-0000000000ee")


@dataclass(frozen=True)
class EvalClients:
    embed: LLMClient
    chat: LLMClient | None
    rerank: LLMClient | None
    verifier: LLMClient | None
    source: str


def _build(prefix: str) -> LLMClient | None:
    base = os.getenv(f"{prefix}_BASE_URL")
    key = os.getenv(f"{prefix}_KEY")
    model = os.getenv(f"{prefix}_MODEL")
    if not (base and key and model):
        return None
    return LLMClient(base_url=base, api_key=key, model_name=model)


def embed_client() -> LLMClient:
    c = _build("EVAL_EMBED")
    if c is None:
        raise RuntimeError("缺少 EVAL_EMBED_* 配置（请复制 .env.eval.example 为 .env.eval 并填写）")
    return c


def chat_client() -> LLMClient:
    c = _build("EVAL_CHAT")
    if c is None:
        raise RuntimeError("缺少 EVAL_CHAT_* 配置（请复制 .env.eval.example 为 .env.eval 并填写）")
    return c


def rerank_client() -> LLMClient | None:
    """可选；未配置返回 None（评测时跳过 rerank 相关项）。"""
    return _build("EVAL_RERANK")


def verifier_client() -> LLMClient | None:
    """V0.0.5 ② Verifier Loop 的「跨 family」验证模型(评测期专用)。

    未配置返回 None,hotpotqa A/B 实验时:
    - --verifier=cross 时若 None 自动降级到 same 并打 warning
    - --verifier=same 时不使用,本函数不调
    """
    return _build("EVAL_VERIFIER")


async def build_clients(
    *, model_user_id: uuid.UUID | None, need_chat: bool
) -> EvalClients:
    """构建本次评测客户端，密钥只存在于当前进程内存。

    ``model_user_id`` 仅用于读取模型连接配置。所有评测语料仍使用隔离的
    ``EVAL_USER_ID``，报告也不会记录该真实用户 ID。
    """
    if model_user_id is None:
        chat = _build("EVAL_CHAT")
        if need_chat and chat is None:
            raise RuntimeError(
                "缺少 EVAL_CHAT_* 配置（请复制 .env.eval.example 为 .env.eval 并填写）"
            )
        return EvalClients(
            embed=embed_client(),
            chat=chat,
            rerank=rerank_client(),
            verifier=verifier_client(),
            source="isolated-env",
        )

    from app.core.llm.resolver import (
        get_client_for_type,
        get_optional_client_for_type,
    )
    from app.db.postgres import SessionLocal

    async with SessionLocal() as session:
        embed = await get_client_for_type(session, model_user_id, "embedding")
        chat = (
            await get_client_for_type(session, model_user_id, "chat")
            if need_chat
            else await get_optional_client_for_type(session, model_user_id, "chat")
        )
        rerank = await get_optional_client_for_type(session, model_user_id, "rerank")
        verifier = await get_optional_client_for_type(session, model_user_id, "verifier")
    return EvalClients(
        embed=embed,
        chat=chat,
        rerank=rerank,
        verifier=verifier,
        source="encrypted-app-config",
    )

"""生成不含密钥和用户标识的评测运行清单。"""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings

_EVAL_DIR = Path(__file__).parent
_FIXTURES_DIR = _EVAL_DIR / "fixtures"
_REPO_ROOT = _EVAL_DIR.parents[1]


def _git(*args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=_REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return proc.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def fixtures_sha256() -> str:
    """对夹具相对路径和内容求单一摘要，证明评测数据版本。"""
    digest = hashlib.sha256()
    for path in sorted(p for p in _FIXTURES_DIR.rglob("*") if p.is_file()):
        digest.update(path.relative_to(_FIXTURES_DIR).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def fixture_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in sorted((_FIXTURES_DIR / "gold").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        counts[path.stem] = len(data) if isinstance(data, list) else 1
    counts["corpus_documents"] = len(list((_FIXTURES_DIR / "corpus").glob("*.*")))
    dialogues = json.loads((_FIXTURES_DIR / "dialogues.json").read_text(encoding="utf-8"))
    counts["dialogues"] = len(dialogues)
    return counts


def build_manifest(
    *,
    model_source: str,
    embed_model: str,
    chat_model: str | None,
    rerank_model: str | None,
    verifier_model: str | None,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """返回可直接写进 Markdown/JSON 的可复现元数据。"""
    status = _git("status", "--porcelain")
    safe_arguments = {
        key: value
        for key, value in arguments.items()
        if key not in {"model_user_id"} and value not in {None, False}
    }
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git("rev-parse", "HEAD"),
        "git_dirty": bool(status and status != "unknown"),
        "fixture_sha256": fixtures_sha256(),
        "fixture_counts": fixture_counts(),
        "model_source": model_source,
        "models": {
            "embedding": embed_model,
            "chat": chat_model or "(not used)",
            "rerank": rerank_model or "(not configured)",
            "verifier": verifier_model or "(not configured)",
        },
        "parameters": {
            "embedding_dimensions": settings.embedding_dims,
            **safe_arguments,
        },
    }

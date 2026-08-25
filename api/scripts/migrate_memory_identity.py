"""执行一次已确认的 canonical self 身份迁移。

示例：
    uv run python -m scripts.migrate_memory_identity \
      <user_id> <canonical_entity_id> --alias-entity-id <alias_id> \
      --display-name 林舟 --confirm

脚本要求显式提供实体 ID，不根据名称猜测迁移目标。
"""
import argparse
import asyncio
import json
import uuid

from app.db.neo4j import close as close_neo4j
from app.db.postgres import SessionLocal, close as close_postgres
from app.services.memory_identity_migration_service import MemoryIdentityMigrationService


async def _run(args: argparse.Namespace) -> None:
    user_id = uuid.UUID(args.user_id)
    async with SessionLocal() as session:
        result = await MemoryIdentityMigrationService(session=session).execute(
            user_id,
            canonical_entity_id=args.canonical_entity_id,
            alias_entity_ids=args.alias_entity_id,
            display_name=args.display_name,
            confirmed=args.confirm,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


async def _run_and_close(args: argparse.Namespace) -> None:
    try:
        await _run(args)
    finally:
        await close_neo4j()
        await close_postgres()


def main() -> None:
    parser = argparse.ArgumentParser(description="执行已确认的 Meme 记忆身份迁移")
    parser.add_argument("user_id", help="用户 UUID")
    parser.add_argument("canonical_entity_id", help="明确选定的本人实体 ID")
    parser.add_argument(
        "--alias-entity-id", action="append", default=[], help="需要合并的称呼别名实体 ID，可重复传入"
    )
    parser.add_argument("--display-name", required=True, help="迁移后的本人展示名")
    parser.add_argument("--confirm", action="store_true", help="确认执行写入")
    args = parser.parse_args()
    if not args.confirm:
        parser.error("身份迁移是写操作，必须显式传入 --confirm")
    asyncio.run(_run_and_close(args))


if __name__ == "__main__":
    main()

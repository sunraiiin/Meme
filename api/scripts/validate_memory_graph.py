"""只读运行一个用户图谱质量报告。

用法：uv run python scripts/validate_memory_graph.py <user_id>
"""
import argparse
import asyncio
import json

from app.core.memory.validation.graph_validator import validate_graph
from app.db.neo4j import close, get_driver
from app.repositories.neo4j import cypher_queries as cq


async def _run(user_id: str) -> None:
    driver = get_driver()
    try:
        async with driver.session() as session:
            entity_result = await session.run(cq.VALIDATOR_ENTITIES, user_id=user_id)
            entities = [dict(record) async for record in entity_result]
            relation_result = await session.run(cq.VALIDATOR_RELATIONS, user_id=user_id)
            relations = [dict(record) async for record in relation_result]
        report = validate_graph(user_id=user_id, entities=entities, relations=relations)
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    finally:
        await close()


def main() -> None:
    parser = argparse.ArgumentParser(description="只读检查 Meme 记忆图谱")
    parser.add_argument("user_id", help="用户 UUID")
    args = parser.parse_args()
    asyncio.run(_run(args.user_id))


if __name__ == "__main__":
    main()

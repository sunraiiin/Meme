"""记忆路由：主动记住 / 列表 / 详情 / 删除。

检索接口在第③步随记忆检索一起加入。
"""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.response import success
from app.db.postgres import get_session
from app.models.user_model import User
from app.schemas.memory_schema import (
    MemoryCurationExecuteRequest,
    MemoryCurationPlanRequest,
    MemorySearchRequest,
    RememberRequest,
)
from app.services.memory_curation_service import MemoryCurationService
from app.services.memory_graph_validation_service import MemoryGraphValidationService
from app.services.memory_identity_migration_service import MemoryIdentityMigrationService
from app.services.memory_service import MemoryService

router = APIRouter(prefix="/memories", tags=["memory"])


@router.post("/remember")
async def remember(
    body: RememberRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = MemoryService(session)
    memory = await service.remember(user.id, body.text)
    return success(service.to_out_dict(memory), "已提交，正在萃取记忆")


@router.post("/search")
async def search_memory(
    body: MemorySearchRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    hits = await MemoryService(session).search(user.id, body.query, body.top_k)
    return success(hits)


@router.post("/curation/plan")
async def plan_memory_curation(
    body: MemoryCurationPlanRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """把自然语言整理请求转成只读、可审阅的结构化计划。"""
    plan = await MemoryCurationService(session=session).plan(user.id, body.request)
    return success(plan)


@router.post("/curation/execute")
async def execute_memory_curation(
    body: MemoryCurationExecuteRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """验证短期令牌并执行已确认的白名单整理计划。"""
    result = await MemoryCurationService(session=session).execute(
        user.id, body.plan, body.confirmation_token, body.confirmed
    )
    return success(result, "记忆整理已执行")


@router.post("/curation/undo/{operation_id}")
async def undo_memory_curation(
    operation_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """从执行审计中的原始快照恢复可安全撤销的操作。"""
    result = await MemoryCurationService(session=session).undo(user.id, operation_id)
    return success(result, "记忆整理已撤销")


@router.get("/curation/audit")
async def list_memory_curation_audit(
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """返回当前用户的记忆整理执行审计。"""
    return success(await MemoryCurationService(session=session).audit(user.id, limit))


@router.get("/profile")
async def get_profile(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """画像视图：系统记住的实体（按类型分组）+ 类型计数。"""
    data = await MemoryService(session).get_profile(user.id)
    return success(data)


# ── V0.0.5 ⑤ 记忆审查与人类反馈闭环 ──

@router.get("/review/overview")
async def review_overview(
    days: int = 30,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Tab 1「我的记忆全景」聚合:类型分布 / 置信度直方 / 长短期 / 30 天趋势 / 纠错统计。"""
    return success(await MemoryService(session).review_overview(user.id, days=days))


@router.get("/review/entities")
async def list_review_entities(
    max_confidence: float = 0.75,
    type: str | None = None,
    include_verified: bool = False,
    limit: int = 50,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Tab 2 审查列表:筛选低置信度实体(默认 < 0.75 且未 verified)。"""
    return success(
        await MemoryService(session).list_review_entities(
            user.id,
            max_confidence=max_confidence,
            type_=type,
            include_verified=include_verified,
            limit=limit,
        )
    )


@router.post("/review/{entity_id}/confirm")
async def confirm_entity(
    entity_id: str,
    body: dict | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """👍 确认实体正确:human_verified=true / confidence=1.0。"""
    reason = (body or {}).get("reason")
    return success(await MemoryService(session).confirm_entity(user.id, entity_id, reason))


@router.patch("/review/{entity_id}/correct")
async def correct_entity(
    entity_id: str,
    body: dict,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """✏️ 修正实体属性(name / type / description / aliases 任一可选)。"""
    return success(
        await MemoryService(session).correct_entity_with_reason(
            user.id, entity_id,
            name=body.get("name"),
            type_=body.get("type"),
            description=body.get("description"),
            aliases=body.get("aliases"),
            reason=body.get("reason"),
        )
    )


@router.delete("/review/{entity_id}")
async def delete_entity_with_reason(
    entity_id: str,
    reason: str | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """🗑 删除实体(可带 reason);失败可从 memory_corrections.before 回滚。"""
    return success(
        await MemoryService(session).delete_entity_with_reason(user.id, entity_id, reason)
    )


@router.delete("/entity/{entity_id}")
async def delete_entity(
    entity_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """删除单个记忆实体（连带其关系）。"""
    await MemoryService(session).delete_entity(user.id, entity_id)
    return success(message="删除成功")


@router.get("/communities")
async def list_communities(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """社区列表（名称/摘要/成员数）。"""
    return success(await MemoryService(session).list_communities(user.id))


@router.get("/communities/{community_id}")
async def community_members(
    community_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """某社区的成员实体。"""
    return success(await MemoryService(session).community_members(user.id, community_id))


@router.post("/recluster")
async def recluster(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """手动触发全量社区聚类。"""
    await MemoryService(session).recluster(user.id)
    return success(message="聚类完成")


@router.post("/merge-duplicates")
async def merge_duplicates(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """合并历史重复实体（同名同类型只保留一个图节点）。"""
    removed = await MemoryService(session).merge_duplicates(user.id)
    return success({"removed": removed}, f"已合并 {removed} 个重复实体")


@router.post("/consolidate")
async def consolidate(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """手动触发记忆巩固（短期记忆→长期 + 核心实体画像增强）。"""
    stats = await MemoryService(session).consolidate(user.id)
    return success(stats, "记忆巩固完成")


@router.get("/insights")
async def list_insights(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """AI 对你的洞察：反思引擎归纳的高层理解。"""
    return success(await MemoryService(session).list_insights(user.id))


@router.post("/reflect")
async def reflect(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """手动触发反思：归纳高层洞察 Insight。"""
    stats = await MemoryService(session).reflect(user.id)
    return success(stats, "反思完成")


@router.delete("/insights/{insight_id}")
async def delete_insight(
    insight_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """删除单条洞察。"""
    await MemoryService(session).delete_insight(user.id, insight_id)
    return success(message="删除成功")


@router.get("/graph")
async def get_graph(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """知识图谱全量数据：实体节点 + 关系边 + 社区。"""
    return success(await MemoryService(session).get_graph(user.id))


@router.get("/graph/validate")
async def validate_memory_graph(
    user: User = Depends(get_current_user),
):
    """只读扫描当前用户图谱，返回迁移前质量报告。"""
    report = await MemoryGraphValidationService().validate(user.id)
    return success(report)


@router.get("/graph/identity-migration-preview")
async def preview_memory_identity_migration(
    user: User = Depends(get_current_user),
):
    """只读列出 canonical self 身份迁移候选，不自动选择或写入。"""
    preview = await MemoryIdentityMigrationService().preview(user.id)
    return success(preview)


@router.get("/graph/entity/{entity_id}")
async def get_entity_subgraph(
    entity_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """单实体一跳邻居子图。"""
    return success(await MemoryService(session).get_entity_subgraph(user.id, entity_id))


@router.get("/timeline")
async def get_timeline(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """事件时间线（按事件时间倒序）。"""
    return success(await MemoryService(session).get_timeline(user.id))


@router.get("")
async def list_memories(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = MemoryService(session)
    items, total = await service.list_memories(user.id, page, page_size)
    return success(
        {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [service.to_out_dict(m) for m in items],
        }
    )


@router.get("/{memory_id}")
async def get_memory(
    memory_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = MemoryService(session)
    memory = await service.get_detail(user.id, memory_id)
    return success(service.to_out_dict(memory))


@router.delete("/{memory_id}")
async def delete_memory(
    memory_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await MemoryService(session).delete(user.id, memory_id)
    return success(message="删除成功")

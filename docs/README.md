# Meme 文档导航

这里保存 Meme 自己的产品、架构和重构决策。后续开发以仓库内文档和 GitHub Issue 为准，聊天记录只作为讨论上下文。

## 当前基线

- [现有系统与功能依赖地图](architecture/CURRENT-SYSTEM.md)
- [功能保留、隐藏、删除与重设计提案](refactor/FEATURE-DECISIONS.md)
- [目标架构与分阶段实施计划](refactor/TARGET-ARCHITECTURE.md)
- [项目路线图](ROADMAP.md)
- [代码来源说明](SOURCE-NOTICE.md)

## 决策状态

`FEATURE-DECISIONS.md` 当前是 `Draft`。只有用户确认后的功能决策，才能进入代码删除或数据库迁移阶段。

## 文档维护规则

1. 功能范围变化时，同步更新功能决策和目标架构。
2. 代码实现通过 GitHub Issue、独立分支和 Pull Request 追踪。
3. 影响数据结构、接口或部署方式的决定，记录原因、替代方案和迁移方法。
4. README 只保留项目入口信息，详细设计统一放在 `docs/`。

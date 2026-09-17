# 文档规范（docs/）

- `docs/architecture.md`：架构说明——分层、数据流、注册表 schema、实例生命周期。架构变更必须先改代码后改文档，同一批提交内完成。
- `docs/development.md`：开发环境搭建、命令、调试技巧。只记录实际验证过的命令。
- 技术术语保留英文（LightRAG、workspace、embedding、LRU），叙述使用中文。
- 每篇文档开头一句话说明本文覆盖范围；不写空泛的营销语言。
- 关键设计决策若影响后续维护，除文档外同步在 `.agents/notes/` 留一条 Agent Note。

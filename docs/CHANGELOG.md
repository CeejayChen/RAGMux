# 变更记录

## 0.2.0（2026-09-17）

界面形态与模型接入的重大更新。**破坏性变更**：旧版 `data/registry.db`（含 kb_groups 表）不兼容，升级前删除 `data/` 目录。

### 新增

- **Ollama provider（开源模型优先）**：llm/embedding 支持原生 Ollama 协议；`extra.options` 透传 ollama options（含 `think: false` 关闭思考型模型推理）；`GET /api/providers/ollama/models` 拉取远端已装模型列表；界面新建配置默认选中 Ollama 并支持一键拉取模型。
- 离线 tokenizer 启用条件扩展：绑定 mock **或 ollama** 的知识库均不依赖 tiktoken 联网下载。
- 管理界面改为 LightRAG WebUI 形态：左侧知识库列表 + 右侧管理面板，默认暗色主题。

### 变更

- **移除分组/层级管理**：知识库为扁平列表（增删改查）。删除 `kb_groups` 表、`/api/groups` 路由与前端层级树；`knowledge_bases` 表去掉 `group_id` 列。
- 实体抽取质量说明：≤1b 开源模型可能产出不合格结构（文档标记 failed 可重试），推荐 8b 以上模型。

### 验证

- 本机 Ollama（qwen3-embedding:0.6b + qwen3.5:0.8b）真实链路：连通性测试、中文文档导入、知识库内检索问答全部通过。
- 后端 pytest 17 项、前端 vitest 3 项、双端 lint 全绿。

## 0.1.0（2026-09-17）

首个可用版本。

- 单进程 KB Gateway：SQLite 注册表（分组树/知识库/模型配置）+ 实例管理器（懒加载、LRU 驱逐、引用计数、互斥创建）。
- 知识库层级运行时增删改查；实例动态构建，源码零硬编码。
- 文档管理（文本/文件导入、分页状态列表、详情、删除）、单库查询（6 模式）、跨库查询（同 embedding 校验）、图谱浏览。
- 模型配置：openai 兼容 / 通用 rerank API / 离线 mock 三类 provider，支持连通性测试与热更新失效重建。
- Web 管理界面（Vue 3 + TS + Element Plus）：层级树、文档、检索测试、图谱、设置、模型配置、系统概览。
- 测试：后端 pytest 18 项、前端 vitest 5 项，全部离线运行。

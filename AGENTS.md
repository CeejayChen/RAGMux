# RAGMux Agent 规范（常驻指令）

RAGMux：单进程知识库网关。以 LightRAG（`lightrag-hku` 包）为检索引擎，在其上提供**知识库的运行时增删改查**：知识库（扁平列表，无分组层级）→ 文档。所有 LightRAG 实例由注册表（SQLite）中的配置**动态创建**，源码中不允许出现针对具体业务知识库的硬编码。单服务实例同时提供 REST API 与 Web 管理界面（界面形态：左侧知识库列表 + 右侧选中知识库的管理面板，参照 LightRAG WebUI）。

> 本文件是 agent 与开发者的常驻上下文。改动架构约定时必须同步更新本文件与 `docs/architecture.md`。

## 环境与 Shell

- 平台 Windows，Shell 为 Git Bash（`echo $0` 含 `bash`、`uname -s` 含 `MINGW`）。Unix 惯用法可用；禁止 CMD 写法（`2>nul`、`del`、`set VAR=` 等）。
- Python 由 uv 管理（项目根 `.venv`），一律通过 `uv run <cmd>` 执行；前端一律通过 `pnpm <cmd>` 在 `web/` 目录执行。
- 本仓库文件路径传给 Windows 原生 Python（非 MSYS python）时用 `E:/...` 形式，不要用 `/e/...`。

## 常用命令

```bash
# 后端（项目根执行）
uv sync                      # 安装/同步依赖
uv run pytest                # 运行全部后端测试（禁止依赖外部 LLM/网络）
uv run pytest tests/test_api.py -k kbs -x         # 单文件/关键字
uv run ruff check src tests && uv run ruff format --check .   # Lint 与格式检查
uv run uvicorn ragmux.main:app --reload --port 9700   # 本地起服务

# 前端（web/ 目录执行）
pnpm install                 # 安装依赖
pnpm dev                     # Vite 开发服务器（代理 /api 到 9700）
pnpm build                   # 产出 dist/（后端托管所需）
pnpm test                    # Vitest 单测
pnpm lint                    # oxlint
pnpm format                  # prettier 写入格式化
```

写入 README/文档的命令必须实际跑通过才允许记录。

## 目录布局

```
src/ragmux/            后端包（FastAPI 单服务）
  config.py            服务配置（pydantic-settings，环境变量 RAGMUX_ 前缀）
  registry/            注册表：知识库/模型配置的 SQLite 持久层（唯一配置事实源）
  manager/             实例管理器（懒加载 + LRU 驱逐 + 互斥）与 LightRAG 实例工厂
  api/                 FastAPI 路由（全部挂 /api 前缀）
  providers/           模型接入（ollama、openai 兼容、rerank_api、mock）→ 按 provider 分发
  static/              前端构建产物（web/dist 构建后复制/指向，勿手改）
web/                   前端（Vue 3 + TS + Vite + Element Plus，暗色主题）
tests/                 pytest 测试（内存 SQLite + mock 模型函数）
docs/                  架构与开发文档
.agents/notes/         Agent Notes（设计决策记录，见下）
```

## 架构铁律

1. **注册表是唯一事实源**。知识库的 LightRAG 参数（存储后端、分块、模型绑定）只存于 SQLite 注册表；实例按需从注册表构建，进程重启或实例驱逐后能无损重建。禁止在源码里写死某个知识库的配置。
2. **单进程多实例**。每个知识库一个 `LightRAG` 实例，`workspace=kb_id`、`working_dir=<data_dir>/kbs/<kb_id>`。实例生命周期只由 `InstanceManager` 管理：懒加载、按 kb_id 互斥创建、LRU 驱逐时调用 `await rag.finalize_storages()`（严禁调用进程级的 `finalize_share_data()`）。
3. **数据面直调实例方法**。文档/查询/图谱直接调 `rag.ainsert / aquery / adelete_by_doc_id / doc_status.get_docs_paginated / get_knowledge_graph` 等，不复用 `lightrag.api.lightrag_server.create_app`。
4. **测试零外网**。单测一律使用 mock provider（确定性 embedding + 桩 LLM）或注入的 fake 函数；不得因缺少 API key 而失败。
5. **配置变更即失效**。更新知识库配置或其模型绑定后，必须使已加载实例失效（驱逐），下次访问按新配置重建。
6. **删除即清理**。删除知识库：先驱逐实例，再删注册表行，最后清理数据目录。
7. **模型策略：开源优先**。文档、示例、界面默认项优先推荐开源模型（本机 Ollama + qwen3 系列）；openai 兼容 provider 仅作为兼容选项。绑定 mock 或 ollama 的知识库自动启用离线 tokenizer（不依赖 tiktoken 联网下载）。

## 数据面 API 约定

- 全部业务路由挂 `/api` 前缀；响应为纯 JSON，错误返回 `{"detail": ...}`（FastAPI 默认）。
- 知识库维度资源一律以 `/api/kbs/{kb_id}/...` 呈现（documents、query、graph、stats）。
- 跨库查询 `POST /api/query` 接受 `kb_ids` 数组；仅允许 embedding 配置相同的库，不一致返回 400。
- 模型服务目录：`GET /api/providers/ollama/models?base_url=...` 拉取 Ollama 已装模型。

## 代码风格

- Python：ruff（line-length 100）；公开模块/函数写**中文 docstring**，仅在代码无法自解释的约束处加注释；类型注解完整。
- 前端：TypeScript strict；oxlint + prettier；组件 `script setup` + `<i18n>` 不引入，界面文案直接中文。
- 技术术语保留英文（LightRAG、workspace、LRU 等），叙述用中文。

## Agent Notes

重要设计决策（含被否方案）写入 `.agents/notes/implemented/<class>/YYYY-MM-DD-<topic>.md`，class ∈ {feature, architecture, bug-fix, testing, process}；标题即结论，正文给出背景/决策/后果三段。提案期决策放 `proposed/`，被否的放 `rejected/`，不得删除。

## 验收标准（随开发逐步补完，完成即勾选）

- [x] 单服务实例同时服务 API 与管理界面（生产模式托管前端构建产物）
- [x] 服务运行中对知识库增删改查（扁平列表，无分组层级）；配置存注册表，实例动态创建，无需改代码
- [x] 每个知识库内文档管理：文本/文件导入、分页列表与状态、详情、删除
- [x] 每个知识库查询（6 种模式）+ 跨库查询（同 embedding 校验）
- [x] 图谱浏览接口（labels + 子图）
- [x] 模型配置（llm/embedding/rerank）运行时 CRUD；支持 ollama（开源模型优先）、openai 兼容与 mock provider；ollama 可拉取远端模型列表
- [x] 管理页面：左侧知识库列表 + 右侧管理面板（文档/图谱/检索/设置）、模型配置、系统概览（暗色，参照 LightRAG WebUI）
- [x] Ollama + 开源模型真实链路验证：qwen3-embedding:0.6b（1024 维）嵌入、qwen3.5:0.8b 抽取与问答
- [x] 后端 pytest 全绿（mock provider，无外部依赖）；前端 vitest 通过；lint 通过
- [x] 端到端冒烟：建库 → 导入 → 查询 → 删除 全链路可用（mock 与本机 ollama 双通道验证）

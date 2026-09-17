# RAGMux 项目设计方案总结

> 用途：向领导汇报 & 团队同步 · 日期：2026-09-17 · 版本：0.2.0
> 阅读指引：第一、二节面向管理者；第三至六节面向研发同事。

---

## 一、项目背景与解决的核心问题

团队在知识库/RAG 场景选用 [LightRAG](https://github.com/HKUDS/LightRAG)（开源 GraphRAG 引擎，提供文档导入、知识图谱抽取、多模式检索问答）。它在单库内表现优秀，但存在一个工程空白：

**原生只支持"一个知识库 = 一个服务进程"**。当业务需要多个知识库（不同项目、不同数据域）时，只能部署多个进程——每个进程占用独立端口与内存、无统一管理入口、修改配置要改代码重启、运维成本随库数线性增长。

**RAGMux 的目标**：用**一个服务进程**管理**任意多个知识库**，所有操作（建库、删库、改配置、传文档、检索问答）在运行时通过界面或 API 完成，**不写一行代码、不重启服务**；并提供对标 LightRAG 官方 WebUI 的中文管理界面。

## 二、方案总览（一句话 + 一张图）

> 一句话：**以 LightRAG 为检索引擎，在单进程内自建一层"知识库网关"——SQLite 注册表存配置，实例管理器按需创建/回收 LightRAG 实例，模型接入层对接开源模型服务。**

```
浏览器 / agent 应用
    │  HTTP（REST API + Web 管理界面）
    ▼
┌─────────────────── RAGMux 单服务（FastAPI, 端口 9700）───────────────────┐
│  api/          管理与数据面路由（知识库、文档、查询、图谱、模型配置）        │
│  registry/     SQLite 注册表：知识库配置 + 模型配置（唯一配置事实源）        │
│  manager/      实例管理器：懒加载 / LRU 回收 / 互斥创建 / 引用保护          │
│  providers/    模型接入：Ollama（开源优先）｜OpenAI 兼容｜Rerank｜离线桩     │
│      ▼                                                                    │
│  LightRAG 实例池（每个知识库一个实例，workspace=kb_id 数据完全隔离）          │
└──────────────────────────────────────────────────────────────────────────┘
```

核心价值：

| 价值点 | 说明 |
|---|---|
| 单实例多库 | 一个进程管所有知识库，端口/内存/运维统一；库间通过 workspace 隔离，互不干扰 |
| 零代码运维 | 建库、换模型、调参数全部在界面/API 完成，配置持久化在 SQLite，重启后无损恢复 |
| 开源模型优先 | 一等支持 Ollama（本机已验证 qwen3 系列），无外部 API 依赖也可运行（内置离线演示模式） |
| 界面对标 LightRAG WebUI | 左侧知识库列表 + 右侧管理面板（文档/检索/图谱/设置），团队零学习成本 |
| 可演进 | 存储后端、模型 provider 均为注册表白名单 + 分发设计，接入新后端不改核心代码 |

## 三、架构设计（技术细节）

### 3.1 分层职责

- **api/**（FastAPI 路由）：全部挂 `/api` 前缀，同时托管前端构建产物（生产模式单端口服务）。
- **registry/**（注册表）：**唯一配置事实源**。知识库的所有 LightRAG 参数只存于 SQLite；进程重启、实例回收、配置热更新后都能从注册表无损重建实例。源码中禁止出现针对具体知识库的硬编码。
- **manager/**（实例管理器）：知识库 → LightRAG 实例的完整生命周期：首次访问懒加载、按 kb_id 互斥创建、容量超限 LRU 回收、引用计数保护使用中的实例不被误回收、配置变更自动失效重建。
- **providers/**（模型接入）：把注册表中的模型配置构建为 LightRAG 可调用的函数，按 provider 分发。
- **数据面**：直调 LightRAG 实例方法（导入管线、检索、图谱、文档状态），不绕道 LightRAG 官方 server，保证单进程内对实例的完全管控。

### 3.2 数据库设计（SQLite，`data/registry.db`）

两张表，扁平结构（`知识库 → 模型配置` 引用关系）：

| 表 | 关键字段 | 说明 |
|---|---|---|
| `knowledge_bases` | id、name（唯一）、description、enabled、llm/embedding/rerank 三个模型引用、config（JSON） | config 为白名单化的 LightRAG 参数：存储后端四件套、分块大小、并发上限、抽取语言、查询默认值。id 同时充当 LightRAG workspace 与数据目录名 |
| `kb_profiles` | id、name（唯一）、kind（llm/embedding/rerank）、provider、base_url、api_key、model、dimension（embedding 必填）、extra | 模型连接配置，多库可复用同一配置；修改后自动失效引用它的实例 |

知识库的真实检索数据（向量、图谱、chunk、文档状态）由 LightRAG 落盘在 `data/kbs/<kb_id>/`，RAGMux 只通过实例方法读写，不耦合其内部格式。

### 3.3 关键机制

- **实例生命周期**：懒加载 → 常驻（LRU，默认容量 8）→ 回收时安全关闭存储；配置变更 → 失效重建，使用中的实例延迟到用完再回收。
- **导入管线**：异步两段式——文档入队即返回（202），后台任务处理（解析→分块→嵌入→图谱抽取），界面轮询状态（待处理/解析中/处理中/已完成/失败）。
- **跨库查询**：`POST /api/query` 传入多个 kb_id 并发检索；强制"同 embedding 配置"硬校验（不同向量空间分数不可比），不满足返回 400。
- **离线能力**：绑定 Ollama/mock 的知识库自动启用离线 tokenizer，本地部署零外网依赖。

### 3.4 模型接入与开源策略

模型策略为**开源优先**，OpenAI 兼容接口仅作为兼容选项：

| 用途 | 内置 provider | 推荐配置 |
|---|---|---|
| LLM（图谱抽取+问答） | `ollama`（原生协议，支持关闭思考模式）、`openai` 兼容、`mock` 离线桩 | Ollama + qwen3 系列，**抽取建议 8b 及以上** |
| Embedding | `ollama`、`openai` 兼容、`mock` | `qwen3-embedding:0.6b`（1024 维）/ bge-m3 / nomic-embed-text |
| Rerank | `rerank_api`（通用 /rerank 协议）、`mock` | 可选 |

界面能力：新建配置默认选中 Ollama，可一键拉取远端已装模型列表，一键连通性测试。

### 3.5 前端

Vue 3 + TypeScript(strict) + Element Plus（暗色主题，参照 LightRAG WebUI 布局）+ Vite + Pinia + Vue Router；工具链 oxlint + prettier + vitest。左侧知识库列表（新建/重命名/删除/状态标记），右侧选中库的四个面板：文档、检索测试、知识图谱（SVG 力导向可视化）、设置（参数与实例控制）；另有模型配置页与系统概览页。

## 四、API 概览（供集成同事）

| 资源 | 端点示例 | 说明 |
|---|---|---|
| 知识库 | `GET/POST /api/kbs`、`PATCH/DELETE /api/kbs/{id}` | 运行时增删改查，删除即清理数据目录 |
| 文档 | `POST /api/kbs/{id}/documents/text`、`GET /api/kbs/{id}/documents` | 导入返回 202 + track_id；分页列表含状态计数 |
| 查询 | `POST /api/kbs/{id}/query`、`POST /api/query`（跨库） | 6 种模式：local/global/hybrid/naive/mix/bypass |
| 图谱 | `GET /api/kbs/{id}/graph/labels`、`GET /api/kbs/{id}/graph` | 标签 + 子图，供可视化 |
| 模型配置 | `GET/POST /api/profiles`、`POST /api/profiles/{id}/test` | CRUD + 连通性测试；`GET /api/providers/ollama/models` 拉取模型列表 |
| 系统 | `GET /api/health`、`GET /api/system/overview` | 健康检查、实例池概览 |

响应为纯 JSON，错误统一 `{"detail": ...}`；agent 应用可直接用 HTTP 客户端集成。

## 五、当前状态（已完成并验证）

- **功能**：知识库增删改查（运行时）、文档管理全流程、单库/跨库查询、图谱浏览、模型配置管理与连通性测试、管理界面全部可用。
- **自动化测试**：后端 pytest 17 项、前端 vitest 3 项，全部离线运行（mock provider，不依赖外部服务）；双端 lint/格式检查通过。
- **真实链路验证**：本机 Ollama + 开源模型（qwen3-embedding:0.6b 嵌入、qwen3.5:0.8b 抽取问答）完成中文文档导入与检索问答实测，回答准确；界面建库全流程经浏览器操作实测通过。
- **文档**：README（快速开始）、docs/architecture.md（架构）、docs/development.md（开发指南）、docs/CHANGELOG.md（变更记录）、AGENTS.md（AI 辅助开发规范）齐备。

## 六、已知边界与风险

| 项 | 说明 | 缓解 |
|---|---|---|
| 文档格式 | 仅支持 UTF-8 文本类文件（.txt/.md 等） | PDF/Office 可接入 LightRAG 解析引擎，已留扩展点 |
| 鉴权 | API 无认证，默认仅监听本机 | 对外部署需加反向代理与认证 |
| 密钥存储 | api_key 明文存本地 SQLite | `data/` 目录不入库不外传；后续可加密 |
| 小模型抽取质量 | ≤1b 参数的开源模型实体抽取结构化输出易不合格 | 文档已注明建议 8b+；失败的文档可删除重导 |
| 单进程容量 | 所有库共享一个事件循环 | 按库可配并发上限；超大流量场景需演进为多进程（架构已预留） |

## 七、后续演进方向（建议）

1. PDF/Office 文档解析接入（LightRAG 自带解析引擎）。
2. 检索结果引用溯源（页面上展示答案引用的原文 chunk）。
3. agent 集成加强：MCP 接口或 OpenAPI 规范导出，供 AI 应用直接挂载知识库。
4. 重型存储后端演练（PostgreSQL/Neo4j/Milvus，配置即切换，已做白名单校验）。
5. 多用户与权限（若需对外服务）。

## 八、快速上手

```bash
# 依赖安装（需 uv、Node≥20 + pnpm、Ollama）
uv sync
cd web && pnpm install && pnpm build && cd ..
ollama pull qwen3:8b && ollama pull qwen3-embedding:0.6b

# 启动（单端口同时提供 API 与管理界面）
uv run uvicorn ragmux.main:app --host 127.0.0.1 --port 9700
# 打开 http://127.0.0.1:9700
```

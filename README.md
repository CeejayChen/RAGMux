# RAGMux

基于 [LightRAG](https://github.com/HKUDS/LightRAG)（`lightrag-hku`）的**单实例多知识库管理服务**。

LightRAG 原生只支持存储层 workspace 隔离、不支持应用层多知识库管理（官方形态是每库一个进程）。RAGMux 在单进程内补上这一层：SQLite 注册表作为唯一配置事实源，`InstanceManager` 按需创建/驱逐 LightRAG 实例，对外提供管理 API 与 Web 管理界面。**不修改 LightRAG 源码、不针对具体知识库写死任何配置。**

界面形态参照 LightRAG WebUI：**左侧知识库列表，右侧是选中知识库的管理面板**（文档 / 检索测试 / 知识图谱 / 设置），暗色主题。

## 模型策略：开源优先

优先使用开源模型（经 [Ollama](https://ollama.com) 部署），openai 兼容接口仅作为兼容选项：

| 用途 | 推荐开源模型 | 说明 |
|---|---|---|
| LLM（抽取+问答） | `qwen3:8b` 及以上 | 实体抽取对结构化输出要求高，小模型（≤1b）易产出不合格格式；检索问答可用更小模型 |
| Embedding | `qwen3-embedding:0.6b`（1024 维）、`bge-m3`（1024 维）、`nomic-embed-text`（768 维） | 维度须与配置一致 |
| Rerank | 通用 `/rerank` 服务或 bge-reranker 类 | 可选 |

绑定 Ollama/mock 的知识库自动启用离线 tokenizer，本地部署零外网依赖。

## 功能

- **知识库管理**：扁平列表，运行时新建/重命名/启停/删除，无需改代码或重启。
- **动态实例**：每个知识库一个 LightRAG 实例（`workspace=kb_id`），懒加载 + LRU 驱逐 + 引用计数防误驱逐；配置变更自动失效重建。
- **模型配置**：LLM / Embedding / Rerank 三类配置，支持 Ollama（可一键拉取远端已装模型列表）、OpenAI 兼容、通用 /rerank、离线 mock；支持连通性测试。
- **文档管理**：文本导入、UTF-8 文本文件上传、分页列表（含解析状态机）、原文详情、删除（连带 chunks 与图谱元素清理）。
- **检索**：单库查询（local/global/hybrid/naive/mix/bypass 六模式）+ 跨库并发查询（同 embedding 硬校验）。
- **图谱浏览**：标签列表 + 子图查询，前端 SVG 力导向可视化。

## 快速开始

前置：[uv](https://docs.astral.sh/uv/)、Node.js ≥ 20 与 pnpm；本机安装 [Ollama](https://ollama.com) 并拉取模型：

```bash
ollama pull qwen3:8b                 # LLM（抽取+问答）
ollama pull qwen3-embedding:0.6b     # Embedding（1024 维）
```

```bash
# 1. 后端依赖
uv sync

# 2. 构建前端（产物由后端托管）
cd web && pnpm install && pnpm build && cd ..

# 3. 启动单服务（API + 管理界面）
uv run uvicorn ragmux.main:app --host 127.0.0.1 --port 9700
```

打开 `http://127.0.0.1:9700`：

1. 「模型配置」→ 新建 Embedding（provider 选 **Ollama**，地址 `http://127.0.0.1:11434`，点"拉取模型列表"选 `qwen3-embedding:0.6b`，维度填 1024）→ 测试连通。
2. 同样新建 LLM 配置（如 `qwen3:8b`）；建议在 extra 中加 `{"options": {"think": false}}` 避免思考型模型拖慢输出。
3. 左侧「新建知识库」绑定上述配置 → 打开知识库 →「文档」导入文本 →「检索测试」提问 →「知识图谱」浏览。

没有 Ollama 时也可全部用 `mock` provider（离线确定性桩）体验完整界面流程。

开发模式（前端热更新）：`cd web && pnpm dev`（`/api` 自动代理到 9700）。

## 配置

服务级配置通过 `RAGMUX_` 前缀环境变量覆盖（见 `src/ragmux/config.py`）：

| 变量 | 默认 | 说明 |
|---|---|---|
| `RAGMUX_HOST` / `RAGMUX_PORT` | 127.0.0.1 / 9700 | 监听地址 |
| `RAGMUX_DATA_DIR` | `./data` | 注册表与知识库数据根目录 |
| `RAGMUX_MAX_LOADED_INSTANCES` | 8 | 实例池容量（LRU 驱逐） |
| `RAGMUX_STATIC_DIR` | `./web/dist` | 前端构建产物目录 |

知识库级配置（存储后端、分块、模型绑定、查询默认值）全部存于注册表，运行时通过 API/界面修改。

## 测试

```bash
uv run pytest            # 后端 17 个测试，mock provider，零外部依赖
cd web && pnpm test      # 前端 vitest
uv run ruff check src tests && cd web && pnpm lint   # 双端 lint
```

## 文档

- [docs/architecture.md](docs/architecture.md) — 架构、注册表 schema、实例生命周期、关键约束
- [docs/development.md](docs/development.md) — 开发环境、命令、常见调试
- [AGENTS.md](AGENTS.md) — agent/开发者常驻规范（含架构铁律与验收标准）

## 当前边界

- 文档导入仅支持 UTF-8 文本类文件（PDF/Office 需 LightRAG 解析引擎集成，见 development.md 的扩展指引）。
- API 无鉴权，默认监听本机；对外部署请自行加反代与认证。
- api_key 明文存于本地 SQLite，勿将 `data/` 目录提交或外传。
- 实体抽取质量取决于 LLM 能力：≤1b 的模型可能产出不合格结构（文档标记 failed 可重试），建议 8b 以上。

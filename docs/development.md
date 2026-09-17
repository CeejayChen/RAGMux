# 开发指南

## 环境

- Windows + Git Bash（会话首条命令 `echo $0 && uname -s` 确认）。
- Python ≥ 3.10（uv 管理，项目根 `.venv`）；Node.js ≥ 20 + pnpm 10。

## 常用命令

```bash
# 后端（项目根）
uv sync                                    # 同步依赖
uv run pytest -q                           # 全部测试（零外部依赖）
uv run pytest tests/test_api.py -k kbs -x  # 单文件/关键字
uv run ruff check src tests                # lint
uv run ruff format src tests               # 格式化
uv run uvicorn ragmux.main:app --reload --port 9700  # 起服务

# 前端（web/）
pnpm install
pnpm dev            # Vite dev server（/api 代理到 9700）
pnpm build          # 类型检查 + 产出 dist/（后端托管）
pnpm test           # vitest
pnpm lint           # oxlint
pnpm format         # prettier
```

## 添加可调参数

知识库可调参数的扩展路径是固定的：

1. `src/ragmux/registry/schemas.py`：在 `KBConfig` 加字段（白名单，有默认值）。
2. `src/ragmux/manager/factory.py`：在 `build()` 透传给 LightRAG 构造参数。
3. 前端 `web/src/components/KBSettingsPanel.vue`：加表单项。
4. 补测试（`tests/`）。

禁止绕过 `KBConfig` 直接透传任意 kwargs。

## 添加存储后端

LightRAG 的后端通过字符串注册表（`lightrag.kg.STORAGES`）解析。RAGMux 不需要改代码：在创建/更新知识库时把 `config.storage` 的四项（kv/vector/graph/doc_status）设为目标后端名即可（名称会被校验）。重型后端（PG/Neo4j/Milvus 等）的连接信息按 LightRAG 约定用环境变量提供。

## 模型 provider 与开源模型策略

模型策略为**开源优先**（Ollama + qwen3 系列等），新示例与文档默认展示 ollama。

内置 provider：`ollama`（llm/embedding）、`openai`（OpenAI 兼容）、`rerank_api`（通用 /rerank）、`mock`（离线桩）。Ollama 配置建议：

- `base_url` 形如 `http://127.0.0.1:11434`；界面可一键拉取已装模型列表。
- 思考型模型（qwen3 系列）建议 `extra = {"options": {"think": false, "num_ctx": 8192}}`，否则推理 token 会吃光输出预算。
- embedding 维度须与模型原生输出一致：qwen3-embedding:0.6b=1024、bge-m3=1024、nomic-embed-text=768。
- 实体抽取建议 8b 以上模型；≤1b 模型检索问答可用，抽取易失败（文档标记 failed，删除后可重导）。

## 添加模型 provider

1. `src/ragmux/providers/`：实现对应 builder（签名参考 `openai_compat.py`：LLM 返回 str，embedding 返回 `EmbeddingFunc`，rerank 返回 `list[{"index", "relevance_score"}]`），并在 `providers/__init__.py` 的分发函数中接线。
2. `src/ragmux/registry/store.py`：把 provider 名加进 `_PROFILE_PROVIDERS` 白名单。
3. 前端 `web/src/views/ProfilesView.vue` 的 `PROVIDERS_BY_KIND` 加选项。

## 离线测试约定

所有测试必须零外部依赖：

- 用 mock provider（`provider: "mock"`），不要在测试里请求真实 LLM/embedding。
- 不要依赖 tiktoken 的联网下载——mock provider 会自动启用离线 tokenizer（`providers/tokenizer.py`），新代码若直接构造 LightRAG 实例也请如此。
- 注册表用 `tmp_path` 下的独立 SQLite 文件（见 `tests/conftest.py`）。

## 调试技巧

- `GET /api/system/overview`：实例池驻留情况（loaded/active ids）。
- `GET /api/kbs/{id}/stats`：单库文档状态计数 + pipeline busy 状态。
- LightRAG 的 INFO 日志默认可见；ultragrid 排查管线问题时把 uvicorn 日志级别调到 info 观察enqueue/驱逐时序。
- Git Bash 下用 curl 发中文 JSON 会被编码破坏（Windows 控制台 GBK），把请求体写进 UTF-8 文件用 `curl -d @file`，或改用浏览器/前端调试（本项目冒烟用 Python urllib 脚本更稳）。
- 本机网络对 pypi.org / Azure CDN 可能抖动：装依赖可用 `uv add <pkg> --default-index https://pypi.tuna.tsinghua.edu.cn/simple`；ollama/mock 知识库因离线 tokenizer 不受 tiktoken 下载影响。

# 架构说明

本文描述 RAGMux 的分层结构、注册表 schema、实例生命周期与关键约束。核对基准：lightrag-hku 1.5.7。

## 分层

```
浏览器 / agent 客户端
   │  HTTP
   ▼
FastAPI 单服务（ragmux.main）
   ├─ api/          业务路由（/api 前缀）+ SPA 静态托管
   ├─ manager/      InstanceManager（生命周期）+ InstanceFactory（构建）
   ├─ providers/    KBProfile → llm/embedding/rerank 函数（openai 兼容 / mock / rerank_api）
   ├─ registry/     SQLite 注册表（唯一配置事实源）
   └─ LightRAG 实例池（每知识库一个，懒加载驻留内存）
            ▼
       lightrag-hku（文档管线、检索、图谱、存储抽象）
```

数据面不走 `lightrag.api.create_app`，直调实例方法：

| 操作 | LightRAG API |
|---|---|
| 导入 | `apipeline_enqueue_documents`（入队即返回）+ 后台任务 `apipeline_process_enqueue_documents` |
| 列表 | `doc_status.get_docs_paginated` + `doc_status.get_all_status_counts` |
| 详情 | `aget_docs_by_ids` + `full_docs.get_by_id` |
| 删除 | `adelete_by_doc_id` |
| 查询 | `aquery(query, param=QueryParam(...))` |
| 图谱 | `get_graph_labels` / `get_knowledge_graph` |

## 注册表 schema（SQLite，`data/registry.db`）

两张表，扁平结构（无分组层级——层级管理已按需求裁剪，见 CHANGELOG 0.2.0）：

- `kb_profiles`：模型配置。`kind ∈ {llm, embedding, rerank}`；`provider`：
  - `ollama`（**开源模型优先**，Ollama 原生协议，`base_url` 为 Ollama host，如 `http://127.0.0.1:11434`；`extra.options` 透传 ollama options，支持 `think: false` 关闭思考型模型的推理开销）；
  - `openai`（OpenAI 兼容 chat/embeddings 端点）；
  - `rerank_api`（通用 `POST {base_url}/rerank`）；
  - `mock`（确定性离线桩）。
  embedding 必须声明 `dimension`，且须与模型原生输出一致（qwen3-embedding:0.6b=1024、bge-m3=1024、nomic-embed-text=768）。
- `knowledge_bases`：知识库。持有三个模型引用（llm 可空——未绑定时回退内置 mock LLM，支持"先建库后绑模型"）与 `config` JSON（`registry/schemas.KBConfig` 的序列化：存储后端四件套、分块参数、并发上限、抽取语言、查询默认值）。存储后端名在创建/更新时对照 `lightrag.kg.STORAGES` 校验。

**设计不变式**：知识库的全部 LightRAG 参数只存在于注册表。进程重启、实例驱逐、配置热更新后，实例都能从注册表记录无损重建（`manager/factory.py` 是"注册表 → LightRAG"的唯一接线点）。

## 实例生命周期（`manager/instances.py`）

- **懒加载**：首次数据面访问（lease）时构建。构建参数来自注册表 bundle：`working_dir=data/kbs/<kb_id>`、`workspace=kb_id`（双保险隔离，文件/共享后端均安全）。
- **离线 tokenizer**：绑定 mock 或 ollama provider 的知识库自动启用内置离线 tokenizer（`providers/tokenizer.py`），规避 tiktoken 首次使用的联网下载——本地/离线部署零外网依赖。
- **互斥创建**：per-key `asyncio.Lock`，同一知识库并发 lease 只构建一次。
- **LRU 驱逐**：驻留超过 `RAGMUX_MAX_LOADED_INSTANCES` 时从最旧开始驱逐；驱逐调用实例级 `finalize_storages()`。**严禁调用进程级 `finalize_share_data()`**（会摧毁其他实例的共享锁表；仅进程退出路径可用，见 `manager/instances.py` 的 `close_all`）。
- **引用计数**：lease 期间 `active` 计数 >0，驱逐跳过在用实例；配置变更触发的 `invalidate` 遇在用实例则标记 `pending_evict`，最后一个引用释放时执行。无实例可驱逐时允许暂时超限（告警日志）。
- **数据面安全**：文档导入的"后台处理任务"独立持有一份 lease，即使处理期间实例被驱逐，任务也会按注册表重建实例继续处理（PENDING 状态已持久化）。

## 请求链路示例：导入文本

```
POST /api/kbs/{id}/documents/text
  → registry.get_kb_bundle(kb_id)        # kb + 三个 profile + KBConfig
  → manager.lease(bundle)                # 懒加载实例（可能触发 LRU 驱逐）
  → inst.apipeline_enqueue_documents()   # 落盘 PENDING，返回 track_id
  → asyncio.create_task(_drain(...))     # 后台 lease + process_enqueue_documents
  ← 202 {track_id, queued}
```

## 跨库查询约束

`POST /api/query` 要求所有 `kb_ids` 绑定**相同的 embedding 配置**（同 id），不同向量空间的分数不可比；不满足返回 400。逐库并发执行（asyncio.gather），单库失败不影响其他库（逐库隔离错误返回）。

## 模型 provider

`providers/` 按 profile.provider 分发（`providers/__init__.py` 是唯一分发点）：

- **ollama（开源优先）**：LLM 复用 LightRAG `ollama_model_complete`（实例内调用带 `hashing_kv`，自动启用 LLM 响应缓存；支持 `extra.options.think=false` 关闭思考型模型推理），embedding 复用 `ollama_embed`（预绑 host/model/options）。已用本机 Ollama + qwen3 系列完成真实链路验证。
- **openai 兼容**：`openai_complete_if_cache` / `openai_embed`。
- **rerank_api**：通用 `/rerank` 协议。
- **mock**：确定性离线桩：哈希 embedding（词级 MD5 落桶 + L2 归一化）、格式感知 LLM（按提示词特征返回实体抽取/关键词/问答三种格式）、词面 rerank。测试与演示零外部依赖。

模型能力边界（实测）：轻量开源模型（qwen3.5:0.8b）可胜任嵌入与检索问答；实体抽取对结构化输出要求高，建议 8b 及以上模型。

## 已知边界

- 单事件循环承载全部实例的导入/查询；重负载按库调低 `llm_model_max_async`/`embedding_func_max_async`。
- 删除知识库时若后台导入任务恰在运行，invalidate 会等引用归零再驱逐；随后才删注册表行与数据目录，窗口内新请求会得到 404（注册表行已删）——语义安全但非事务性。
- 前端图谱布局为轻量力导向实现，不提供大规模图（>500 节点）的交互性能。
- 文档导入去重按内容 hash + file_path，重复导入返回 failed（file name already exists），属预期行为。

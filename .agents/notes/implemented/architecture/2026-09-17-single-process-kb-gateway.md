# 单进程网关 + 注册表驱动的 LightRAG 多实例

日期：2026-09-17 · 状态：implemented · 分类：architecture

## 背景

LightRAG 原生只支持存储层 workspace 隔离，无应用层多知识库管理能力；官方形态是每库一个服务进程。需求要求：只部署一个服务实例、运行时增删改查知识库层级、LightRAG 实例不硬编码（不改代码即可建库）。多进程部署被明确否决（运维负担）。

## 决策

在单进程内实现 KB Gateway：SQLite 注册表（分组树 / 知识库 / 模型配置三张表）是唯一配置事实源；`InstanceManager` 按 kb_id 懒加载 `LightRAG` 实例（`workspace=kb_id`、`working_dir=data/kbs/<kb_id>`），per-key asyncio.Lock 防并发创建，LRU 驱逐并调用 `finalize_storages()`（进程级 `finalize_share_data()` 仅允许进程退出时调用）。数据面直调实例方法（`ainsert`/`aquery`/`doc_status.*`/`get_knowledge_graph`），不复用 `lightrag.api.create_app`。

可行性依据（已核对 lightrag-hku 1.5.7 源码）：共享状态按 `workspace:namespace` 键控（`kg/shared_storage.py`），实例间 pipeline 围栏互不干扰；`initialize_share_data()` 在 `LightRAG.__post_init__` 中幂等调用；LLM/embedding/rerank 为实例级状态，各库可绑不同模型。

## 后果

- 配置变更必须显式失效（驱逐）实例，否则旧配置驻留内存。
- 文件后端下实例持有打开的文件句柄，驱逐必须走 `finalize_storages()`，删除数据目录必须先驱逐。
- 单事件循环承载所有实例的导入与查询；重负载场景需限制 `llm_model_max_async`/`embedding_func_max_async`（注册表可按库配置）。
- 跨库查询受"同 embedding 配置"约束（不同向量空间不可比，参照 WeKnora 的硬约束设计）。

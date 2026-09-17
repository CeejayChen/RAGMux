# 扁平化知识库 + Ollama 开源模型优先

日期：2026-09-17 · 状态：implemented · 分类：architecture

## 背景

0.1.0 实现了"分组树 → 知识库"的层级管理，但需求方明确：不需要分组和层级，只要能增删一个个知识库；界面要对标 LightRAG WebUI（左侧知识库列表、右侧选中库的管理面板）。同时要求模型接入 Ollama，且模型策略尽可能采用开源模型。

## 决策

1. **裁剪层级**：删除 `kb_groups` 表与全部分组逻辑，`knowledge_bases` 去掉 `group_id`；前端层级树改为扁平列表。知识库 id 仍同时充当 `workspace` 与数据目录名，隔离语义不变。
2. **Ollama 作为一等 provider**：llm/embedding 走 LightRAG 自带 `ollama_model_complete` / `ollama_embed`，保留其 LLM 响应缓存路径（实例内 `hashing_kv` 注入）；`extra.options` 透传 ollama options（支持 `think:false`）；新增 `/api/providers/ollama/models` 拉取远端模型列表供界面选择。
3. **离线 tokenizer 规则扩展**：由"绑定 mock 才启用"扩展为"绑定 mock 或 ollama 即启用"——本地部署不应被 tiktoken 首次联网下载卡死（实测本机到 Azure CDN 不可达导致建库后首次导入直接 503）。
4. **开源优先落到产品默认**：界面新建配置默认 provider=ollama、排首位；README 给出开源模型推荐表与维度对照。

## 后果

- 旧注册表不兼容（含 kb_groups），升级需删 `data/`（已在 CHANGELOG 标注破坏性变更）。
- 跨库查询的"同 embedding 校验"语义不变，但失去分组后 `POST /api/query` 的 kb_ids 就是唯一的多库组织方式。
- 实测模型能力边界写入文档：qwen3.5:0.8b 可胜任检索问答，实体抽取需 8b+；思考型模型必须显式 `think:false`（否则推理 token 吃光 num_predict 导致空回答/抽取失败）。
- openai 兼容 provider 保留，但不再出现在任何默认项与示例首位。

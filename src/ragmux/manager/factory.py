"""实例工厂：把注册表记录（KBBundle）构建为可用的 LightRAG 实例。

工厂是"注册表 → LightRAG"的唯一接线点：新增可调参数时在
``KBConfig`` 加字段、在此透传，别处不得出现针对具体知识库的参数。
"""

from __future__ import annotations

from pathlib import Path

from lightrag import LightRAG
from lightrag.utils import Tokenizer, logger

from ragmux.providers import build_embedding_func, build_llm_func, build_rerank_func
from ragmux.providers.mock import mock_llm_func
from ragmux.providers.tokenizer import OfflineTokenizer
from ragmux.registry.store import KBBundle


class InstanceFactory:
    """按知识库构建 LightRAG 实例。实例的 initialize/finalize 由管理器编排。"""

    def __init__(self, kb_data_root: Path):
        self.kb_data_root = kb_data_root

    def working_dir(self, kb_id: str) -> Path:
        """知识库专属数据目录（文件后端的落盘位置）。"""
        return self.kb_data_root / kb_id

    async def build(self, bundle: KBBundle) -> LightRAG:
        kb = bundle.kb
        cfg = bundle.kb_config
        working_dir = self.working_dir(kb.id)
        working_dir.mkdir(parents=True, exist_ok=True)

        llm_profile = bundle.llm
        if llm_profile is not None:
            llm_func = build_llm_func(llm_profile)
            llm_name = llm_profile.model
        else:
            # 未绑定 LLM 配置时回退内置 mock LLM：允许"先建库后绑模型"的渐进式使用
            llm_func = mock_llm_func
            llm_name = "ragmux-mock-llm(未绑定)"
        kwargs = {
            "working_dir": str(working_dir),
            "workspace": kb.id,
            # 存储后端四件套（注册表白名单校验过名称）
            "kv_storage": cfg.storage.kv_storage,
            "vector_storage": cfg.storage.vector_storage,
            "graph_storage": cfg.storage.graph_storage,
            "doc_status_storage": cfg.storage.doc_status_storage,
            # 模型函数（实例级状态：各库可绑不同模型）
            "llm_model_func": llm_func,
            "llm_model_name": llm_name,
            "llm_model_max_async": cfg.llm_model_max_async,
            "embedding_func": build_embedding_func(bundle.embedding),
            "embedding_func_max_async": cfg.embedding_func_max_async,
            "embedding_batch_num": cfg.embedding_batch_num,
            # 分块
            "chunk_token_size": cfg.chunk_token_size,
            "chunk_overlap_token_size": cfg.chunk_overlap_token_size,
            # 实体抽取
            "addon_params": cfg.to_addon_params(),
        }
        if bundle.rerank is not None:
            kwargs["rerank_model_func"] = build_rerank_func(bundle.rerank)
        # mock / ollama 库使用离线 tokenizer：本地与离线部署零网络依赖
        # （tiktoken 首次使用需联网下载编码文件）。必须包一层 Tokenizer 适配
        # （truncate_by_token_limit 等方法由包装类提供）。
        if bundle.prefers_offline_tokenizer():
            kwargs["tokenizer"] = Tokenizer(model_name="offline", tokenizer=OfflineTokenizer())

        logger.info("构建 LightRAG 实例: kb=%s(%s) workspace=%s", kb.name, kb.id, kb.id)
        return LightRAG(**kwargs)

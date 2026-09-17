"""模型接入层：按 provider 把模型配置（KBProfile）构建为 LightRAG 可调用的函数。

- ``openai``：OpenAI 兼容 chat / embeddings 端点
- ``ollama``：Ollama 服务（chat / embed 原生协议）
- ``rerank_api``：通用 ``POST {base_url}/rerank`` 协议
- ``mock``：确定性离线桩（测试与演示）
"""

from __future__ import annotations

from ragmux.providers.mock import make_mock_embed_func, mock_llm_func, mock_rerank_func
from ragmux.providers.ollama import build_embedding_func as _build_ollama_embedding
from ragmux.providers.ollama import build_llm_func as _build_ollama_llm
from ragmux.providers.openai_compat import build_embedding_func as _build_openai_embedding
from ragmux.providers.openai_compat import build_llm_func as _build_openai_llm
from ragmux.providers.openai_compat import build_rerank_func as _build_rerank_api


def build_llm_func(profile):
    """按 provider 分发 LLM 函数构建。"""
    if profile.provider == "openai":
        return _build_openai_llm(profile)
    if profile.provider == "ollama":
        return _build_ollama_llm(profile)
    if profile.provider == "mock":
        return mock_llm_func
    raise ValueError(f"llm 类型不支持 provider={profile.provider}")


def build_embedding_func(profile):
    """按 provider 分发 embedding 函数构建。"""
    if profile.provider == "openai":
        return _build_openai_embedding(profile)
    if profile.provider == "ollama":
        return _build_ollama_embedding(profile)
    if profile.provider == "mock":
        from lightrag.utils import EmbeddingFunc

        if profile.dimension is None:
            raise ValueError(f"embedding 配置缺少 dimension: {profile.name}")
        return EmbeddingFunc(
            embedding_dim=profile.dimension,
            model_name=profile.model,
            func=make_mock_embed_func(profile.dimension),
        )
    raise ValueError(f"embedding 类型不支持 provider={profile.provider}")


def build_rerank_func(profile):
    """按 provider 分发 rerank 函数构建。"""
    if profile.provider == "rerank_api":
        return _build_rerank_api(profile)
    if profile.provider == "mock":
        return mock_rerank_func
    raise ValueError(f"rerank 类型不支持 provider={profile.provider}")


__all__ = ["build_embedding_func", "build_llm_func", "build_rerank_func"]

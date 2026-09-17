"""OpenAI 兼容与 rerank 协议的模型函数构建。

- LLM / embedding：复用 LightRAG 自带的 ``openai_complete_if_cache`` 与
  ``openai_embed``（OpenAI 兼容 API，包括各类自建网关）。
- rerank：通用 ``POST {base_url}/rerank`` 协议（Jina / SiliconFlow 等兼容实现）。
"""

from __future__ import annotations

from functools import partial
from typing import Any

import httpx
from lightrag.llm.openai import openai_complete_if_cache, openai_embed
from lightrag.utils import EmbeddingFunc, logger

from ragmux.registry.models import KBProfile


def build_llm_func(profile: KBProfile):
    """按模型配置构建 LightRAG ``llm_model_func``（签名由 LightRAG 约定）。"""
    extra = dict(profile.extra or {})

    async def llm_func(
        prompt: str,
        system_prompt: str | None = None,
        history_messages: list | None = None,
        **kwargs: Any,
    ) -> str:
        return await openai_complete_if_cache(
            profile.model,
            prompt,
            system_prompt=system_prompt,
            history_messages=history_messages or [],
            base_url=profile.base_url,
            api_key=profile.api_key,
            **{**extra, **kwargs},
        )

    return llm_func


def build_embedding_func(profile: KBProfile) -> EmbeddingFunc:
    """按模型配置构建 LightRAG ``embedding_func``。

    维度取自配置的 ``dimension``；openai provider 时由 LightRAG 侧自动注入
    ``send_dimensions`` 语义（openai_embed 支持 dimensions 参数裁剪）。
    """
    if profile.dimension is None:
        raise ValueError(f"embedding 配置缺少 dimension: {profile.name}")
    extra = dict(profile.extra or {})
    max_token_size = extra.pop("max_token_size", None)
    return EmbeddingFunc(
        embedding_dim=profile.dimension,
        max_token_size=max_token_size,
        model_name=profile.model,
        func=partial(
            openai_embed,
            model=profile.model,
            base_url=profile.base_url,
            api_key=profile.api_key,
            **extra,
        ),
    )


def build_rerank_func(profile: KBProfile):
    """构建 rerank 函数（通用 /rerank 协议，Jina / SiliconFlow 等兼容实现）。"""
    extra = dict(profile.extra or {})
    timeout = float(extra.pop("timeout", 30.0))

    async def rerank_api_func(
        *, query: str, documents: list[str], top_n: int | None = None, **_kwargs: Any
    ) -> list[dict[str, Any]]:
        base_url = (profile.base_url or "").rstrip("/")
        if not base_url:
            raise ValueError(f"rerank 配置缺少 base_url: {profile.name}")
        payload = {"model": profile.model, "query": query, "documents": documents, "top_n": top_n}
        headers = {"Authorization": f"Bearer {profile.api_key}"} if profile.api_key else {}
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(f"{base_url}/rerank", json=payload, headers=headers)
            response.raise_for_status()
            body = response.json()
        results = body.get("results", [])
        return [
            {"index": item["index"], "relevance_score": item.get("relevance_score", 0.0)}
            for item in results
        ]

    logger.info("rerank provider=%s model=%s 就绪", profile.provider, profile.model)
    return rerank_api_func

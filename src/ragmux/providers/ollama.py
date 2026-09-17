"""Ollama provider：本地/远程 Ollama 服务的 LLM 与 embedding 接入。

复用 LightRAG 自带的 ``ollama_model_complete`` / ``ollama_embed``：
- 实例内调用时 LightRAG 会注入 ``hashing_kv``（llm_response_cache），
  ``ollama_model_complete`` 据此启用 LLM 响应缓存并读取模型名；
- 连通性测试等独立调用没有 hashing_kv，走直连 chat 的精简路径。
"""

from __future__ import annotations

from typing import Any

import httpx
import numpy as np
import ollama as ollama_sdk
from lightrag.llm.ollama import ensure_think_supported, ollama_embed, ollama_model_complete
from lightrag.utils import EmbeddingFunc, logger

from ragmux.registry.models import KBProfile


def _extra(profile: KBProfile) -> dict[str, Any]:
    return dict(profile.extra or {})


async def _direct_chat(
    profile: KBProfile, options: dict[str, Any], timeout: float, prompt: str
) -> str:
    """不经 LightRAG 缓存的直连 chat（仅用于连通性测试等独立调用）。"""
    client = ollama_sdk.AsyncClient(
        host=profile.base_url,
        timeout=timeout,
        headers={"Authorization": f"Bearer {profile.api_key}"} if profile.api_key else {},
    )
    response = await client.chat(
        model=profile.model,
        messages=[{"role": "user", "content": prompt}],
        stream=False,
        options=options or None,
    )
    message = response.get("message", {}) if isinstance(response, dict) else response.message
    content = (message or {}).get("content", "") if isinstance(message, dict) else message.content
    return content or ""


def build_llm_func(profile: KBProfile):
    """构建 LightRAG ``llm_model_func``（ollama provider）。

    LightRAG 的角色包装层会向 kwargs 注入 ``hashing_kv``（即该实例的
    llm_response_cache），据此走缓存路径；独立调用（无 hashing_kv）直连。
    """
    extra = _extra(profile)
    options = dict(extra.get("options") or {})
    ensure_think_supported(options, context=f"模型配置 {profile.name}")
    timeout = float(extra.get("timeout", 300))

    async def llm_func(
        prompt: str,
        system_prompt: str | None = None,
        history_messages: list | None = None,
        **kwargs: Any,
    ) -> str:
        if kwargs.get("hashing_kv") is None:
            return await _direct_chat(profile, options, timeout, prompt)
        return await ollama_model_complete(
            prompt,
            system_prompt=system_prompt,
            history_messages=history_messages or [],
            host=profile.base_url,
            api_key=profile.api_key,
            options=options,
            timeout=timeout,
            **kwargs,
        )

    logger.info("ollama LLM provider 就绪: model=%s host=%s", profile.model, profile.base_url)
    return llm_func


def build_embedding_func(profile: KBProfile) -> EmbeddingFunc:
    """构建 LightRAG ``embedding_func``（ollama provider）。

    维度必须与模型原生输出一致（如 bge-m3=1024、nomic-embed-text=768）。
    """
    if profile.dimension is None:
        raise ValueError(f"embedding 配置缺少 dimension: {profile.name}")
    extra = _extra(profile)
    options = dict(extra.get("options") or {})
    timeout = float(extra.get("timeout", 120))
    # ollama_embed 对外是被包装的 EmbeddingFunc，取内层原函数并预绑连接参数
    inner = ollama_embed.func if isinstance(ollama_embed, EmbeddingFunc) else ollama_embed
    max_token_size = extra.get("max_token_size")
    query_prefix = extra.get("query_prefix")
    document_prefix = extra.get("document_prefix")

    async def embed_func(texts: list[str], **kwargs: Any) -> np.ndarray:
        return await inner(
            texts,
            embed_model=profile.model,
            host=profile.base_url,
            api_key=profile.api_key,
            options=options,
            timeout=timeout,
            max_token_size=max_token_size,
            query_prefix=query_prefix,
            document_prefix=document_prefix,
            **kwargs,
        )

    logger.info(
        "ollama embedding provider 就绪: model=%s dim=%s host=%s",
        profile.model,
        profile.dimension,
        profile.base_url,
    )
    return EmbeddingFunc(
        embedding_dim=profile.dimension,
        max_token_size=max_token_size,
        model_name=profile.model,
        func=embed_func,
    )


async def list_ollama_models(base_url: str, timeout: float = 5.0) -> list[dict[str, Any]]:
    """查询 Ollama 服务已安装的模型列表（GET {host}/api/tags）。"""
    base = (base_url or "").rstrip("/")
    if not base:
        raise ValueError("缺少 Ollama host（base_url）")
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(f"{base}/api/tags")
        response.raise_for_status()
        body = response.json()
    return [
        {"name": item.get("name") or item.get("model"), "size": item.get("size")}
        for item in body.get("models", [])
    ]

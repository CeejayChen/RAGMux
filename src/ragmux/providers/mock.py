"""mock provider：确定性、离线的 LLM / embedding / rerank 桩实现。

用途：自动化测试与无 API key 的界面演示。输出完全由输入决定，不访问网络。
mock LLM 依据提示词特征返回 LightRAG 期望格式的内容（实体抽取 / 关键词提取 /
普通问答），使图谱与检索链路在离线环境下也能端到端跑通。
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

import numpy as np

# 实体抽取输出：固定的确定性实体，保证 mock 库的图谱非空
_MOCK_ENTITY_OUTPUT = (
    "(mock_entity<|>category<|>A deterministic entity produced by the RAGMux mock provider "
    "for offline testing.<|>mock,test,offline)\n"
    "(mock_concept<|>category<|>A deterministic companion concept used to form a mock "
    "relation in offline tests.<|>concept,mock)\n"
    "(mock_entity<|>related<|>mock_concept<|>mock_entity and mock_concept are linked for "
    "offline graph testing.<|>mock,relation,test)"
)

# 关键词提取输出：包含 mock 实体名，保证 mix/local/global 模式能命中图谱
_MOCK_KEYWORD_OUTPUT = '("mock_entity,mock_concept,mock", "mock_entity,mock_concept,test")'

_MOCK_ANSWER = (
    "这是 RAGMux mock provider 生成的离线回答。当前知识库使用 mock 模型配置，"
    "仅用于验证链路与界面，不产生真实的语义理解。"
)


def _looks_like_entity_extraction(prompt: str) -> bool:
    markers = ("-Entity-", "entity_types", "extract entities", "实体抽取", "##### entity_types")
    lowered = prompt.lower()
    return any(marker.lower() in lowered for marker in markers)


def _looks_like_keyword_extraction(prompt: str) -> bool:
    return "high_level_keywords" in prompt or "keyword extraction" in prompt.lower()


def _looks_like_gleaning(prompt: str) -> bool:
    return "MANY entities were missed" in prompt


async def mock_llm_func(
    prompt: str,
    system_prompt: str | None = None,
    history_messages: list[dict[str, Any]] | None = None,
    **_kwargs: Any,
) -> str:
    """按提示词特征返回确定性输出的桩 LLM。"""
    if _looks_like_gleaning(prompt):
        return "(none)"
    if _looks_like_entity_extraction(prompt):
        return _MOCK_ENTITY_OUTPUT
    if _looks_like_keyword_extraction(prompt):
        return _MOCK_KEYWORD_OUTPUT
    return _MOCK_ANSWER


def make_mock_embed_func(dimension: int):
    """构造确定性哈希 embedding 函数：词级 MD5 哈希落桶 + L2 归一化。"""

    async def embed_func(texts: list[str]) -> np.ndarray:
        vectors = np.zeros((len(texts), dimension), dtype=np.float32)
        for row, text in enumerate(texts):
            for token in re.findall(r"[\w]+", text.lower()):
                digest = hashlib.md5(token.encode("utf-8")).hexdigest()
                index = int(digest, 16) % dimension
                vectors[row, index] += 1.0
            norm = float(np.linalg.norm(vectors[row]))
            if norm > 0:
                vectors[row] /= norm
        return vectors

    return embed_func


async def mock_rerank_func(
    *,
    query: str,
    documents: list[str],
    top_n: int | None = None,
    **_kwargs: Any,
) -> list[dict[str, Any]]:
    """按词面重合度排序的桩 rerank（返回 LightRAG 期望的 index 格式）。"""

    def overlap(doc: str) -> float:
        query_tokens = set(re.findall(r"[\w]+", query.lower()))
        doc_tokens = set(re.findall(r"[\w]+", doc.lower()))
        if not query_tokens:
            return 0.0
        return len(query_tokens & doc_tokens) / len(query_tokens)

    scores = [overlap(doc) for doc in documents]
    order = sorted(range(len(documents)), key=lambda i: scores[i], reverse=True)
    limit = top_n if top_n is not None else len(documents)
    return [{"index": i, "relevance_score": scores[i]} for i in order[:limit]]

"""查询路由：单库查询与跨库查询。

跨库查询沿用 WeKnora 式硬约束：仅允许 embedding 配置相同的知识库一起查询，
不同向量空间的分数不可比，直接拒绝。
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request
from lightrag import QueryParam

from ragmux.api.deps import get_manager, get_store
from ragmux.api.schemas import MultiKBQueryRequest, QueryRequest
from ragmux.manager.instances import InstanceManager
from ragmux.registry.schemas import KBConfig
from ragmux.registry.store import RegistryStore

router = APIRouter(tags=["query"])


def _build_query_param(config: KBConfig, body: QueryRequest | MultiKBQueryRequest) -> QueryParam:
    """请求参数叠加知识库默认值（显式传入者优先）。"""
    defaults = config.query
    return QueryParam(
        mode=body.mode or defaults.mode,
        only_need_context=defaults.only_need_context
        if body.only_need_context is None
        else body.only_need_context,
        response_type=body.response_type or defaults.response_type,
        top_k=body.top_k or defaults.top_k,
        chunk_top_k=body.chunk_top_k or defaults.chunk_top_k,
    )


@router.post("/kbs/{kb_id}/query")
async def query_kb(kb_id: str, body: QueryRequest, request: Request) -> dict:
    store: RegistryStore = get_store(request)
    manager: InstanceManager = get_manager(request)
    bundle = await store.get_kb_bundle(kb_id)
    param = _build_query_param(bundle.kb_config, body)
    async with manager.lease(bundle) as instance:
        response = await instance.aquery(body.query, param=param)
    return {"kb_id": kb_id, "query": body.query, "mode": param.mode, "response": response}


@router.post("/query")
async def query_multi_kb(body: MultiKBQueryRequest, request: Request) -> dict:
    """跨库查询：并发查询多个知识库，返回逐库结果。

    约束：所有库必须绑定相同的 embedding 配置（同向量空间）。
    """
    store: RegistryStore = get_store(request)
    manager: InstanceManager = get_manager(request)
    if len(set(body.kb_ids)) != len(body.kb_ids):
        raise HTTPException(status_code=422, detail="kb_ids 存在重复")

    bundles = [await store.get_kb_bundle(kb_id) for kb_id in body.kb_ids]
    embedding_ids = {bundle.embedding.id for bundle in bundles}
    if len(embedding_ids) > 1:
        detail = "、".join(f"{b.kb.name}({b.embedding.name})" for b in bundles)
        raise HTTPException(
            status_code=400, detail=f"跨库查询要求所有知识库使用相同 embedding 配置，当前: {detail}"
        )

    async def _one(bundle) -> dict:
        try:
            param = _build_query_param(bundle.kb_config, body)
            async with manager.lease(bundle) as instance:
                response = await instance.aquery(body.query, param=param)
            return {
                "kb_id": bundle.kb_id,
                "kb_name": bundle.kb.name,
                "ok": True,
                "response": response,
            }
        except Exception as exc:  # noqa: BLE001 — 跨库查询逐库隔离错误
            return {
                "kb_id": bundle.kb_id,
                "kb_name": bundle.kb.name,
                "ok": False,
                "error": str(exc),
            }

    results = await asyncio.gather(*(_one(bundle) for bundle in bundles))
    return {"query": body.query, "results": list(results)}

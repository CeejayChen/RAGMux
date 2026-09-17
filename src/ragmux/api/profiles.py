"""模型配置路由：LLM / Embedding / Rerank 配置的运行时管理。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ragmux.api.deps import get_manager, get_store
from ragmux.api.schemas import ProfileCreateRequest, ProfileUpdateRequest
from ragmux.manager.instances import InstanceManager
from ragmux.registry.store import RegistryStore

router = APIRouter(prefix="/profiles", tags=["profiles"])

# PATCH 允许修改的字段白名单
_EDITABLE_FIELDS = {"name", "provider", "model", "base_url", "api_key", "dimension", "extra"}


def _serialize(row) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "kind": row.kind,
        "provider": row.provider,
        "model": row.model,
        "base_url": row.base_url,
        "has_api_key": bool(row.api_key),
        "dimension": row.dimension,
        "extra": row.extra,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


@router.get("")
async def list_profiles(request: Request, kind: str | None = None) -> dict:
    store: RegistryStore = get_store(request)
    rows = await store.list_profiles(kind=kind)
    return {"profiles": [_serialize(row) for row in rows]}


@router.post("", status_code=201)
async def create_profile(body: ProfileCreateRequest, request: Request) -> dict:
    store: RegistryStore = get_store(request)
    row = await store.create_profile(
        name=body.name,
        kind=body.kind,
        provider=body.provider,
        model=body.model,
        base_url=body.base_url,
        api_key=body.api_key,
        dimension=body.dimension,
        extra=body.extra,
    )
    return _serialize(row)


@router.patch("/{profile_id}")
async def update_profile(profile_id: str, body: ProfileUpdateRequest, request: Request) -> dict:
    """更新模型配置；引用它的知识库实例会被失效，下次访问按新配置重建。"""
    store: RegistryStore = get_store(request)
    manager: InstanceManager = get_manager(request)
    changes = {key: getattr(body, key) for key in body.model_fields_set if key in _EDITABLE_FIELDS}
    row = await store.update_profile(profile_id, changes)
    for kb_id in await store.kb_ids_referencing_profile(profile_id):
        await manager.invalidate(kb_id)
    return _serialize(row)


@router.delete("/{profile_id}")
async def delete_profile(profile_id: str, request: Request) -> dict:
    store: RegistryStore = get_store(request)
    await store.delete_profile(profile_id)
    return {"deleted": True}


@router.post("/{profile_id}/test")
async def test_profile(profile_id: str, request: Request) -> dict:
    """连通性测试：embedding 试嵌入、llm 试问答、rerank 试排序。"""
    from ragmux.providers import build_embedding_func, build_llm_func, build_rerank_func

    store: RegistryStore = get_store(request)
    profile = await store.get_profile(profile_id)
    try:
        if profile.kind == "embedding":
            func = build_embedding_func(profile)
            vectors = await func(["ping"])
            return {"ok": True, "detail": f"返回维度 {int(vectors.shape[-1])}"}
        if profile.kind == "llm":
            func = build_llm_func(profile)
            answer = await func("Reply with the single word: pong")
            return {"ok": True, "detail": str(answer)[:200]}
        if profile.kind == "rerank":
            func = build_rerank_func(profile)
            results = await func(query="ping", documents=["pong", "ping"], top_n=2)
            return {"ok": True, "detail": f"返回 {len(results)} 条排序结果"}
        raise HTTPException(status_code=422, detail=f"未知模型类型: {profile.kind}")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"连通性测试失败: {exc}") from exc

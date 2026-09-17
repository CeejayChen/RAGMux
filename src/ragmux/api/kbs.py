"""知识库路由：知识库实体的运行时增删改查与实例控制（扁平结构）。"""

from __future__ import annotations

import shutil

from fastapi import APIRouter, Request

from ragmux.api.deps import get_manager, get_settings, get_store
from ragmux.api.schemas import KBCreateRequest, KBUpdateRequest
from ragmux.manager.instances import InstanceManager
from ragmux.registry.schemas import KBConfig
from ragmux.registry.store import RegistryStore

router = APIRouter(prefix="/kbs", tags=["kbs"])


async def _kb_detail(store: RegistryStore, manager: InstanceManager, kb_id: str) -> dict:
    kb = await store.get_kb(kb_id)
    config = KBConfig(**kb.config)
    profiles = {
        "llm": None,
        "embedding": None,
        "rerank": None,
    }
    for kind, field_id in (
        ("llm", kb.llm_profile_id),
        ("embedding", kb.embedding_profile_id),
        ("rerank", kb.rerank_profile_id),
    ):
        if field_id:
            profile = await store.get_profile(field_id)
            profiles[kind] = {
                "id": profile.id,
                "name": profile.name,
                "provider": profile.provider,
                "model": profile.model,
            }
        elif kind == "llm":
            # 与工厂的回退行为一致：未绑定 LLM 时实例使用内置 mock LLM
            profiles[kind] = {
                "id": None,
                "name": None,
                "provider": "mock",
                "model": "ragmux-mock-llm(未绑定)",
            }
    stats = manager.stats()
    return {
        "id": kb.id,
        "name": kb.name,
        "description": kb.description,
        "enabled": kb.enabled,
        "config": config.model_dump(),
        "profiles": profiles,
        "created_at": kb.created_at,
        "updated_at": kb.updated_at,
        "instance_loaded": kb.id in stats.loaded_ids,
    }


@router.get("")
async def list_kbs(request: Request) -> dict:
    store: RegistryStore = get_store(request)
    rows = await store.list_kbs()
    manager: InstanceManager = get_manager(request)
    loaded = set(manager.stats().loaded_ids)
    return {
        "kbs": [
            {
                "id": row.id,
                "name": row.name,
                "description": row.description,
                "enabled": row.enabled,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
                "instance_loaded": row.id in loaded,
            }
            for row in rows
        ]
    }


@router.post("", status_code=201)
async def create_kb(body: KBCreateRequest, request: Request) -> dict:
    store: RegistryStore = get_store(request)
    kb = await store.create_kb(
        name=body.name,
        embedding_profile_id=body.embedding_profile_id,
        description=body.description,
        llm_profile_id=body.llm_profile_id,
        rerank_profile_id=body.rerank_profile_id,
        config=body.config,
    )
    return await _kb_detail(store, get_manager(request), kb.id)


@router.get("/{kb_id}")
async def get_kb(kb_id: str, request: Request) -> dict:
    store: RegistryStore = get_store(request)
    return await _kb_detail(store, get_manager(request), kb_id)


@router.patch("/{kb_id}")
async def update_kb(kb_id: str, body: KBUpdateRequest, request: Request) -> dict:
    """更新知识库。显式提供的字段才生效；构建相关字段（config/模型绑定）变更
    会失效已加载实例，下次访问按新配置重建。"""
    store: RegistryStore = get_store(request)
    manager: InstanceManager = get_manager(request)
    kb = await store.get_kb(kb_id)
    old_signature = (kb.llm_profile_id, kb.embedding_profile_id, kb.rerank_profile_id, kb.config)

    changes = {key: getattr(body, key) for key in body.model_fields_set}
    await store.update_kb(kb_id, changes)

    updated = await store.get_kb(kb_id)
    new_signature = (
        updated.llm_profile_id,
        updated.embedding_profile_id,
        updated.rerank_profile_id,
        updated.config,
    )
    if old_signature != new_signature:
        await manager.invalidate(kb_id)
    return await _kb_detail(store, manager, kb_id)


@router.delete("/{kb_id}")
async def delete_kb(kb_id: str, request: Request, remove_data: bool = True) -> dict:
    """删除知识库：先失效实例，再删注册表行，最后清理数据目录。"""
    store: RegistryStore = get_store(request)
    manager: InstanceManager = get_manager(request)
    settings = get_settings(request)
    kb = await store.get_kb(kb_id)  # 先取 name 供响应，随后删行
    await manager.invalidate(kb_id)
    await store.delete_kb_row(kb_id)
    if remove_data:
        shutil.rmtree(settings.kb_data_root / kb_id, ignore_errors=True)
    return {"deleted": True, "id": kb_id, "name": kb.name, "data_removed": remove_data}


@router.post("/{kb_id}/invalidate")
async def invalidate_kb(kb_id: str, request: Request) -> dict:
    """手动驱逐实例（配置热更新排查 / 释放内存用）。"""
    store: RegistryStore = get_store(request)
    manager: InstanceManager = get_manager(request)
    await store.get_kb(kb_id)
    evicted = await manager.invalidate(kb_id)
    return {"invalidated": evicted}


@router.get("/{kb_id}/stats")
async def kb_stats(kb_id: str, request: Request) -> dict:
    """知识库运行统计：文档状态计数与 pipeline 状态。"""
    from lightrag.kg.shared_storage import get_namespace_data

    store: RegistryStore = get_store(request)
    manager: InstanceManager = get_manager(request)
    bundle = await store.get_kb_bundle(kb_id)
    async with manager.lease(bundle) as instance:
        status_counts = await instance.doc_status.get_all_status_counts()
        pipeline_status = dict(await get_namespace_data("pipeline_status", workspace=kb_id))
    # pipeline_status 中包含锁对象与历史列表等不可序列化内容，裁剪为标量字段
    safe_pipeline = {
        key: value
        for key, value in pipeline_status.items()
        if isinstance(value, (str, int, float, bool)) and key != "history_messages"
    }
    return {
        "kb_id": kb_id,
        "status_counts": status_counts,
        "pipeline": safe_pipeline,
        "instance_loaded": True,
    }

"""知识库内文档管理路由：导入、列表、详情、删除。

导入采用 LightRAG 服务端同款两段式：先 enqueue（落盘 PENDING 状态）即返回，
后台任务再驱动 pipeline 处理；后台任务独立持有 lease，实例被驱逐时也能
按注册表配置重建后继续处理（PENDING 状态已持久化）。
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request, UploadFile
from lightrag.utils import logger

from ragmux.api.deps import get_manager, get_store, parse_status_filter
from ragmux.api.schemas import DocumentTextRequest
from ragmux.manager.instances import InstanceManager
from ragmux.registry.store import KBBundle, RegistryStore

router = APIRouter(prefix="/kbs/{kb_id}/documents", tags=["documents"])

# v1 仅支持纯文本类格式（PDF/Office 需 LightRAG 解析引擎，见 docs/development.md）
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def _serialize_status(doc_id: str, status) -> dict:
    """兼容 dict 与 DocProcessingStatus 两种返回形态（不同存储后端实现有差异）。"""

    def field(name: str):
        if isinstance(status, dict):
            return status.get(name)
        return getattr(status, name, None)

    raw_status = field("status")
    return {
        "id": doc_id,
        "status": raw_status.value if hasattr(raw_status, "value") else str(raw_status),
        "file_path": field("file_path"),
        "content_summary": field("content_summary"),
        "content_length": field("content_length"),
        "chunks_count": field("chunks_count"),
        "error_msg": field("error_msg"),
        "created_at": field("created_at"),
        "updated_at": field("updated_at"),
        "track_id": field("track_id"),
    }


async def _drain(manager: InstanceManager, bundle: KBBundle) -> None:
    """后台驱动 pipeline；独立 lease 保证实例存活到处理结束。"""
    try:
        async with manager.lease(bundle) as instance:
            await instance.apipeline_process_enqueue_documents()
    except Exception:  # noqa: BLE001 — 后台任务隔离，任何失败都不能影响主请求
        logger.exception("后台文档处理失败: kb=%s", bundle.kb_id)


@router.post("/text", status_code=202)
async def insert_text(kb_id: str, body: DocumentTextRequest, request: Request) -> dict:
    """文本导入。入队即返回 track_id，处理进度通过文档列表轮询。"""
    store: RegistryStore = get_store(request)
    manager: InstanceManager = get_manager(request)
    bundle = await store.get_kb_bundle(kb_id)
    async with manager.lease(bundle) as instance:
        track_id = await instance.apipeline_enqueue_documents(
            body.texts, file_paths=body.file_paths if body.file_paths else None
        )
    asyncio.create_task(_drain(manager, bundle))
    return {"track_id": track_id, "queued": len(body.texts)}


@router.post("/file", status_code=202)
async def upload_file(kb_id: str, request: Request, file: UploadFile) -> dict:
    """纯文本类文件导入（.txt/.md/.markdown/.json/.csv/.html 等，UTF-8 解码）。"""
    store: RegistryStore = get_store(request)
    manager: InstanceManager = get_manager(request)
    bundle = await store.get_kb_bundle(kb_id)

    filename = file.filename or "unnamed.txt"
    payload = await file.read()
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件超过 20MB 上限")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=415, detail=f"仅支持 UTF-8 文本文件（当前版本不含 PDF/Office 解析）: {exc}"
        ) from exc
    if not text.strip():
        raise HTTPException(status_code=422, detail="文件内容为空")

    async with manager.lease(bundle) as instance:
        track_id = await instance.apipeline_enqueue_documents([text], file_paths=[filename])
    asyncio.create_task(_drain(manager, bundle))
    return {"track_id": track_id, "queued": 1, "file_path": filename}


@router.get("")
async def list_documents(
    kb_id: str,
    request: Request,
    page: int = 1,
    page_size: int = 25,
    status_filter: str | None = None,
    sort_field: str = "updated_at",
    sort_direction: str = "desc",
) -> dict:
    """分页列出文档及其处理状态。page_size 实际范围 10-200（LightRAG 约定）。"""
    store: RegistryStore = get_store(request)
    manager: InstanceManager = get_manager(request)
    bundle = await store.get_kb_bundle(kb_id)
    doc_status_enum = parse_status_filter(status_filter)
    async with manager.lease(bundle) as instance:
        rows, total = await instance.doc_status.get_docs_paginated(
            status_filter=doc_status_enum,
            page=max(page, 1),
            page_size=page_size,
            sort_field=sort_field,
            sort_direction=sort_direction,
        )
        status_counts = await instance.doc_status.get_all_status_counts()
    return {
        "documents": [_serialize_status(doc_id, status) for doc_id, status in rows],
        "pagination": {"page": page, "page_size": page_size, "total_count": total},
        "status_counts": status_counts,
    }


@router.get("/{doc_id}")
async def get_document(kb_id: str, doc_id: str, request: Request) -> dict:
    """文档详情：处理状态 + 原文内容。"""
    store: RegistryStore = get_store(request)
    manager: InstanceManager = get_manager(request)
    bundle = await store.get_kb_bundle(kb_id)
    async with manager.lease(bundle) as instance:
        statuses = await instance.aget_docs_by_ids(doc_id)
        if doc_id not in statuses:
            raise HTTPException(status_code=404, detail=f"文档不存在: {doc_id}")
        stored = await instance.full_docs.get_by_id(doc_id)
    status = statuses[doc_id]
    detail = _serialize_status(doc_id, status)
    # full_docs 存储形如 {"content": ..., "chunk_options": ...}；老数据可能直接是字符串
    if isinstance(stored, dict):
        detail["content"] = stored.get("content")
    elif isinstance(stored, str):
        detail["content"] = stored
    else:
        detail["content"] = None
    return detail


@router.delete("/{doc_id}")
async def delete_document(
    kb_id: str, doc_id: str, request: Request, delete_llm_cache: bool = True
) -> dict:
    """删除文档及其派生数据（chunks、图谱元素按需重建）。"""
    store: RegistryStore = get_store(request)
    manager: InstanceManager = get_manager(request)
    bundle = await store.get_kb_bundle(kb_id)
    async with manager.lease(bundle) as instance:
        result = await instance.adelete_by_doc_id(doc_id, delete_llm_cache=delete_llm_cache)
    body = {
        "status": result.status,
        "doc_id": result.doc_id,
        "message": result.message,
    }
    if result.status == "not_found":
        raise HTTPException(status_code=404, detail=body)
    if result.status == "not_allowed":
        raise HTTPException(status_code=409, detail=body)
    if result.status == "fail":
        raise HTTPException(status_code=500, detail=body)
    return body

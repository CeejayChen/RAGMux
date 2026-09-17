"""系统级路由：健康检查与运行概览。"""

from __future__ import annotations

from fastapi import APIRouter, Request

import ragmux
from ragmux.api.deps import get_manager, get_store

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": ragmux.__version__}


@router.get("/system/overview")
async def overview(request: Request) -> dict:
    """注册表计数 + 实例驻留状态，供管理界面概览页使用。"""
    store = get_store(request)
    manager = get_manager(request)
    stats = manager.stats()
    return {
        "version": ragmux.__version__,
        "registry": await store.overview_counts(),
        "instances": {
            "loaded": stats.loaded,
            "capacity": stats.capacity,
            "loaded_ids": stats.loaded_ids,
            "active_ids": stats.active_ids,
        },
    }

"""图谱浏览路由：标签列表与子图查询（供前端可视化）。"""

from __future__ import annotations

from fastapi import APIRouter, Request

from ragmux.api.deps import get_manager, get_store
from ragmux.manager.instances import InstanceManager
from ragmux.registry.store import RegistryStore

router = APIRouter(prefix="/kbs/{kb_id}/graph", tags=["graph"])


@router.get("/labels")
async def graph_labels(kb_id: str, request: Request) -> dict:
    store: RegistryStore = get_store(request)
    manager: InstanceManager = get_manager(request)
    bundle = await store.get_kb_bundle(kb_id)
    async with manager.lease(bundle) as instance:
        labels = await instance.get_graph_labels()
    return {"labels": labels or []}


@router.get("")
async def subgraph(
    kb_id: str, request: Request, label: str = "*", max_depth: int = 3, max_nodes: int = 100
) -> dict:
    """按标签取子图。label='*' 表示从随机节点展开（LightRAG 约定）。"""
    store: RegistryStore = get_store(request)
    manager: InstanceManager = get_manager(request)
    bundle = await store.get_kb_bundle(kb_id)
    async with manager.lease(bundle) as instance:
        graph = await instance.get_knowledge_graph(
            node_label=label, max_depth=max_depth, max_nodes=max_nodes
        )
    return graph.model_dump()

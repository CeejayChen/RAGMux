"""API 层：FastAPI 路由与依赖。全部业务路由挂 /api 前缀。"""

from fastapi import APIRouter

from ragmux.api import documents, graph, kbs, profiles, providers, query, system


def build_api_router() -> APIRouter:
    """装配全部业务子路由。"""
    router = APIRouter(prefix="/api")
    router.include_router(system.router)
    router.include_router(providers.router)
    router.include_router(profiles.router)
    router.include_router(kbs.router)
    router.include_router(documents.router)
    router.include_router(query.router)
    router.include_router(graph.router)
    return router


__all__ = ["build_api_router"]

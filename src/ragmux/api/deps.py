"""API 公共依赖与领域错误映射。"""

from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from lightrag.base import DocStatus

from ragmux.config import Settings
from ragmux.manager.instances import InstanceBuildError, InstanceManager
from ragmux.registry.store import ConflictError, NotFoundError, RegistryStore


def get_store(request: Request) -> RegistryStore:
    return request.app.state.store


def get_manager(request: Request) -> InstanceManager:
    return request.app.state.manager


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def map_domain_errors(app) -> None:
    """把领域异常映射为 HTTP 语义（应用创建时注册一次）。"""

    @app.exception_handler(NotFoundError)
    async def _not_found(_request: Request, exc: NotFoundError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ConflictError)
    async def _conflict(_request: Request, exc: ConflictError):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(InstanceBuildError)
    async def _build_error(_request: Request, exc: InstanceBuildError):
        return JSONResponse(status_code=503, content={"detail": str(exc)})


DOC_STATUS_VALUES = {status.value for status in DocStatus}


def parse_status_filter(value: str | None) -> DocStatus | None:
    """把查询参数解析为 DocStatus；非法值抛 422。"""
    if value is None or value == "":
        return None
    if value not in DOC_STATUS_VALUES:
        raise HTTPException(
            status_code=422,
            detail=f"非法的文档状态过滤值: {value}，可选 {sorted(DOC_STATUS_VALUES)}",
        )
    return DocStatus(value)

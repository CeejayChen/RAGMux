"""RAGMux 服务入口：单进程 FastAPI 应用（API + 管理界面静态托管）。

启动：``uv run uvicorn ragmux.main:app --host 127.0.0.1 --port 9700``
生产模式托管 ``web/dist`` 构建产物（SPA fallback 到 index.html）；
开发模式前端由 Vite dev server 提供（/api 代理到本服务）。
"""

from __future__ import annotations

import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from ragmux.api import build_api_router
from ragmux.api.deps import map_domain_errors
from ragmux.config import Settings
from ragmux.config import settings as default_settings
from ragmux.manager.instances import InstanceFactory, InstanceManager
from ragmux.registry.store import RegistryStore


def create_app(app_settings: Settings | None = None) -> FastAPI:
    """应用工厂（测试注入临时数据目录时使用）。"""
    cfg = app_settings or default_settings

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        cfg.data_dir.mkdir(parents=True, exist_ok=True)
        store = await RegistryStore.create(cfg.registry_db_path)
        manager = InstanceManager(
            factory=InstanceFactory(cfg.kb_data_root), max_instances=cfg.max_loaded_instances
        )
        app.state.store = store
        app.state.manager = manager
        app.state.settings = cfg
        yield
        await manager.close_all()
        await store.dispose()

    app = FastAPI(
        title="RAGMux",
        description="基于 LightRAG 的单实例多知识库管理层",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    map_domain_errors(app)
    app.include_router(build_api_router())

    _mount_static(app, cfg)
    return app


def _mount_static(app: FastAPI, cfg: Settings) -> None:
    """托管前端构建产物。目录不存在时仅提供 API 与提示页。"""
    static_dir = cfg.resolve_static_dir()

    if not static_dir.is_dir():

        @app.get("/", include_in_schema=False)
        async def _no_ui() -> JSONResponse:
            return JSONResponse(
                {
                    "name": "RAGMux",
                    "hint": "管理界面未构建：在 web/ 目录执行 pnpm install && pnpm build 后重启服务",
                    "api_docs": "/docs",
                }
            )

        return

    @app.get("/{full_path:path}", include_in_schema=False)
    async def _spa(full_path: str):
        if full_path.startswith("api/") or full_path == "api":
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = (static_dir / full_path).resolve()
        # 防目录穿越：解析后必须仍位于静态目录内
        if full_path and candidate.is_file() and str(candidate).startswith(str(static_dir)):
            return FileResponse(candidate)
        index = static_dir / "index.html"
        if index.is_file():
            # 入口文件禁缓存：前端更新后浏览器重载即可拿到新资源清单
            return FileResponse(index, headers={"Cache-Control": "no-cache"})
        raise HTTPException(status_code=404, detail="Not Found")


def copy_frontend_dist(dist_dir: Path, target_dir: Path) -> None:
    """把前端构建产物复制进包内 static 目录（可选的打包方式）。"""
    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.copytree(dist_dir, target_dir)


app = create_app()

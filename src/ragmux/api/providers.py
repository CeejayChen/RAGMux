"""模型服务目录：查询外部模型服务上可用的模型列表。

用于管理界面创建模型配置时直接拉取远端模型清单（当前支持 Ollama）。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ragmux.providers.ollama import list_ollama_models

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("/ollama/models")
async def ollama_models(base_url: str = Query(alias="base_url")) -> dict:
    """拉取 Ollama 服务已安装的模型（GET {host}/api/tags）。"""
    try:
        models = await list_ollama_models(base_url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"无法连接 Ollama 服务: {exc}") from exc
    return {"models": models}

"""pytest 共享夹具：临时数据目录 + mock 模型配置 + 应用客户端。

测试零外部依赖：一律使用 mock provider（确定性 LLM/embedding），
注册表使用临时目录下的独立 SQLite 文件。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from ragmux.config import Settings
from ragmux.main import create_app


@pytest.fixture
async def app_client(tmp_path: Path):
    """带临时数据目录的应用客户端（lifespan 已进入）。"""
    settings = Settings(
        data_dir=tmp_path / "data",
        static_dir=tmp_path / "no-static",
        max_loaded_instances=4,
        cors_origins=[],
    )
    app = create_app(settings)
    transport = ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=transport, base_url="http://test") as client,
    ):
        yield client


@pytest.fixture
async def mock_profiles(app_client: AsyncClient) -> dict[str, str]:
    """创建 mock LLM 与 embedding 配置，返回 {kind: profile_id}。"""
    ids: dict[str, str] = {}
    for payload in [
        {"name": "mock-llm", "kind": "llm", "provider": "mock", "model": "mock-llm-v1"},
        {
            "name": "mock-embed",
            "kind": "embedding",
            "provider": "mock",
            "model": "mock-embed-v1",
            "dimension": 64,
        },
    ]:
        response = await app_client.post("/api/profiles", json=payload)
        assert response.status_code == 201, response.text
        ids[payload["kind"]] = response.json()["id"]
    return ids


@pytest.fixture
async def demo_kb(app_client: AsyncClient, mock_profiles: dict[str, str]) -> dict:
    """创建一个 mock 知识库，返回完整响应体。"""
    response = await app_client.post(
        "/api/kbs",
        json={
            "name": "演示知识库",
            "embedding_profile_id": mock_profiles["embedding"],
            "llm_profile_id": mock_profiles["llm"],
            "description": "pytest 自动创建的 mock 知识库",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()

"""API 集成测试：mock provider 全链路（配置 → 建库 → 导入 → 查询 → 图谱 → 删除）+ Ollama 接入。"""

from __future__ import annotations

import asyncio

from httpx import AsyncClient


async def test_profile_api_and_test_endpoint(app_client: AsyncClient):
    response = await app_client.post(
        "/api/profiles",
        json={
            "name": "m-embed",
            "kind": "embedding",
            "provider": "mock",
            "model": "e",
            "dimension": 32,
        },
    )
    assert response.status_code == 201
    profile_id = response.json()["id"]
    assert response.json()["has_api_key"] is False

    test_result = await app_client.post(f"/api/profiles/{profile_id}/test")
    assert test_result.status_code == 200, test_result.text
    assert test_result.json()["ok"] is True

    assert (await app_client.get("/api/profiles", params={"kind": "embedding"})).json()["profiles"]


async def test_ollama_profile_and_catalog_endpoint(app_client: AsyncClient):
    """ollama 配置可创建；模型目录端点对不可达服务返回 502；连通性测试同样 502。"""
    response = await app_client.post(
        "/api/profiles",
        json={
            "name": "local-ollama",
            "kind": "llm",
            "provider": "ollama",
            "model": "qwen3:8b",
            "base_url": "http://127.0.0.1:9",  # 不可达端口
            "extra": {"timeout": 1},
        },
    )
    assert response.status_code == 201, response.text
    profile_id = response.json()["id"]

    catalog = await app_client.get(
        "/api/providers/ollama/models", params={"base_url": "http://127.0.0.1:9"}
    )
    assert catalog.status_code == 502
    missing = await app_client.get("/api/providers/ollama/models")
    assert missing.status_code == 422

    test_result = await app_client.post(f"/api/profiles/{profile_id}/test")
    assert test_result.status_code == 502, test_result.text


async def test_end_to_end_flow(app_client: AsyncClient, mock_profiles: dict[str, str]):
    """核心链路：建库 → 文本导入 → 轮询状态 → 查询 → 图谱 → 删除。"""
    kb = (
        await app_client.post(
            "/api/kbs",
            json={
                "name": "e2e-kb",
                "embedding_profile_id": mock_profiles["embedding"],
                "llm_profile_id": mock_profiles["llm"],
                "description": "pytest 自动创建的 mock 知识库",
            },
        )
    ).json()
    kb_id = kb["id"]

    # 导入文本（mock 管线应很快完成）
    response = await app_client.post(
        f"/api/kbs/{kb_id}/documents/text",
        json={
            "texts": [
                "RAGMux 是一个多知识库管理服务。它管理 LightRAG 实例。",
                "第二个文档：知识库支持运行时增删改查。",
            ]
        },
    )
    assert response.status_code == 202, response.text

    # 轮询直到处理完成
    docs = {}
    for _ in range(60):
        listing = (await app_client.get(f"/api/kbs/{kb_id}/documents")).json()
        docs = {d["id"]: d for d in listing["documents"]}
        if docs and all(d["status"] in ("processed", "failed") for d in docs.values()):
            break
        await asyncio.sleep(0.3)
    assert docs, "文档列表为空"
    assert all(d["status"] == "processed" for d in docs.values()), docs
    assert listing["status_counts"].get("processed") == 2

    # 文档详情（取含 RAGMux 的那份）
    detail = None
    for candidate_id in docs:
        candidate = (await app_client.get(f"/api/kbs/{kb_id}/documents/{candidate_id}")).json()
        if candidate.get("content") and "RAGMux" in candidate["content"]:
            detail = candidate
            break
    assert detail is not None, "未找到包含 RAGMux 的文档"

    # 查询：naive 模式走纯向量召回（mock embedding 词面哈希，重叠词必然命中）
    response = await app_client.post(
        f"/api/kbs/{kb_id}/query",
        json={"query": "RAGMux 是一个多知识库管理服务", "mode": "naive"},
    )
    assert response.status_code == 200, response.text
    assert "mock" in response.json()["response"], response.json()

    # mix 模式走关键词+图谱链路，仅验证接口可用
    response = await app_client.post(f"/api/kbs/{kb_id}/query", json={"query": "mock_entity"})
    assert response.status_code == 200, response.text

    # 图谱（mock 实体抽取应产出节点）
    labels = (await app_client.get(f"/api/kbs/{kb_id}/graph/labels")).json()["labels"]
    assert len(labels) > 0
    subgraph = (await app_client.get(f"/api/kbs/{kb_id}/graph", params={"label": labels[0]})).json()
    assert len(subgraph["nodes"]) > 0

    # 统计
    stats = (await app_client.get(f"/api/kbs/{kb_id}/stats")).json()
    assert stats["status_counts"]["processed"] == 2

    # 跨库查询：新建第二个库（同 embedding 配置）后一起查
    kb2 = (
        await app_client.post(
            "/api/kbs",
            json={"name": "e2e-kb2", "embedding_profile_id": mock_profiles["embedding"]},
        )
    ).json()
    multi = await app_client.post(
        "/api/query", json={"kb_ids": [kb_id, kb2["id"]], "query": "测试"}
    )
    assert multi.status_code == 200, multi.text
    assert all(r["ok"] for r in multi.json()["results"]), multi.json()

    # 删除库
    assert (await app_client.delete(f"/api/kbs/{kb_id}")).status_code == 200
    remaining = (await app_client.get("/api/kbs")).json()["kbs"]
    assert [row["id"] for row in remaining] == [kb2["id"]]
    assert (await app_client.delete(f"/api/kbs/{kb2['id']}")).status_code == 200
    assert (await app_client.get("/api/kbs")).json()["kbs"] == []


async def test_cross_kb_query_embedding_mismatch(app_client: AsyncClient):
    """不同 embedding 配置的库跨查 → 400。"""
    e1 = (
        await app_client.post(
            "/api/profiles",
            json={
                "name": "e1",
                "kind": "embedding",
                "provider": "mock",
                "model": "m",
                "dimension": 8,
            },
        )
    ).json()
    e2 = (
        await app_client.post(
            "/api/profiles",
            json={
                "name": "e2",
                "kind": "embedding",
                "provider": "mock",
                "model": "m",
                "dimension": 16,
            },
        )
    ).json()
    kb1 = (
        await app_client.post("/api/kbs", json={"name": "k1", "embedding_profile_id": e1["id"]})
    ).json()
    kb2 = (
        await app_client.post("/api/kbs", json={"name": "k2", "embedding_profile_id": e2["id"]})
    ).json()
    response = await app_client.post(
        "/api/query", json={"kb_ids": [kb1["id"], kb2["id"]], "query": "x"}
    )
    assert response.status_code == 400


async def test_kb_config_update_invalidates_instance(
    app_client: AsyncClient, mock_profiles: dict[str, str]
):
    kb = (
        await app_client.post(
            "/api/kbs",
            json={
                "name": "cfg-kb",
                "embedding_profile_id": mock_profiles["embedding"],
                "llm_profile_id": mock_profiles["llm"],
            },
        )
    ).json()
    kb_id = kb["id"]

    # 触发实例加载
    await app_client.post(f"/api/kbs/{kb_id}/documents/text", json={"texts": ["触发加载的内容"]})
    detail = (await app_client.get(f"/api/kbs/{kb_id}")).json()
    assert detail["instance_loaded"] is True

    # 修改构建参数 → 实例失效（后台任务持有时延迟到释放后驱逐，轮询确认）
    response = await app_client.patch(
        f"/api/kbs/{kb_id}", json={"config": {"chunk_token_size": 512}}
    )
    assert response.status_code == 200, response.text
    detail = (await app_client.get(f"/api/kbs/{kb_id}")).json()
    assert detail["config"]["chunk_token_size"] == 512
    for _ in range(40):
        detail = (await app_client.get(f"/api/kbs/{kb_id}")).json()
        if detail["instance_loaded"] is False:
            break
        await asyncio.sleep(0.1)
    assert detail["instance_loaded"] is False

    # 未知存储后端 → 409
    response = await app_client.patch(
        f"/api/kbs/{kb_id}", json={"config": {"storage": {"kv_storage": "NoSuchStorage"}}}
    )
    assert response.status_code == 409


async def test_document_delete(app_client: AsyncClient, mock_profiles: dict[str, str]):
    kb = (
        await app_client.post(
            "/api/kbs",
            json={
                "name": "del-kb",
                "embedding_profile_id": mock_profiles["embedding"],
                "llm_profile_id": mock_profiles["llm"],
            },
        )
    ).json()
    await app_client.post(
        f"/api/kbs/{kb['id']}/documents/text", json={"texts": ["待删除的文档内容"]}
    )
    docs = {}
    for _ in range(60):
        listing = (await app_client.get(f"/api/kbs/{kb['id']}/documents")).json()
        docs = {d["id"]: d for d in listing["documents"]}
        if docs and all(d["status"] in ("processed", "failed") for d in docs.values()):
            break
        await asyncio.sleep(0.3)
    doc_id = next(iter(docs))
    response = await app_client.delete(f"/api/kbs/{kb['id']}/documents/{doc_id}")
    assert response.status_code == 200 and response.json()["status"] == "success"
    assert (await app_client.get(f"/api/kbs/{kb['id']}/documents")).json()["pagination"][
        "total_count"
    ] == 0

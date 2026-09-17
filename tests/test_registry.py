"""注册表（模型配置/知识库）的领域逻辑测试。"""

from __future__ import annotations

import pytest

from ragmux.registry.store import ConflictError, NotFoundError, RegistryStore


@pytest.fixture
async def store(tmp_path) -> RegistryStore:
    return await RegistryStore.create(tmp_path / "registry.db")


async def test_kb_duplicate_name_rejected(store: RegistryStore):
    emb = await store.create_profile(
        name="e", kind="embedding", provider="mock", model="m", dimension=8
    )
    await store.create_kb(name="kb", embedding_profile_id=emb.id)
    with pytest.raises(ConflictError):
        await store.create_kb(name="kb", embedding_profile_id=emb.id)


async def test_kb_flat_create_and_delete(store: RegistryStore):
    emb = await store.create_profile(
        name="e", kind="embedding", provider="mock", model="m", dimension=8
    )
    kb = await store.create_kb(name="kb1", embedding_profile_id=emb.id)
    assert await store.list_kbs() != []
    await store.delete_kb_row(kb.id)
    assert await store.list_kbs() == []
    with pytest.raises(NotFoundError):
        await store.get_kb(kb.id)


async def test_profile_validation(store: RegistryStore):
    with pytest.raises(ConflictError):
        await store.create_profile(
            name="x", kind="embedding", provider="openai", model="m"
        )  # 缺 dimension
    with pytest.raises(ConflictError):
        await store.create_profile(
            name="x", kind="llm", provider="rerank_api", model="m"
        )  # provider 不匹配
    row = await store.create_profile(
        name="ok", kind="embedding", provider="openai", model="m", dimension=128
    )
    assert row.dimension == 128


async def test_ollama_provider_accepted(store: RegistryStore):
    """ollama provider 对 llm/embedding 合法；rerank 不支持。"""
    llm = await store.create_profile(
        name="ollama-llm",
        kind="llm",
        provider="ollama",
        model="qwen3:8b",
        base_url="http://127.0.0.1:11434",
    )
    assert llm.provider == "ollama"
    emb = await store.create_profile(
        name="ollama-emb",
        kind="embedding",
        provider="ollama",
        model="bge-m3",
        base_url="http://127.0.0.1:11434",
        dimension=1024,
    )
    assert emb.dimension == 1024
    with pytest.raises(ConflictError):
        await store.create_profile(name="bad", kind="rerank", provider="ollama", model="x")


async def test_profile_delete_blocked_when_referenced(store: RegistryStore):
    llm = await store.create_profile(name="l", kind="llm", provider="mock", model="m")
    emb = await store.create_profile(
        name="e", kind="embedding", provider="mock", model="m", dimension=8
    )
    await store.create_kb(name="kb", embedding_profile_id=emb.id, llm_profile_id=llm.id)
    with pytest.raises(ConflictError):
        await store.delete_profile(emb.id)
    with pytest.raises(ConflictError):
        await store.delete_profile(llm.id)


async def test_kb_bundle_requires_enabled(store: RegistryStore):
    emb = await store.create_profile(
        name="e", kind="embedding", provider="mock", model="m", dimension=8
    )
    kb = await store.create_kb(name="kb", embedding_profile_id=emb.id)
    await store.update_kb(kb.id, {"enabled": False})
    with pytest.raises(ConflictError):
        await store.get_kb_bundle(kb.id)

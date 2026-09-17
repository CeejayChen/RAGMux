"""实例管理器行为测试：懒加载、LRU 驱逐、失效、引用计数防误驱逐。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from ragmux.manager.factory import InstanceFactory
from ragmux.manager.instances import InstanceManager
from ragmux.registry.store import RegistryStore


@pytest.fixture
async def env(tmp_path: Path):
    store = await RegistryStore.create(tmp_path / "registry.db")
    llm = await store.create_profile(name="l", kind="llm", provider="mock", model="m")
    emb = await store.create_profile(
        name="e", kind="embedding", provider="mock", model="m", dimension=8
    )
    factory = InstanceFactory(tmp_path / "kbs")
    return store, factory, llm, emb


async def _make_bundle(store, llm, emb, name: str):
    kb = await store.create_kb(name=name, embedding_profile_id=emb.id, llm_profile_id=llm.id)
    return await store.get_kb_bundle(kb.id)


async def test_lru_eviction(env):
    store, factory, llm, emb = env
    manager = InstanceManager(factory=factory, max_instances=2)
    bundles = [await _make_bundle(store, llm, emb, f"kb{i}") for i in range(3)]

    async with manager.lease(bundles[0]) as inst0:
        assert inst0 is not None
    async with manager.lease(bundles[1]):
        pass
    assert manager.stats().loaded == 2

    # 加载第三个 → LRU 驱逐第一个
    async with manager.lease(bundles[2]):
        pass
    stats = manager.stats()
    assert stats.loaded == 2
    assert bundles[0].kb_id not in stats.loaded_ids
    assert {bundles[1].kb_id, bundles[2].kb_id}.issubset(set(stats.loaded_ids))


async def test_active_instance_not_evicted(env):
    store, factory, llm, emb = env
    manager = InstanceManager(factory=factory, max_instances=1)
    b0 = await _make_bundle(store, llm, emb, "hold")
    b1 = await _make_bundle(store, llm, emb, "other")

    async with manager.lease(b0):
        async with manager.lease(b1):
            pass  # b0 在用，不可驱逐；允许暂时超限
        assert manager.stats().loaded >= 1
        assert b0.kb_id in manager.stats().active_ids
    # b0 释放后仍驻留（未超限时驱逐只在腾位时发生）
    assert manager.stats().loaded == 2 or b0.kb_id in manager.stats().loaded_ids


async def test_invalidate_rebuilds(env):
    store, factory, llm, emb = env
    manager = InstanceManager(factory=factory, max_instances=4)
    bundle = await _make_bundle(store, llm, emb, "kb")

    async with manager.lease(bundle) as first:
        pass
    assert await manager.invalidate(bundle.kb_id) is True
    assert manager.stats().loaded == 0
    async with manager.lease(bundle) as second:
        assert second is not first


async def test_invalidate_deferred_while_active(env):
    store, factory, llm, emb = env
    manager = InstanceManager(factory=factory, max_instances=4)
    bundle = await _make_bundle(store, llm, emb, "kb")

    async with manager.lease(bundle):
        evicted = await manager.invalidate(bundle.kb_id)
        assert evicted is False  # 在用中，标记待驱逐
        assert manager.stats().loaded == 1
    # 释放后完成驱逐
    assert manager.stats().loaded == 0


async def test_concurrent_lease_single_creation(env):
    """同一知识库并发 lease 应互斥地只创建一个实例。"""
    store, factory, llm, emb = env
    manager = InstanceManager(factory=factory, max_instances=4)
    bundle = await _make_bundle(store, llm, emb, "kb")

    instances: list = []

    async def _grab():
        async with manager.lease(bundle) as inst:
            instances.append(inst)
            await asyncio.sleep(0.05)

    await asyncio.gather(_grab(), _grab(), _grab())
    assert len({id(inst) for inst in instances}) == 1

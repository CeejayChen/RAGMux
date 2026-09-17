"""实例管理器：懒加载 + per-key 互斥创建 + LRU 驱逐 + 引用计数。

关键约束（与 LightRAG 1.5.7 的实现核对过）：

- 每个实例绑定创建时的事件循环，本管理器必须在应用主循环内使用。
- 驱逐只调用实例级 ``finalize_storages()``；进程级 ``finalize_share_data()``
  仅允许在进程退出路径调用。
- 引用计数（lease）保证驱逐不会命中正在使用中的实例；若无实例可驱逐则
  允许临时超出容量上限并记录告警，绝不强杀在用实例。
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from lightrag import LightRAG
from lightrag.utils import logger

from ragmux.manager.factory import InstanceFactory
from ragmux.registry.store import KBBundle


class InstanceBuildError(Exception):
    """实例构建或初始化失败（存储后端连不上、维度不符等）。"""


@dataclass
class _Entry:
    instance: LightRAG
    active: int = 0
    pending_evict: bool = False


@dataclass
class ManagerStats:
    loaded: int = 0
    capacity: int = 8
    loaded_ids: list[str] = field(default_factory=list)
    active_ids: list[str] = field(default_factory=list)


class InstanceManager:
    """kb_id → LightRAG 实例的驻留与生命周期管理。"""

    def __init__(self, factory: InstanceFactory, max_instances: int = 8):
        self.factory = factory
        self.max_instances = max_instances
        self._entries: OrderedDict[str, _Entry] = OrderedDict()
        self._key_locks: dict[str, asyncio.Lock] = {}
        self._registry_lock = asyncio.Lock()
        self._closed = False

    @asynccontextmanager
    async def lease(self, bundle: KBBundle) -> AsyncIterator[LightRAG]:
        """取用知识库实例的上下文管理器：按需创建，期间引用计数 +1 防驱逐。"""
        kb_id = bundle.kb_id
        lock = self._lock_for(kb_id)
        async with lock:
            instance = await self._get_or_create(bundle)
            # 引用计数必须在持锁期间变更，否则 invalidate 可能在此间隙驱逐新实例
            self._entries[kb_id].active += 1
        try:
            yield instance
        finally:
            async with lock:
                entry = self._entries.get(kb_id)
                if entry is not None:
                    entry.active -= 1
                    if entry.active <= 0 and entry.pending_evict:
                        await self._evict(kb_id)

    async def invalidate(self, kb_id: str) -> bool:
        """使已加载实例失效（配置变更/删除前调用）。返回是否实际驱逐了实例。"""
        async with self._lock_for(kb_id):
            entry = self._entries.get(kb_id)
            if entry is None:
                return False
            if entry.active > 0:
                entry.pending_evict = True
                logger.info("实例 %s 正在使用中，标记待驱逐（引用归零后执行）", kb_id)
                return False
            return await self._evict(kb_id)

    async def close_all(self) -> None:
        """进程退出路径：驱逐全部实例。"""
        self._closed = True
        for kb_id in list(self._entries.keys()):
            await self._evict(kb_id)

    def stats(self) -> ManagerStats:
        return ManagerStats(
            loaded=len(self._entries),
            capacity=self.max_instances,
            loaded_ids=list(self._entries.keys()),
            active_ids=[kb_id for kb_id, entry in self._entries.items() if entry.active > 0],
        )

    # ------------------------------------------------------------------

    def _lock_for(self, kb_id: str) -> asyncio.Lock:
        """取 kb_id 专属锁（创建互斥的粒度；进程内单事件循环，无需异步字典锁）。"""
        lock = self._key_locks.get(kb_id)
        if lock is None:
            lock = asyncio.Lock()
            self._key_locks[kb_id] = lock
        return lock

    async def _get_or_create(self, bundle: KBBundle) -> LightRAG:
        """在持有 kb 锁的前提下获取或构建实例；必要时先做 LRU 腾位。"""
        kb_id = bundle.kb_id
        entry = self._entries.get(kb_id)
        if entry is not None:
            entry.pending_evict = False
            self._entries.move_to_end(kb_id)
            return entry.instance

        await self._make_room(exclude_kb_id=kb_id)
        try:
            instance = await self.factory.build(bundle)
            await instance.initialize_storages()
        except Exception as exc:
            raise InstanceBuildError(f"知识库实例构建失败: {exc}") from exc
        self._entries[kb_id] = _Entry(instance=instance)
        logger.info("实例已加载: %s（驻留 %d/%d）", kb_id, len(self._entries), self.max_instances)
        return instance

    async def _make_room(self, exclude_kb_id: str) -> None:
        """LRU 腾位：从最旧开始驱逐空闲实例；全部在用时允许暂时超限。"""
        while len(self._entries) >= self.max_instances:
            victim_id = next(
                (
                    kb_id
                    for kb_id, entry in self._entries.items()
                    if kb_id != exclude_kb_id and entry.active <= 0 and not entry.pending_evict
                ),
                None,
            )
            if victim_id is None:
                logger.warning(
                    "无空闲实例可驱逐（驻留 %d > 容量 %d），允许暂时超限",
                    len(self._entries),
                    self.max_instances,
                )
                return
            await self._evict(victim_id)

    async def _evict(self, kb_id: str) -> bool:
        """驱逐实例并 finalize 其存储；仅在持有 kb 锁或进程退出路径调用。"""
        entry = self._entries.pop(kb_id, None)
        if entry is None:
            return False
        try:
            await entry.instance.finalize_storages()
        except Exception as exc:  # noqa: BLE001 — finalize 失败不阻断驱逐，但必须记录
            logger.error("实例 %s finalize 失败: %s", kb_id, exc)
        logger.info("实例已驱逐: %s（驻留 %d）", kb_id, len(self._entries))
        return True

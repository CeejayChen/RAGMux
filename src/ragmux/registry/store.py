"""注册表存储：模型配置与知识库（扁平结构）的异步 CRUD。

领域错误（``NotFoundError`` / ``ConflictError``）由 API 层统一映射为
HTTP 404 / 409；本模块不做任何 HTTP 语义。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from ragmux.registry.models import Base, KBProfile, KnowledgeBase, new_id, utcnow_iso
from ragmux.registry.schemas import KBConfig


class NotFoundError(Exception):
    """资源不存在。"""


class ConflictError(Exception):
    """资源冲突（重名、仍被引用等）。"""


@dataclass
class KBBundle:
    """构建一个 LightRAG 实例所需的全部注册表记录（知识库 + 三个模型配置）。"""

    kb: KnowledgeBase
    llm: KBProfile | None
    embedding: KBProfile
    rerank: KBProfile | None
    kb_config: KBConfig = field(default_factory=KBConfig)

    @property
    def kb_id(self) -> str:
        return self.kb.id

    def prefers_offline_tokenizer(self) -> bool:
        """绑定模型含 mock 或 ollama provider 时返回 True。

        这类本地/离线部署不应依赖 tiktoken 首次使用时的联网下载，改用
        内置离线 tokenizer（ factories 据此选择，见 manager/factory.py）。
        """
        return any(
            profile is not None and profile.provider in ("mock", "ollama")
            for profile in (self.llm, self.embedding, self.rerank)
        )


_PROFILE_PROVIDERS: dict[str, set[str]] = {
    "llm": {"openai", "ollama", "mock"},
    "embedding": {"openai", "ollama", "mock"},
    "rerank": {"rerank_api", "mock"},
}


class RegistryStore:
    """注册表访问门面。通过 :meth:`create` 构造以完成建表。"""

    def __init__(self, engine: AsyncEngine):
        self.engine = engine
        self.session_factory = async_sessionmaker(engine, expire_on_commit=False)

    @classmethod
    async def create(cls, db_path: Path | str) -> RegistryStore:
        """打开（或创建）注册表数据库并建表。"""
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        engine = create_async_engine(f"sqlite+aiosqlite:///{path.as_posix()}")
        store = cls(engine)
        async with engine.begin() as conn:
            await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
            await conn.run_sync(Base.metadata.create_all)
        return store

    async def dispose(self) -> None:
        await self.engine.dispose()

    # ------------------------------------------------------------------
    # 模型配置
    # ------------------------------------------------------------------

    async def list_profiles(self, kind: str | None = None) -> list[KBProfile]:
        async with self.session_factory() as session:
            stmt = select(KBProfile).order_by(KBProfile.created_at)
            if kind is not None:
                stmt = stmt.where(KBProfile.kind == kind)
            return list((await session.execute(stmt)).scalars().all())

    async def get_profile(self, profile_id: str) -> KBProfile:
        async with self.session_factory() as session:
            row = await session.get(KBProfile, profile_id)
            if row is None:
                raise NotFoundError(f"模型配置不存在: {profile_id}")
            return row

    async def create_profile(
        self,
        *,
        name: str,
        kind: str,
        provider: str,
        model: str,
        base_url: str | None = None,
        api_key: str | None = None,
        dimension: int | None = None,
        extra: dict | None = None,
    ) -> KBProfile:
        """创建模型配置。"""
        validate_profile(kind, provider, dimension)
        if await self._profile_name_taken(name):
            raise ConflictError(f"模型配置名已存在: {name}")
        row = KBProfile(
            id=new_id(),
            name=name,
            kind=kind,
            provider=provider,
            base_url=base_url,
            api_key=api_key,
            model=model,
            dimension=dimension,
            extra=extra,
        )
        async with self.session_factory() as session:
            session.add(row)
            await session.commit()
        return row

    async def update_profile(self, profile_id: str, changes: dict) -> KBProfile:
        """更新模型配置（调用方控制字段白名单）。"""
        current = await self.get_profile(profile_id)
        async with self.session_factory() as session:
            row = await session.get(KBProfile, profile_id)
            for key, value in changes.items():
                setattr(row, key, value)
            validate_profile(row.kind, row.provider, row.dimension)
            if (
                "name" in changes
                and changes["name"] != current.name
                and await self._profile_name_taken(changes["name"])
            ):
                raise ConflictError(f"模型配置名已存在: {changes['name']}")
            row.updated_at = utcnow_iso()
            await session.commit()
            await session.refresh(row)
            return row

    async def delete_profile(self, profile_id: str) -> None:
        """删除模型配置；仍被知识库引用时拒绝。"""
        await self.get_profile(profile_id)
        referencing = await self.kb_ids_referencing_profile(profile_id)
        if referencing:
            raise ConflictError(f"模型配置仍被 {len(referencing)} 个知识库引用，先解除绑定")
        async with self.session_factory() as session:
            await session.execute(delete(KBProfile).where(KBProfile.id == profile_id))
            await session.commit()

    async def kb_ids_referencing_profile(self, profile_id: str) -> list[str]:
        async with self.session_factory() as session:
            stmt = select(KnowledgeBase.id).where(
                (KnowledgeBase.llm_profile_id == profile_id)
                | (KnowledgeBase.embedding_profile_id == profile_id)
                | (KnowledgeBase.rerank_profile_id == profile_id)
            )
            return list((await session.execute(stmt)).scalars().all())

    async def _profile_name_taken(self, name: str) -> bool:
        async with self.session_factory() as session:
            row = (
                (await session.execute(select(KBProfile).where(KBProfile.name == name)))
                .scalars()
                .first()
            )
            return row is not None

    # ------------------------------------------------------------------
    # 知识库
    # ------------------------------------------------------------------

    async def list_kbs(self) -> list[KnowledgeBase]:
        async with self.session_factory() as session:
            stmt = select(KnowledgeBase).order_by(KnowledgeBase.created_at)
            return list((await session.execute(stmt)).scalars().all())

    async def get_kb(self, kb_id: str) -> KnowledgeBase:
        async with self.session_factory() as session:
            row = await session.get(KnowledgeBase, kb_id)
            if row is None:
                raise NotFoundError(f"知识库不存在: {kb_id}")
            return row

    async def get_kb_by_name(self, name: str) -> KnowledgeBase | None:
        async with self.session_factory() as session:
            return (
                (await session.execute(select(KnowledgeBase).where(KnowledgeBase.name == name)))
                .scalars()
                .first()
            )

    async def create_kb(
        self,
        *,
        name: str,
        embedding_profile_id: str,
        description: str = "",
        llm_profile_id: str | None = None,
        rerank_profile_id: str | None = None,
        config: KBConfig | None = None,
    ) -> KnowledgeBase:
        """创建知识库。校验模型引用与存储后端名的有效性。"""
        if await self.get_kb_by_name(name) is not None:
            raise ConflictError(f"知识库重名: {name}")
        for profile_id in (llm_profile_id, embedding_profile_id, rerank_profile_id):
            if profile_id is not None:
                await self.get_profile(profile_id)
        kb_config = config or KBConfig()
        validate_storage_names(kb_config)
        row = KnowledgeBase(
            id=new_id(),
            name=name,
            description=description,
            llm_profile_id=llm_profile_id,
            embedding_profile_id=embedding_profile_id,
            rerank_profile_id=rerank_profile_id,
            config=kb_config.model_dump(),
        )
        async with self.session_factory() as session:
            session.add(row)
            await session.commit()
        return row

    async def update_kb(self, kb_id: str, changes: dict) -> KnowledgeBase:
        """更新知识库（调用方控制字段白名单）。config 为部分合并更新。"""
        await self.get_kb(kb_id)
        changes = dict(changes)
        async with self.session_factory() as session:
            row = await session.get(KnowledgeBase, kb_id)
            if (
                "name" in changes
                and changes["name"] != row.name
                and await self.get_kb_by_name(changes["name"])
            ):
                raise ConflictError(f"知识库重名: {changes['name']}")
            for profile_key in ("llm_profile_id", "embedding_profile_id", "rerank_profile_id"):
                if changes.get(profile_key) is not None:
                    await self.get_profile(changes[profile_key])
            config_changes = changes.pop("config", None)
            for key, value in changes.items():
                setattr(row, key, value)
            if config_changes is not None:
                new_config = KBConfig(**{**row.config, **config_changes})
                validate_storage_names(new_config)
                row.config = new_config.model_dump()
            row.updated_at = utcnow_iso()
            await session.commit()
            await session.refresh(row)
            return row

    async def delete_kb_row(self, kb_id: str) -> None:
        """仅删除注册表行；实例驱逐与数据目录清理由 API 层编排。"""
        await self.get_kb(kb_id)
        async with self.session_factory() as session:
            await session.execute(delete(KnowledgeBase).where(KnowledgeBase.id == kb_id))
            await session.commit()

    async def get_kb_bundle(self, kb_id: str) -> KBBundle:
        """加载构建实例所需的完整记录集；任一绑定缺失即抛错。"""
        kb = await self.get_kb(kb_id)
        if not kb.enabled:
            raise ConflictError(f"知识库已停用: {kb.name}")
        llm = await self.get_profile(kb.llm_profile_id) if kb.llm_profile_id else None
        embedding = await self.get_profile(kb.embedding_profile_id)
        rerank = await self.get_profile(kb.rerank_profile_id) if kb.rerank_profile_id else None
        kb_config = KBConfig(**kb.config)
        return KBBundle(kb=kb, llm=llm, embedding=embedding, rerank=rerank, kb_config=kb_config)

    async def overview_counts(self) -> dict[str, int]:
        async with self.session_factory() as session:
            kbs = (await session.execute(select(func.count()).select_from(KnowledgeBase))).scalar()
            profiles = (await session.execute(select(func.count()).select_from(KBProfile))).scalar()
            return {"kbs": int(kbs or 0), "profiles": int(profiles or 0)}


def validate_profile(kind: str, provider: str, dimension: int | None) -> None:
    """校验模型配置的类型/provider/维度组合。"""
    if kind not in _PROFILE_PROVIDERS:
        raise ConflictError(f"不支持的模型类型: {kind}")
    if provider not in _PROFILE_PROVIDERS[kind]:
        raise ConflictError(
            f"{kind} 类型不支持 provider={provider}，可选: {sorted(_PROFILE_PROVIDERS[kind])}"
        )
    if kind == "embedding" and dimension is None:
        raise ConflictError("embedding 配置必须声明向量维度 dimension")


def validate_storage_names(config: KBConfig) -> None:
    """校验存储后端名在 lightrag.kg.STORAGES 注册表中存在。"""
    from lightrag.kg import STORAGES

    names = list(config.storage.model_dump().values())
    missing = [name for name in names if name not in STORAGES]
    if missing:
        raise ConflictError(
            f"未知存储后端实现: {missing}（须为 lightrag.kg.STORAGES 中注册的名称）"
        )

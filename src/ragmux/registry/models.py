"""注册表 ORM 模型（SQLite / SQLAlchemy 2.0）。

两张表构成"知识库 → 模型配置"的引用关系（扁平结构，无分组层级）：

- ``knowledge_bases``：知识库一等实体，持有自身 LightRAG 配置（JSON）与模型绑定。
- ``kb_profiles``：模型配置（llm / embedding / rerank），知识库按 id 引用。

约定：所有 id 为 ``uuid4().hex``；时间戳为 UTC ISO 字符串。
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow_iso() -> str:
    """当前 UTC 时间的 ISO 字符串（注册表统一时间戳格式）。"""
    return datetime.now(UTC).isoformat(timespec="seconds")


def new_id() -> str:
    """生成注册表实体 id（uuid4 hex）。"""
    import uuid

    return uuid.uuid4().hex


class Base(DeclarativeBase):
    pass


class KBProfile(Base):
    """模型配置：LLM / Embedding / Rerank 的连接与参数，供知识库按 id 引用。"""

    __tablename__ = "kb_profiles"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    kind: Mapped[str] = mapped_column(String(16))
    """llm | embedding | rerank"""
    provider: Mapped[str] = mapped_column(String(32), default="openai")
    """openai（OpenAI 兼容 API）| ollama（本地 Ollama）| mock（离线确定性桩）| rerank_api（/rerank 协议）"""
    base_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    """openai：API 根地址；ollama：Ollama host（如 http://127.0.0.1:11434）。"""
    api_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    model: Mapped[str] = mapped_column(String(255))
    dimension: Mapped[int | None] = mapped_column(Integer, nullable=True)
    """embedding 专用：向量维度（必须与模型实际输出一致）。"""
    extra: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    """provider 特有的扩展参数（如 ollama options/timeout、query_prefix）。"""
    created_at: Mapped[str] = mapped_column(String(32), default=utcnow_iso)
    updated_at: Mapped[str] = mapped_column(String(32), default=utcnow_iso, onupdate=utcnow_iso)


class KnowledgeBase(Base):
    """知识库一等实体：配置即实例的构建蓝图，全部字段可运行时修改。"""

    __tablename__ = "knowledge_bases"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    llm_profile_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("kb_profiles.id"), nullable=True
    )
    embedding_profile_id: Mapped[str] = mapped_column(String(32), ForeignKey("kb_profiles.id"))
    rerank_profile_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("kb_profiles.id"), nullable=True
    )
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    """KBConfig 序列化结果：LightRAG 构建参数与查询默认值（见 schemas.KBConfig）。"""
    created_at: Mapped[str] = mapped_column(String(32), default=utcnow_iso)
    updated_at: Mapped[str] = mapped_column(String(32), default=utcnow_iso, onupdate=utcnow_iso)

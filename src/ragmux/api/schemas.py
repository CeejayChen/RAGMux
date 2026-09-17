"""API 请求模型（响应统一用 dict 组装，便于携带 LightRAG 动态字段）。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ragmux.registry.schemas import QUERY_MODES, KBConfig


class ProfileCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    kind: str
    provider: str = "openai"
    model: str = Field(min_length=1)
    base_url: str | None = None
    api_key: str | None = None
    dimension: int | None = None
    extra: dict | None = None


class ProfileUpdateRequest(BaseModel):
    name: str | None = None
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    dimension: int | None = None
    extra: dict | None = None


class KBCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    embedding_profile_id: str
    description: str = ""
    llm_profile_id: str | None = None
    rerank_profile_id: str | None = None
    config: KBConfig = Field(default_factory=KBConfig)


class KBUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    enabled: bool | None = None
    llm_profile_id: str | None = None
    embedding_profile_id: str | None = None
    rerank_profile_id: str | None = None
    config: dict | None = None
    """KBConfig 的部分合并更新（深合并到现有配置）。"""


class DocumentTextRequest(BaseModel):
    texts: list[str] = Field(min_length=1)
    file_paths: list[str] | None = None
    """与 texts 对齐的展示名（引用/去重提示用）。"""


class QueryRequest(BaseModel):
    query: str = Field(min_length=1)
    mode: QUERY_MODES | None = None
    only_need_context: bool | None = None
    response_type: str | None = None
    top_k: int | None = Field(default=None, ge=1)
    chunk_top_k: int | None = Field(default=None, ge=1)


class MultiKBQueryRequest(BaseModel):
    kb_ids: list[str] = Field(min_length=1)
    query: str = Field(min_length=1)
    mode: QUERY_MODES | None = None
    only_need_context: bool | None = None
    response_type: str | None = None
    top_k: int | None = Field(default=None, ge=1)
    chunk_top_k: int | None = Field(default=None, ge=1)

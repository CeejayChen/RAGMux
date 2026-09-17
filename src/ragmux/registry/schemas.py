"""注册表的 API/领域 schema（pydantic v2）。

``KBConfig`` 是知识库 → LightRAG 构建参数的唯一载体：字段白名单即"允许
运行时调整的 LightRAG 参数清单"。新增可调参数时在此扩展字段并在
``manager.factory`` 中接线，禁止绕过本模型直接透传任意 kwargs。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

QUERY_MODES = Literal["local", "global", "hybrid", "naive", "mix", "bypass"]


class KBStorageConfig(BaseModel):
    """四类存储后端实现名（必须存在于 lightrag.kg.STORAGES 注册表）。"""

    kv_storage: str = "JsonKVStorage"
    vector_storage: str = "NanoVectorDBStorage"
    graph_storage: str = "NetworkXStorage"
    doc_status_storage: str = "JsonDocStatusStorage"


class KBQueryDefaults(BaseModel):
    """查询默认值；请求未显式指定时生效。"""

    mode: QUERY_MODES = "mix"
    only_need_context: bool = False
    response_type: str = "多个段落"
    top_k: int = Field(default=10, ge=1)
    chunk_top_k: int = Field(default=6, ge=1)


class KBConfig(BaseModel):
    """知识库的 LightRAG 构建参数与查询默认值。"""

    storage: KBStorageConfig = Field(default_factory=KBStorageConfig)
    chunk_token_size: int = Field(default=1200, ge=128)
    chunk_overlap_token_size: int = Field(default=100, ge=0)
    llm_model_max_async: int = Field(default=4, ge=1)
    """该库 LLM 调用并发上限（单进程多库场景下用于限流）。"""
    embedding_func_max_async: int = Field(default=4, ge=1)
    embedding_batch_num: int = Field(default=32, ge=1)
    language: str = "Simplified Chinese"
    """实体抽取提示词语言（addon_params.language）。"""
    query: KBQueryDefaults = Field(default_factory=KBQueryDefaults)
    entity_types: list[str] | None = None
    """覆盖实体类型清单；None 使用 LightRAG 默认。"""

    def to_addon_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {"language": self.language}
        if self.entity_types:
            params["entity_types"] = self.entity_types
        return params

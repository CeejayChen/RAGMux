"""服务配置。

所有配置项均可通过 ``RAGMUX_`` 前缀的环境变量覆盖（pydantic-settings），
例如 ``RAGMUX_DATA_DIR=./data``。注册表中的知识库配置不属于本模块——
那是运行时数据，只存于 SQLite。
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 仓库根目录（src/ragmux/config.py → 上三级）
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """服务级配置。仅包含进程自身的运行参数，不包含任何具体知识库的配置。"""

    model_config = SettingsConfigDict(env_prefix="RAGMUX_", env_file=".env", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 9700
    """HTTP 监听端口。"""

    data_dir: Path = REPO_ROOT / "data"
    """数据根目录：注册表数据库与各知识库的 LightRAG working_dir 都在其下。"""

    max_loaded_instances: int = 8
    """同时驻留内存的 LightRAG 实例上限（LRU 驱逐）。"""

    static_dir: Path | None = None
    """前端构建产物目录；缺省使用 <repo>/web/dist。目录不存在则只提供 API。"""

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    """开发期 Vite dev server 的跨域来源。"""

    def resolve_static_dir(self) -> Path:
        return (self.static_dir or REPO_ROOT / "web" / "dist").resolve()

    @property
    def registry_db_path(self) -> Path:
        return self.data_dir / "registry.db"

    @property
    def kb_data_root(self) -> Path:
        return self.data_dir / "kbs"


settings = Settings()

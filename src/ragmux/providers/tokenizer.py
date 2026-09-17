"""离线 tokenizer：避免 tiktoken 首次使用时从网络下载编码文件。

设计约束：``decode(encode(x)) == x`` 必须精确成立——LightRAG 的分块器以
token 计数切分后用 decode 还原 chunk 内容，若丢失空白会破坏原文与向量。
实现：每个 token 携带其前导空白一并编码，decode 直接拼接即可无损还原。
线程安全：id 表更新持锁（LightRAG 会在工作线程并发调用 encode）。
"""

from __future__ import annotations

import re
import threading

# 每个词 token 带上前导空白；独立空白串与标点单独成 token
_TOKEN_RE = re.compile(r"\s*\w+|\s+|[^\w\s]", re.UNICODE)

_LOCK = threading.Lock()
_TOKEN_TO_ID: dict[str, int] = {}
_ID_TO_TOKEN: dict[int, str] = {}


def _token_id(token: str) -> int:
    """token → id；同一 token 在进程内映射稳定。"""
    with _LOCK:
        cached = _TOKEN_TO_ID.get(token)
        if cached is not None:
            return cached
        new_id = len(_TOKEN_TO_ID) + 1
        _TOKEN_TO_ID[token] = new_id
        _ID_TO_TOKEN[new_id] = token
        return new_id


def _token_text(token_id: int) -> str:
    with _LOCK:
        return _ID_TO_TOKEN.get(token_id, "")


class OfflineTokenizer:
    """LightRAG TokenizerInterface 的离线实现（无损、确定性、线程安全）。"""

    def encode(self, content: str) -> list[int]:
        """切分为 token id 序列。"""
        return [_token_id(match.group(0)) for match in _TOKEN_RE.finditer(content)]

    def decode(self, tokens: list[int]) -> str:
        """由 token id 序列精确还原原文。"""
        return "".join(_token_text(t) for t in tokens)

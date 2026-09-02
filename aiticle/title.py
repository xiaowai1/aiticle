from __future__ import annotations

import re

WECHAT_TITLE_MAX = 32


def finalize_wechat_title(title: str, name: str = "", code: str = "") -> str:
    """清洗 AI 标题：去代码、去空白；超长则抛错触发重试，避免硬截断半句。"""
    text = title.strip()
    if code:
        text = re.sub(rf"[（(]\s*{code}\s*[）)]", "", text)
        text = re.sub(rf"\b{code}\b", "", text)
    text = re.sub(r"\s+", "", text).strip("：:，, ")
    if not text:
        raise ValueError("标题为空")
    if len(text) > WECHAT_TITLE_MAX:
        raise ValueError(f"标题 {len(text)} 字，超过微信 {WECHAT_TITLE_MAX} 字上限")
    return text


def fit_wechat_title(text: str, max_len: int = WECHAT_TITLE_MAX) -> str:
    """发布前最后一道保险（正常不应触发截断）。"""
    text = text.strip()
    if len(text) <= max_len:
        return text
    chunk = text[:max_len]
    for i in range(len(chunk) - 1, max(0, len(chunk) - 10), -1):
        if chunk[i] in "，。；、：｜|·":
            return chunk[:i].rstrip("，。；、：｜|·")
    return chunk

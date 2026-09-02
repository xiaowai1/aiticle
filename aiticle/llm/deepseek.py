from __future__ import annotations

import json
import re
from typing import Any

import httpx

from aiticle.config import Settings

FORBIDDEN = [
    "买入",
    "卖出",
    "加仓",
    "减仓",
    "抄底",
    "逃顶",
    "目标价",
    "强烈推荐",
    "必涨",
    "翻倍",
    "庄家",
    "内幕",
    "稳赚",
    "低估",
    "高估",
    "买入点",
    "卖出点",
    "跟庄",
    "建议关注",
    "可以布局",
]


class DeepSeekClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._url = settings.deepseek_base_url.rstrip("/") + "/chat/completions"

    def complete_json(self, system: str, user: str, *, max_tokens: int = 8192) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.settings.deepseek_api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.settings.deepseek_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.55,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        if self.settings.deepseek_model.startswith("deepseek-v4"):
            payload["thinking"] = {"type": "disabled"}

        with httpx.Client(timeout=180.0) as client:
            resp = client.post(self._url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        content = data["choices"][0]["message"]["content"]
        parsed = _extract_json(content)
        if not isinstance(parsed, dict):
            raise RuntimeError("DeepSeek 未返回 JSON 对象")
        return parsed


def _extract_json(text: str) -> Any:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise
        return json.loads(match.group(0))


def find_forbidden(text: str) -> list[str]:
    return [word for word in FORBIDDEN if word in text]

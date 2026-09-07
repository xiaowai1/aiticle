from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from aiticle.data.fetcher import normalize_code

logger = logging.getLogger(__name__)

MAX_FAIL_ATTEMPTS = 3


class WrittenRecord(BaseModel):
    name: str = ""
    drafted_at: str
    media_id: str | None = None
    title: str | None = None


class FailedRecord(BaseModel):
    name: str = ""
    attempts: int = 0
    last_error: str | None = None
    last_at: str | None = None


class WrittenRegistry(BaseModel):
    version: int = 1
    updated_at: str = ""
    written: dict[str, WrittenRecord] = Field(default_factory=dict)
    failed: dict[str, FailedRecord] = Field(default_factory=dict)


class RegistryStatus(BaseModel):
    market_total: int = 0
    written_count: int = 0
    remaining_count: int = 0
    failed_blocked_count: int = 0
    next_codes: list[str] = Field(default_factory=list)


class RegistryStore:
    """按领域隔离的已写/失败记录。"""

    def __init__(self, registry_path: Path, data_dir: Path | None = None) -> None:
        self.registry_path = registry_path
        self.data_dir = data_dir or registry_path.parent

    def load_registry(self) -> WrittenRegistry:
        if not self.registry_path.exists():
            return WrittenRegistry()
        raw = json.loads(self.registry_path.read_text(encoding="utf-8"))
        return WrittenRegistry.model_validate(raw)

    def save_registry(self, registry: WrittenRegistry) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        registry.updated_at = datetime.now().isoformat(timespec="seconds")
        payload = json.dumps(registry.model_dump(), ensure_ascii=False, indent=2)
        fd, tmp = tempfile.mkstemp(dir=self.data_dir, suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp, self.registry_path)
        except Exception:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def clear_registry(self) -> None:
        self.save_registry(WrittenRegistry())

    def mark_written(
        self,
        code: str,
        *,
        name: str = "",
        media_id: str | None = None,
        title: str | None = None,
    ) -> None:
        if not media_id:
            raise ValueError("缺少草稿 media_id，不能标记为已写")
        registry = self.load_registry()
        code = normalize_code(code)
        registry.written[code] = WrittenRecord(
            name=name,
            drafted_at=datetime.now().isoformat(timespec="seconds"),
            media_id=media_id,
            title=title,
        )
        registry.failed.pop(code, None)
        self.save_registry(registry)

    def mark_failed(self, code: str, error: str, *, name: str = "") -> None:
        registry = self.load_registry()
        code = normalize_code(code)
        now = datetime.now().isoformat(timespec="seconds")
        rec = registry.failed.get(code)
        if rec:
            rec.attempts += 1
            rec.last_error = error[:500]
            rec.last_at = now
            if name:
                rec.name = name
        else:
            registry.failed[code] = FailedRecord(
                name=name,
                attempts=1,
                last_error=error[:500],
                last_at=now,
            )
        self.save_registry(registry)

    def get_status(self) -> RegistryStatus:
        registry = self.load_registry()
        market = fetch_market_list()
        remaining = 0
        blocked = 0
        next_codes: list[str] = []

        for code, name in market:
            if code in registry.written:
                continue
            failed = registry.failed.get(code)
            if failed and failed.attempts >= MAX_FAIL_ATTEMPTS:
                blocked += 1
                continue
            remaining += 1
            if len(next_codes) < 5:
                next_codes.append(f"{code} {name}".strip())

        return RegistryStatus(
            market_total=len(market),
            written_count=len(registry.written),
            remaining_count=remaining,
            failed_blocked_count=blocked,
            next_codes=next_codes,
        )


def fetch_market_list() -> list[tuple[str, str]]:
    """拉取当前沪深京 A 股列表（含 ST），按代码升序。"""
    import akshare as ak

    df = ak.stock_info_a_code_name()
    items: list[tuple[str, str]] = []
    for _, row in df.iterrows():
        code = normalize_code(str(row["code"]))
        name = str(row.get("name") or "").strip()
        items.append((code, name))
    items.sort(key=lambda x: x[0])
    return items


def pick_unwritten(count: int = 1, *, store: RegistryStore) -> list[tuple[str, str]]:
    registry = store.load_registry()
    market = fetch_market_list()
    picked: list[tuple[str, str]] = []

    for code, name in market:
        if code in registry.written:
            continue
        failed = registry.failed.get(code)
        if failed and failed.attempts >= MAX_FAIL_ATTEMPTS:
            continue
        picked.append((code, name))
        if len(picked) >= count:
            break

    return picked

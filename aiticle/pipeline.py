from __future__ import annotations

import json
import logging
from datetime import datetime

from aiticle.config import DATA_DIR, Settings
from aiticle.data.fetcher import fetch_company
from aiticle.export import export_wechat
from aiticle.generate import generate_wechat
from aiticle.llm.deepseek import DeepSeekClient
from aiticle.publish.wechat import WeChatDraftPublisher
from aiticle.registry import mark_failed, mark_written

logger = logging.getLogger(__name__)

DAILY_LOG = DATA_DIR / "daily_runs.jsonl"


def process_one_company(
    settings: Settings,
    code: str,
    *,
    name: str = "",
) -> dict:
    """拉取最新公开数据 → DeepSeek 写公众号稿 → 写入微信草稿箱。"""
    settings.require_deepseek()
    settings.require_wechat()

    try:
        logger.info("[%s] 正在拉取公开数据…", code)
        snapshot = fetch_company(code)
        if snapshot.fetch_warnings:
            for w in snapshot.fetch_warnings:
                logger.warning("[%s] %s", code, w)

        client = DeepSeekClient(settings)
        logger.info("[%s] 正在生成公众号文稿…", code)
        article = generate_wechat(client, snapshot)

        out = export_wechat(snapshot, article)
        logger.info("[%s] 已导出到 %s", code, out)

        publisher = WeChatDraftPublisher(settings)
        media_id = publisher.publish_from_dir(out)
        if not media_id:
            raise RuntimeError("微信草稿创建失败：未返回 media_id")
        logger.info("[%s] 公众号草稿 media_id=%s", code, media_id)

        # 仅草稿箱写入成功后才记入已写；任一步失败走 mark_failed，不会进 written
        mark_written(
            snapshot.code,
            name=snapshot.name or name,
            media_id=media_id,
            title=article.title,
        )
        record = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "code": snapshot.code,
            "name": snapshot.name,
            "status": "ok",
            "media_id": media_id,
            "title": article.title,
            "output_dir": str(out),
        }
        _append_log(record)
        return record
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        logger.error("[%s] 失败: %s", code, msg)
        mark_failed(code, msg, name=name)
        record = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "code": code,
            "status": "error",
            "error": msg,
        }
        _append_log(record)
        raise


def _append_log(record: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with DAILY_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")

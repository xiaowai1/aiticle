from __future__ import annotations

import json
import logging
from datetime import datetime

from aiticle.config import Settings, VerticalConfig
from aiticle.data.fetcher import fetch_company
from aiticle.export import export_wechat
from aiticle.generate import generate_wechat
from aiticle.llm.deepseek import DeepSeekClient
from aiticle.publish.wechat import WeChatDraftPublisher
from aiticle.registry import MAX_FAIL_ATTEMPTS, RegistryStore, pick_unwritten
from aiticle.verticals.base import Vertical

logger = logging.getLogger(__name__)


class StockVertical(Vertical):
    id = "stock"
    label = "A股公司介绍"
    description = "沪深京 A 股上市公司公开资料介绍"
    implemented = True

    def run_batch(
        self,
        settings: Settings,
        config: VerticalConfig,
        count: int | None,
    ) -> list[dict]:
        self.require_ready(config)
        settings.require_deepseek()
        WeChatDraftPublisher(config).verify_connection()

        store = RegistryStore(config.registry_path, config.data_dir)
        n = count or config.batch_count

        status = store.get_status()
        if status.remaining_count == 0:
            logger.warning(
                "当前在市公司均已写过（或失败次数已达上限）。已写 %d / 在市 %d",
                status.written_count,
                status.market_total,
            )

        targets = pick_unwritten(n, store=store)
        if not targets:
            logger.error("没有可处理的公司。")
            return []

        results: list[dict] = []
        for code, name in targets:
            logger.info("开始处理 %s %s", code, name)
            try:
                results.append(self.process_one(settings, config, code, name=name))
            except Exception:  # noqa: BLE001
                continue

        ok = sum(1 for r in results if r.get("status") == "ok")
        logger.info("本批结束：成功 %d / 计划 %d", ok, len(targets))
        return results

    def process_one(
        self,
        settings: Settings,
        config: VerticalConfig,
        target: str,
        *,
        name: str = "",
    ) -> dict:
        self.require_ready(config)
        settings.require_deepseek()
        code = target
        store = RegistryStore(config.registry_path, config.data_dir)

        try:
            logger.info("[%s] 正在拉取公开数据…", code)
            snapshot = fetch_company(code)
            if snapshot.fetch_warnings:
                for w in snapshot.fetch_warnings:
                    logger.warning("[%s] %s", code, w)

            client = DeepSeekClient(settings)
            logger.info("[%s] 正在生成公众号文稿…", code)
            article = generate_wechat(client, snapshot)

            out = export_wechat(snapshot, article, config.output_dir)
            logger.info("[%s] 已导出到 %s", code, out)

            publisher = WeChatDraftPublisher(config)
            media_id = publisher.publish_from_dir(out)
            if not media_id:
                raise RuntimeError("微信草稿创建失败：未返回 media_id")
            logger.info("[%s] 公众号草稿 media_id=%s", code, media_id)

            store.mark_written(
                snapshot.code,
                name=snapshot.name or name,
                media_id=media_id,
                title=article.title,
            )
            record = {
                "vertical": self.id,
                "time": datetime.now().isoformat(timespec="seconds"),
                "code": snapshot.code,
                "name": snapshot.name,
                "status": "ok",
                "media_id": media_id,
                "title": article.title,
                "output_dir": str(out),
            }
            _append_log(config, record)
            return record
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            logger.error("[%s] 失败: %s", code, msg)
            store.mark_failed(code, msg, name=name)
            record = {
                "vertical": self.id,
                "time": datetime.now().isoformat(timespec="seconds"),
                "code": code,
                "status": "error",
                "error": msg,
            }
            _append_log(config, record)
            raise

    def status(self, config: VerticalConfig) -> str:
        store = RegistryStore(config.registry_path, config.data_dir)
        st = store.get_status()
        reg = store.load_registry()
        lines = [
            f"领域：{self.label}（{self.id}）",
            f"在市 {st.market_total} | 已写 {st.written_count} | 待写 {st.remaining_count} | "
            f"失败跳过 {st.failed_blocked_count}",
        ]
        if st.next_codes:
            lines.append("接下来：" + ", ".join(st.next_codes))
        if reg.failed:
            retryable = sum(1 for f in reg.failed.values() if f.attempts < MAX_FAIL_ATTEMPTS)
            if retryable:
                lines.append(f"失败待重试 {retryable} 家（满 3 次自动跳过）")
        return "\n".join(lines)


def _append_log(config: VerticalConfig, record: dict) -> None:
    config.data_dir.mkdir(parents=True, exist_ok=True)
    with config.daily_log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")

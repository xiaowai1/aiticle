from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from aiticle.config import OUTPUT_DIR, load_settings
from aiticle.data.fetcher import fetch_company, normalize_code
from aiticle.pipeline import process_one_company
from aiticle.publish.wechat import WeChatDraftPublisher, detect_outbound_ipv4
from aiticle.registry import (
    MAX_FAIL_ATTEMPTS,
    clear_registry,
    get_status,
    load_registry,
    pick_unwritten,
)

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="A 股公司介绍 → 微信公众号草稿箱")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="拉当日列表，选未写公司 → 写稿 → 草稿箱")
    p_run.add_argument("--count", type=int, default=None, help="本批家数，默认 .env 的 DAILY_COMPANY_COUNT")

    p_gen = sub.add_parser("generate", help="指定一家公司：拉数 → 写稿 → 草稿箱")
    p_gen.add_argument("--code", required=True)

    p_pub = sub.add_parser("publish", help="把已生成的 output/<代码> 重新发到草稿箱")
    p_pub.add_argument("--dir", type=Path)
    p_pub.add_argument("--code")

    p_fetch = sub.add_parser("fetch", help="仅拉公开数据（调试用）")
    p_fetch.add_argument("--code", required=True)

    sub.add_parser("status", help="查看在市列表与已写进度")
    sub.add_parser("check-wechat", help="诊断本机出口 IP 与公众号白名单")
    sub.add_parser("reset-registry", help="清空已写与失败记录，从头轮询")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "run":
            return _cmd_run(args.count)
        if args.cmd == "generate":
            return _cmd_generate(args.code)
        if args.cmd == "publish":
            return _cmd_publish(args.dir, args.code)
        if args.cmd == "fetch":
            return _cmd_fetch(args.code)
        if args.cmd == "status":
            return _cmd_status()
        if args.cmd == "check-wechat":
            return _cmd_check_wechat()
        if args.cmd == "reset-registry":
            return _cmd_reset_registry()
    except Exception as exc:  # noqa: BLE001
        logging.error("%s", exc)
        return 1
    return 0


def _run_batch(count: int | None) -> list[dict]:
    settings = load_settings()
    settings.require_wechat()
    WeChatDraftPublisher(settings).verify_connection()

    n = count or settings.daily_company_count

    status = get_status()
    if status.remaining_count == 0:
        logger.warning(
            "当前在市公司均已写过（或失败次数已达上限）。已写 %d / 在市 %d",
            status.written_count,
            status.market_total,
        )

    targets = pick_unwritten(n)
    if not targets:
        logger.error("没有可处理的公司。")
        return []

    results: list[dict] = []
    for code, name in targets:
        logger.info("开始处理 %s %s", code, name)
        try:
            results.append(process_one_company(settings, code, name=name))
        except Exception:  # noqa: BLE001
            continue

    ok = sum(1 for r in results if r.get("status") == "ok")
    logger.info("本批结束：成功 %d / 计划 %d", ok, len(targets))
    return results


def _cmd_run(count: int | None) -> int:
    results = _run_batch(count)
    if not results:
        print("本批没有成功写入任何草稿，请查看上方日志。")
        return 1
    for r in results:
        if r.get("status") == "ok":
            print(f"✓ {r['code']} {r.get('name', '')} → media_id={r['media_id']}")
    return 0


def _cmd_generate(code: str) -> int:
    settings = load_settings()
    WeChatDraftPublisher(settings).verify_connection()
    record = process_one_company(settings, code)
    print(
        f"已写入草稿箱 media_id={record['media_id']}，本地备份 {record['output_dir']}"
    )
    return 0


def _cmd_publish(article_dir: Path | None, code: str | None) -> int:
    settings = load_settings()
    settings.require_wechat()
    if article_dir is None:
        if not code:
            raise RuntimeError("请提供 --dir 或 --code")
        article_dir = OUTPUT_DIR / normalize_code(code)
    media_id = WeChatDraftPublisher(settings).publish_from_dir(article_dir)
    print(f"公众号草稿 media_id: {media_id}")
    return 0


def _cmd_fetch(code: str) -> int:
    snapshot = fetch_company(code)
    out = OUTPUT_DIR / snapshot.code
    out.mkdir(parents=True, exist_ok=True)
    path = out / "snapshot.json"
    path.write_text(json.dumps(snapshot.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写入 {path}")
    for item in snapshot.fetch_warnings:
        print(f"警告: {item}")
    return 0


def _cmd_status() -> int:
    st = get_status()
    reg = load_registry()
    print(
        f"在市 {st.market_total} | 已写 {st.written_count} | 待写 {st.remaining_count} | "
        f"失败跳过 {st.failed_blocked_count}"
    )
    if st.next_codes:
        print("接下来：", ", ".join(st.next_codes))
    if reg.failed:
        retryable = sum(1 for f in reg.failed.values() if f.attempts < MAX_FAIL_ATTEMPTS)
        if retryable:
            print(f"失败待重试 {retryable} 家（满 3 次自动跳过）")
    return 0


def _cmd_reset_registry() -> int:
    clear_registry()
    print("已清空已写列表与失败记录，下次 run 从列表头部重新选取。")
    return 0


def _cmd_check_wechat() -> int:
    settings = load_settings()
    settings.require_wechat()
    ip = detect_outbound_ipv4()
    print(f"本机出口 IPv4：{ip or '探测失败'}")
    print(f"配置的 AppID：{settings.wechat_app_id}")
    try:
        token = WeChatDraftPublisher(settings).verify_connection()
        print(f"成功：access_token 已获取（前 8 位 {token[:8]}…）")
        print("白名单与 AppSecret 配置正常。")
        return 0
    except RuntimeError as exc:
        print(str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())

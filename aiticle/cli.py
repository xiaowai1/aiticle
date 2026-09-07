from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from aiticle.config import (
    DEFAULT_VERTICAL,
    load_settings,
    load_vertical_config,
    resolve_article_dir,
)
from aiticle.data.fetcher import fetch_company
from aiticle.publish.wechat import WeChatDraftPublisher, detect_outbound_ipv4
from aiticle.registry import RegistryStore
from aiticle.verticals import get_vertical, list_verticals

logger = logging.getLogger(__name__)


def _add_vertical_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--vertical",
        "-v",
        default=DEFAULT_VERTICAL,
        choices=["stock", "reserved"],
        help="内容领域：stock=A股公司介绍，reserved=预留（默认 stock）",
    )


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="多领域内容 → 微信公众号草稿箱")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="按领域批量：拉列表 → 写稿 → 草稿箱")
    _add_vertical_arg(p_run)
    p_run.add_argument("--count", type=int, default=None, help="本批数量，默认读 .env 对应领域配置")

    p_gen = sub.add_parser("generate", help="指定目标：拉数 → 写稿 → 草稿箱")
    _add_vertical_arg(p_gen)
    p_gen.add_argument("--code", required=True, help="stock 领域为股票代码")

    p_pub = sub.add_parser("publish", help="把已生成的本地文稿重新发到草稿箱")
    _add_vertical_arg(p_pub)
    p_pub.add_argument("--dir", type=Path)
    p_pub.add_argument("--code")

    p_fetch = sub.add_parser("fetch", help="仅拉公开数据（stock 领域调试用）")
    _add_vertical_arg(p_fetch)
    p_fetch.add_argument("--code", required=True)

    p_status = sub.add_parser("status", help="查看领域进度")
    _add_vertical_arg(p_status)
    p_status.add_argument("--all", action="store_true", help="列出全部领域状态")

    p_check = sub.add_parser("check-wechat", help="诊断出口 IP 与公众号白名单")
    _add_vertical_arg(p_check)

    p_reset = sub.add_parser("reset-registry", help="清空已写与失败记录")
    _add_vertical_arg(p_reset)

    sub.add_parser("verticals", help="列出可用内容领域")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "run":
            return _cmd_run(args.vertical, args.count)
        if args.cmd == "generate":
            return _cmd_generate(args.vertical, args.code)
        if args.cmd == "publish":
            return _cmd_publish(args.vertical, args.dir, args.code)
        if args.cmd == "fetch":
            return _cmd_fetch(args.vertical, args.code)
        if args.cmd == "status":
            return _cmd_status(args.vertical, args.all)
        if args.cmd == "check-wechat":
            return _cmd_check_wechat(args.vertical)
        if args.cmd == "reset-registry":
            return _cmd_reset_registry(args.vertical)
        if args.cmd == "verticals":
            return _cmd_verticals()
    except Exception as exc:  # noqa: BLE001
        logging.error("%s", exc)
        return 1
    return 0


def _cmd_run(vertical_id: str, count: int | None) -> int:
    settings = load_settings()
    config = load_vertical_config(vertical_id, settings)
    vertical = get_vertical(vertical_id)
    results = vertical.run_batch(settings, config, count)
    if not results:
        if not vertical.implemented:
            print(f"领域「{config.label}」尚未实现，无法运行。")
        else:
            print("本批没有成功写入任何草稿，请查看上方日志。")
        return 1
    for r in results:
        if r.get("status") == "ok":
            print(f"✓ {r['code']} {r.get('name', '')} → media_id={r['media_id']}")
    return 0


def _cmd_generate(vertical_id: str, code: str) -> int:
    settings = load_settings()
    config = load_vertical_config(vertical_id, settings)
    vertical = get_vertical(vertical_id)
    WeChatDraftPublisher(config).verify_connection()
    record = vertical.process_one(settings, config, code)
    print(
        f"已写入草稿箱 media_id={record['media_id']}，本地备份 {record['output_dir']}"
    )
    return 0


def _cmd_publish(vertical_id: str, article_dir: Path | None, code: str | None) -> int:
    settings = load_settings()
    config = load_vertical_config(vertical_id, settings)
    config.require_wechat()
    if article_dir is None:
        if not code:
            raise RuntimeError("请提供 --dir 或 --code")
        article_dir = resolve_article_dir(vertical_id, code)
    media_id = WeChatDraftPublisher(config).publish_from_dir(article_dir)
    print(f"公众号草稿 media_id: {media_id}")
    return 0


def _cmd_fetch(vertical_id: str, code: str) -> int:
    if vertical_id != "stock":
        raise RuntimeError("fetch 目前仅支持 stock 领域")
    config = load_vertical_config(vertical_id)
    snapshot = fetch_company(code)
    out = config.output_dir / snapshot.code
    out.mkdir(parents=True, exist_ok=True)
    path = out / "snapshot.json"
    path.write_text(json.dumps(snapshot.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写入 {path}")
    for item in snapshot.fetch_warnings:
        print(f"警告: {item}")
    return 0


def _cmd_status(vertical_id: str, show_all: bool) -> int:
    if show_all:
        for vertical in list_verticals():
            config = load_vertical_config(vertical.id)
            print(vertical.status(config))
            print()
        return 0
    config = load_vertical_config(vertical_id)
    vertical = get_vertical(vertical_id)
    print(vertical.status(config))
    return 0


def _cmd_reset_registry(vertical_id: str) -> int:
    config = load_vertical_config(vertical_id)
    if vertical_id != "stock":
        raise RuntimeError("reset-registry 目前仅支持 stock 领域")
    RegistryStore(config.registry_path, config.data_dir).clear_registry()
    print(f"已清空领域「{config.label}」的已写列表与失败记录。")
    return 0


def _cmd_check_wechat(vertical_id: str) -> int:
    config = load_vertical_config(vertical_id)
    config.require_wechat()
    ip = detect_outbound_ipv4()
    print(f"领域：{config.label}（{config.id}）")
    print(f"本机出口 IPv4：{ip or '探测失败'}")
    print(f"配置的 AppID：{config.wechat_app_id}")
    try:
        token = WeChatDraftPublisher(config).verify_connection()
        print(f"成功：access_token 已获取（前 8 位 {token[:8]}…）")
        print("白名单与 AppSecret 配置正常。")
        return 0
    except RuntimeError as exc:
        print(str(exc))
        return 1


def _cmd_verticals() -> int:
    for vertical in list_verticals():
        config = load_vertical_config(vertical.id)
        creds = "已配置" if config.wechat_app_id and config.wechat_app_secret else "未配置"
        impl = "已实现" if vertical.implemented else "待实现"
        print(f"{vertical.id:10}  {vertical.label}  [{impl}]  微信凭证：{creds}")
        print(f"             {vertical.description}")
        print(f"             输出目录：{config.output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

from __future__ import annotations

import logging
import json
import re
from pathlib import Path

import httpx

from aiticle.config import PLACEHOLDER_COVER, Settings
from aiticle.render import markdown_to_wechat_html
from aiticle.title import fit_wechat_title

# 强制走 IPv4，避免微信侧识别为 ::ffff:x.x.x.x 导致白名单偶发不通过
_HTTP_TRANSPORT = httpx.HTTPTransport(local_address="0.0.0.0")

logger = logging.getLogger(__name__)


def detect_outbound_ipv4() -> str | None:
    try:
        with httpx.Client(timeout=10.0, transport=_HTTP_TRANSPORT) as client:
            resp = client.get("https://api.ipify.org")
            text = resp.text.strip()
            return text if text else None
    except Exception:
        return None


def _parse_wechat_ip(errmsg: str) -> str | None:
    m = re.search(r"invalid ip (\d+\.\d+\.\d+\.\d+)", errmsg)
    return m.group(1) if m else None


class WeChatDraftPublisher:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        if not settings.wechat_app_id or not settings.wechat_app_secret:
            raise RuntimeError("未配置 WECHAT_APP_ID / WECHAT_APP_SECRET")

    def verify_connection(self) -> str:
        """校验凭证与 IP 白名单，成功返回 access_token。"""
        return self._token()

    def publish_from_dir(self, article_dir: Path) -> str:
        meta = json.loads((article_dir / "wechat_meta.json").read_text(encoding="utf-8"))
        markdown = (article_dir / "wechat.md").read_text(encoding="utf-8")
        lines = markdown.splitlines()
        if lines and lines[0].startswith("# "):
            markdown = "\n".join(lines[1:]).strip()
        html = markdown_to_wechat_html(markdown)
        cover = _resolve_cover(article_dir)
        token = self._token()
        thumb_id = self._upload_cover(token, cover)
        return self._add_draft(
            token,
            title=meta["title"],
            digest=meta.get("digest") or "",
            html=html,
            thumb_media_id=thumb_id,
        )

    def _http_client(self, timeout: float = 30.0) -> httpx.Client:
        return httpx.Client(timeout=timeout, transport=_HTTP_TRANSPORT)

    def _token(self) -> str:
        url = "https://api.weixin.qq.com/cgi-bin/token"
        params = {
            "grant_type": "client_credential",
            "appid": self.settings.wechat_app_id,
            "secret": self.settings.wechat_app_secret,
        }
        with self._http_client() as client:
            data = client.get(url, params=params).json()
        if "access_token" not in data:
            errcode = data.get("errcode")
            errmsg = data.get("errmsg", "")
            if errcode == 40164:
                wechat_ip = _parse_wechat_ip(errmsg) or "见 errmsg"
                local_ip = detect_outbound_ipv4()
                raise RuntimeError(
                    _whitelist_help(
                        wechat_ip=wechat_ip,
                        local_ip=local_ip,
                        app_id=self.settings.wechat_app_id,
                        raw=errmsg,
                    )
                )
            if errcode == 40125:
                raise RuntimeError(
                    "AppSecret 无效（40125）。请到 mp.weixin.qq.com → 设置与开发 → 基本配置 "
                    "→ 开发者密码(AppSecret) 重置，将新 Secret 写入 .env 的 WECHAT_APP_SECRET。"
                    f" 当前 AppID：{self.settings.wechat_app_id}"
                )
            raise RuntimeError(f"获取微信 access_token 失败: {data}")
        return data["access_token"]

    def _upload_cover(self, token: str, path: Path) -> str:
        url = "https://api.weixin.qq.com/cgi-bin/material/add_material"
        params = {"access_token": token, "type": "image"}
        with path.open("rb") as fh:
            files = {"media": (path.name, fh, "image/jpeg")}
            with self._http_client(timeout=60.0) as client:
                data = client.post(url, params=params, files=files).json()
        if "media_id" not in data:
            raise RuntimeError(f"上传封面失败: {data}")
        return data["media_id"]

    def _add_draft(self, token: str, *, title: str, digest: str, html: str, thumb_media_id: str) -> str:
        url = "https://api.weixin.qq.com/cgi-bin/draft/add"
        params = {"access_token": token}
        payload = {
            "articles": [
                {
                    "title": fit_wechat_title(title),
                    "digest": digest[:120],
                    "content": html,
                    "thumb_media_id": thumb_media_id,
                    "need_open_comment": 0,
                    "only_fans_can_comment": 0,
                }
            ]
        }
        # 不传 author：微信会同时显示作者名与可点击作者链接，造成「名字出现两次」
        with self._http_client(timeout=60.0) as client:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            data = client.post(
                url,
                params=params,
                content=body,
                headers={"Content-Type": "application/json; charset=utf-8"},
            ).json()
        if "media_id" not in data:
            raise RuntimeError(f"创建草稿失败: {data}")
        return data["media_id"]


def _resolve_cover(article_dir: Path) -> Path:
    """微信接口要求 thumb_media_id；若本地无 cover.jpg 则用灰色占位图。"""
    custom = article_dir / "cover.jpg"
    if custom.exists():
        return custom
    if not PLACEHOLDER_COVER.exists():
        raise RuntimeError(f"占位封面缺失: {PLACEHOLDER_COVER}")
    logger.info("未提供 cover.jpg，已用占位封面；请在微信草稿箱中自行上传替换")
    return PLACEHOLDER_COVER


def _whitelist_help(
    *,
    wechat_ip: str,
    local_ip: str | None,
    app_id: str,
    raw: str,
) -> str:
    lines = [
        f"微信仍判定 IP 不在白名单（errmsg: {raw}）",
        f"微信看到的出口 IP：{wechat_ip}",
    ]
    if local_ip:
        lines.append(f"本机探测到的出口 IPv4：{local_ip}")
        if local_ip != wechat_ip:
            lines.append("两者不一致时，白名单应填「微信看到的 IP」。")
    lines.extend(
        [
            f"当前 AppID：{app_id}",
            "",
            "请逐项核对：",
            "1. 登录 mp.weixin.qq.com → 设置与开发 → 基本配置 → IP白名单",
            "2. 白名单填纯 IPv4（如 183.242.40.67），不要带端口、不要填 ::ffff: 开头",
            "3. AppID 必须与 .env 中 WECHAT_APP_ID 完全一致",
            "4. 保存后等 5～60 分钟；有人反馈需「保存两次」才生效",
            "5. 上云后出口 IP 会变，要把云服务器的公网 IP 加入白名单",
            "6. errmsg 里的 ipv6 ::ffff:x.x.x.x 是同一 IPv4 的映射，不是第二个 IP",
        ]
    )
    return "\n".join(lines)

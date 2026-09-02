from __future__ import annotations

import json
import re

from aiticle.llm.deepseek import DeepSeekClient, find_forbidden
from aiticle.llm.prompts import SYSTEM_PROMPT, WECHAT_USER
from aiticle.models import CompanySnapshot, WechatArticle
from aiticle.title import finalize_wechat_title

# 导读式表述，正文不应出现
_GUIDE_PHRASES = (
    "指引",
    "建议查阅",
    "请投资者",
    "投资者应",
    "理性判断",
    "如需了解",
    "官方渠道",
    "巨潮资讯网查阅",
    "查阅指引",
)
FOOTER = "\n\n---\n本文仅供公司介绍参考，不构成投资建议。"

_DISCLAIMER_HEADING = re.compile(
    r"\n##\s*(数据出处与免责声明|免责声明|数据出处|风险提示与免责声明|数据出处与免责|风险与查阅指引|查阅指引)\s*\n[\s\S]*$",
    re.IGNORECASE,
)
_DISCLAIMER_TAIL = re.compile(
    r"\n+---\s*\n[\s\S]*?(不构成.*?投资建议[\s\S]*?)$",
    re.IGNORECASE,
)


def generate_wechat(client: DeepSeekClient, snapshot: CompanySnapshot) -> WechatArticle:
    payload = json.dumps(snapshot.to_prompt_dict(), ensure_ascii=False, indent=2)
    user_base = WECHAT_USER.format(payload=payload)
    last_error: Exception | None = None
    for _ in range(3):
        try:
            user = user_base
            if last_error:
                user += f"\n\n【修正要求】{last_error}"
            raw = client.complete_json(
                SYSTEM_PROMPT,
                user,
                max_tokens=8192,
            )
            article = _parse_article(raw, snapshot)
            if _is_list_dump(article.body_markdown):
                raise RuntimeError("文稿过于罗列数据，需改写为叙事体")
            guide_hits = _find_guide_phrases(article.body_markdown)
            if guide_hits:
                raise RuntimeError(f"文稿含导读表述（{', '.join(guide_hits)}），应改为纯介绍")
            return article
        except (RuntimeError, ValueError) as exc:
            last_error = exc
    raise last_error or RuntimeError("公众号文稿生成失败")


def _parse_article(raw: dict, snapshot: CompanySnapshot) -> WechatArticle:
    raw_title = str(raw.get("title") or "").strip()
    markdown = str(raw.get("markdown") or raw.get("body") or "").strip()
    digest = str(raw.get("digest") or "").strip()
    try:
        title = finalize_wechat_title(raw_title, name=snapshot.name or "", code=snapshot.code)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    markdown = _strip_disclaimer(markdown) + FOOTER
    hits = find_forbidden(title + "\n" + markdown)
    if hits:
        raise RuntimeError(f"文稿含禁止表述: {', '.join(hits)}，请改用客观数据表述")
    if not title or not markdown:
        raise RuntimeError("生成结果缺少标题或正文")
    return WechatArticle(title=title, digest=digest[:120], body_markdown=markdown)


def _strip_disclaimer(markdown: str) -> str:
    text = _DISCLAIMER_HEADING.sub("", markdown)
    text = _DISCLAIMER_TAIL.sub("", text)
    lines = text.splitlines()
    while lines:
        last = lines[-1].strip()
        if not last:
            lines.pop()
            continue
        if any(k in last for k in ("不构成", "投资建议", "投资需谨慎", "风险自担", "数据来源", "数据来源于", "公开披露")):
            lines.pop()
            continue
        break
    return "\n".join(lines).rstrip()


def _is_list_dump(markdown: str) -> bool:
    """拒绝公告标题清单式、字段罗列式正文。"""
    lines = markdown.splitlines()
    bullets = sum(1 for line in lines if re.match(r"^\s*[-*]\s+\S", line))
    numbered = sum(1 for line in lines if re.match(r"^\s*\d+\.\s+\S", line))
    list_lines = bullets + numbered
    non_empty = sum(1 for line in lines if line.strip())
    if list_lines >= 10:
        return True
    if non_empty and list_lines / non_empty > 0.35:
        return True
    return False


def _find_guide_phrases(text: str) -> list[str]:
    body = text.split("---")[0]
    return [p for p in _GUIDE_PHRASES if p in body]

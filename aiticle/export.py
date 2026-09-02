from __future__ import annotations

import json
from pathlib import Path

from aiticle.config import OUTPUT_DIR
from aiticle.models import CompanySnapshot, WechatArticle
from aiticle.render import markdown_to_wechat_html


def export_wechat(snapshot: CompanySnapshot, article: WechatArticle) -> Path:
    out = OUTPUT_DIR / snapshot.code
    out.mkdir(parents=True, exist_ok=True)
    (out / "snapshot.json").write_text(
        json.dumps(snapshot.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    path = out / "wechat.md"
    path.write_text(f"# {article.title}\n\n{article.body_markdown.strip()}\n", encoding="utf-8")
    (out / "wechat.html").write_text(
        markdown_to_wechat_html(article.body_markdown),
        encoding="utf-8",
    )
    (out / "wechat_meta.json").write_text(
        json.dumps(
            {"title": article.title, "digest": article.digest, "author": ""},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return out

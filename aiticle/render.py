from __future__ import annotations

import re

import markdown

_SECTION = (
    "font-size:16px;line-height:1.9;color:#333;"
)

_H2_STYLE = (
    "font-size:19px;font-weight:bold;color:#1a1a1a;"
    "margin:32px 0 14px;padding-bottom:8px;"
    "border-bottom:2px solid #d4d4d4;line-height:1.4;"
)

_H3_STYLE = (
    "font-size:17px;font-weight:bold;color:#2d2d2d;"
    "margin:24px 0 12px;line-height:1.4;"
)

_P_STYLE = (
    "margin:0 0 16px;text-indent:2em;line-height:1.9;color:#333;"
)

_TABLE_WRAP = "margin:16px 0;text-indent:0;"
_TABLE_STYLE = (
    "width:100%;border-collapse:collapse;font-size:14px;line-height:1.6;"
)
_TH_STYLE = (
    "border:1px solid #ddd;padding:8px 6px;background:#f5f5f5;"
    "font-weight:bold;text-align:center;"
)
_TD_STYLE = "border:1px solid #ddd;padding:8px 6px;text-align:center;"
_HR_STYLE = "border:none;border-top:1px solid #e0e0e0;margin:28px 0;"
_FOOTER_STYLE = (
    "margin:0;text-indent:0;font-size:14px;color:#888;line-height:1.7;"
)


def markdown_to_wechat_html(md_text: str) -> str:
    body, footer = _split_footer(md_text)
    html = markdown.markdown(
        body,
        extensions=["tables", "sane_lists"],
    )
    html = _style_wechat_html(html)
    if footer:
        html += (
            f'<hr style="{_HR_STYLE}"/>'
            f'<p style="{_FOOTER_STYLE}">{footer}</p>'
        )
    return f'<section style="{_SECTION}">{html}</section>'


def _split_footer(md_text: str) -> tuple[str, str | None]:
    """免责声明单独渲染，段首不缩进。"""
    parts = re.split(r"\n+---\s*\n+", md_text.strip(), maxsplit=1)
    if len(parts) == 2:
        footer = parts[1].strip()
        if footer:
            return parts[0].strip(), footer
    return md_text.strip(), None


def _style_wechat_html(html: str) -> str:
    html = re.sub(
        r"<h2>(.*?)</h2>",
        lambda m: f'<h2 style="{_H2_STYLE}">{m.group(1)}</h2>',
        html,
        flags=re.DOTALL,
    )
    html = re.sub(
        r"<h3>(.*?)</h3>",
        lambda m: f'<h3 style="{_H3_STYLE}">{m.group(1)}</h3>',
        html,
        flags=re.DOTALL,
    )
    html = re.sub(r"<p>", f'<p style="{_P_STYLE}">', html)
    html = re.sub(
        r"<table>",
        f'<div style="{_TABLE_WRAP}"><table style="{_TABLE_STYLE}">',
        html,
    )
    html = html.replace("</table>", "</table></div>")
    html = re.sub(
        r"<th>",
        f'<th style="{_TH_STYLE}">',
        html,
    )
    html = re.sub(
        r"<td>",
        f'<td style="{_TD_STYLE}">',
        html,
    )
    html = re.sub(
        r"<hr\s*/?>",
        f'<hr style="{_HR_STYLE}"/>',
        html,
    )
    return html

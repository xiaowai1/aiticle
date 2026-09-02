from __future__ import annotations

import logging
import math
import time
from datetime import date, datetime, timedelta
from typing import Any, Callable

import pandas as pd

from aiticle.models import (
    Announcement,
    CompanySnapshot,
    DividendRecord,
    InstitutionalHolding,
    MarketQuote,
    PeriodMetrics,
    PriceTrend,
    ResearchReport,
    RestrictedUnlock,
    Segment,
    Shareholder,
)

logger = logging.getLogger(__name__)

CNINFO_COMPANY = "http://webapi.cninfo.com.cn/#/company"


def normalize_code(code: str) -> str:
    digits = "".join(ch for ch in code.strip() if ch.isdigit())
    if len(digits) not in {5, 6}:
        raise ValueError(f"无效股票代码: {code}")
    return digits.zfill(6)


def to_em_symbol(code: str) -> str:
    code = normalize_code(code)
    if code.startswith(("6", "9")):
        return f"SH{code}"
    if code.startswith(("4", "8")):
        return f"BJ{code}"
    return f"SZ{code}"


def to_dot_symbol(code: str) -> str:
    em = to_em_symbol(code)
    return f"{em[2:]}.{em[:2]}"


def _to_sina_symbol(code: str) -> str:
    code = normalize_code(code)
    if code.startswith(("6", "9")):
        return f"sh{code}"
    return f"sz{code}"


def _safe_call(
    label: str,
    fn: Callable[[], Any],
    warnings: list[str],
    retries: int | None = None,
    required: bool = False,
) -> Any | None:
    max_attempts = retries if retries is not None else (3 if required else 1)
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning("%s 第 %s 次失败: %s", label, attempt, exc)
            time.sleep(2.0 * attempt)
    msg = f"{label} 获取失败: {last_exc}"
    if required:
        raise RuntimeError(msg)
    logger.warning(msg)
    warnings.append(msg)
    return None


def _pause() -> None:
    time.sleep(0.8)


def _cell(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if pd.isna(value):
        return None
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return pd.Timestamp(value).strftime("%Y-%m-%d")
    text = str(value).strip()
    return text or None


def _fmt_yi(value: Any) -> str | None:
    try:
        if value is None or pd.isna(value):
            return None
        num = float(value)
    except (TypeError, ValueError):
        return _cell(value)
    if math.isnan(num) or math.isinf(num):
        return None
    abs_num = abs(num)
    if abs_num >= 1e8:
        return f"{num / 1e8:.2f}亿元"
    if abs_num >= 1e4:
        return f"{num / 1e4:.2f}万元"
    return f"{num:.2f}元"


def _fmt_per_share(value: Any) -> str | None:
    try:
        if value is None or pd.isna(value):
            return None
        num = float(value)
    except (TypeError, ValueError):
        return _cell(value)
    if math.isnan(num) or math.isinf(num):
        return None
    return f"{num:.2f}元/股"


def _fmt_pct(value: Any) -> str | None:
    try:
        if value is None or pd.isna(value):
            return None
        num = float(value)
    except (TypeError, ValueError):
        return _cell(value)
    if math.isnan(num) or math.isinf(num):
        return None
    return f"{num:.2f}%"


def _fmt_ratio_as_pct(value: Any) -> str | None:
    try:
        if value is None or pd.isna(value):
            return None
        num = float(value)
    except (TypeError, ValueError):
        return _cell(value)
    if math.isnan(num) or math.isinf(num):
        return None
    if abs(num) <= 1.5:
        num *= 100
    return f"{num:.2f}%"


def _series_map(df: pd.DataFrame) -> dict[str, Any]:
    if df is None or df.empty:
        return {}
    if {"item", "value"}.issubset({c.lower() for c in df.columns}):
        item_col = next(c for c in df.columns if c.lower() == "item")
        value_col = next(c for c in df.columns if c.lower() == "value")
        return {str(k).strip(): v for k, v in zip(df[item_col], df[value_col])}
    row = df.iloc[0].to_dict()
    return {str(k): v for k, v in row.items()}


def _first_col(row: pd.Series, names: list[str]) -> Any:
    lower = {str(c).lower(): c for c in row.index}
    for name in names:
        if name in row.index:
            return row[name]
        key = name.lower()
        if key in lower:
            return row[lower[key]]
    return None


def fetch_company(code: str) -> CompanySnapshot:
    import akshare as ak

    code = normalize_code(code)
    em_symbol = to_em_symbol(code)
    warnings: list[str] = []
    sources: list[str] = []

    snapshot = CompanySnapshot(code=code, em_symbol=em_symbol)

    profile_df = _safe_call(
        "巨潮公司概况",
        lambda: ak.stock_profile_cninfo(symbol=code),
        warnings,
        required=True,
    )
    _pause()
    if profile_df is not None and not profile_df.empty:
        row = profile_df.iloc[0]
        snapshot.full_name = _cell(row.get("公司名称"))
        snapshot.name = _cell(row.get("A股简称")) or snapshot.name
        snapshot.industry = _cell(row.get("所属行业"))
        snapshot.market = _cell(row.get("所属市场"))
        snapshot.establish_date = _cell(row.get("成立日期"))
        snapshot.list_date = _cell(row.get("上市日期"))
        snapshot.website = _cell(row.get("官方网站"))
        snapshot.office_address = _cell(row.get("办公地址")) or _cell(row.get("注册地址"))
        snapshot.legal_person = _cell(row.get("法人代表"))
        snapshot.main_business = _cell(row.get("主营业务"))
        snapshot.business_scope = _cell(row.get("经营范围"))
        snapshot.profile = _cell(row.get("机构简介"))
        sources.append("巨潮资讯-公司概况")

    zygc_df = _safe_call(
        "东方财富主营构成",
        lambda: ak.stock_zygc_em(symbol=em_symbol),
        warnings,
    )
    if zygc_df is not None and not zygc_df.empty:
        latest = str(zygc_df["报告日期"].max())
        latest_df = zygc_df[zygc_df["报告日期"].astype(str) == latest]
        snapshot.product_segments = _segments(latest_df, "按产品分类")
        snapshot.region_segments = _segments(latest_df, "按地区分类")
        snapshot.industry_segments = _segments(latest_df, "按行业分类")
        if not snapshot.industry_segments:
            unnamed = latest_df[latest_df["分类类型"].isna()]
            snapshot.industry_segments = _segments_from_frame(unnamed)
        sources.append(f"东方财富-主营构成（报告期 {latest[:10]}）")
    _pause()

    indicator_df = _safe_call(
        "东方财富财务指标",
        lambda: ak.stock_financial_analysis_indicator_em(
            symbol=to_dot_symbol(code),
            indicator="按报告期",
        ),
        warnings,
    )
    if indicator_df is not None and not indicator_df.empty:
        snapshot.periods = _periods_from_indicators(indicator_df)
        sources.append("东方财富-财务分析主要指标")
    _pause()

    if not snapshot.periods:
        profit_df = _safe_call(
            "东方财富利润表",
            lambda: ak.stock_profit_sheet_by_report_em(symbol=em_symbol),
            warnings,
        )
        cash_df = _safe_call(
            "东方财富现金流量表",
            lambda: ak.stock_cash_flow_sheet_by_report_em(symbol=em_symbol),
            warnings,
        )
        snapshot.periods = _periods_from_statements(profit_df, cash_df)
        if snapshot.periods:
            sources.append("东方财富-利润表/现金流量表")
    _pause()

    end = date.today()
    start = end - timedelta(days=365)
    notice_df = _safe_call(
        "巨潮公告",
        lambda: ak.stock_zh_a_disclosure_report_cninfo(
            symbol=code,
            market="沪深京",
            keyword="",
            category="",
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
        ),
        warnings,
    )
    if notice_df is not None and not notice_df.empty:
        snapshot.announcements = []
        for _, row in notice_df.head(12).iterrows():
            title = _cell(row.get("公告标题"))
            if not title:
                continue
            snapshot.announcements.append(
                Announcement(
                    date=_cell(row.get("公告时间")) or "",
                    title=title,
                    url=_cell(row.get("公告链接")),
                )
            )
        sources.append("巨潮资讯-信息披露公告")
    _pause()

    _enrich_market_and_traders(snapshot, code, warnings, sources)
    _pause()

    snapshot.sources = sources
    snapshot.fetch_warnings = warnings
    if not snapshot.name:
        snapshot.name = code
    snapshot.sources.append(CNINFO_COMPANY)
    return snapshot


def _enrich_market_and_traders(
    snapshot: CompanySnapshot,
    code: str,
    warnings: list[str],
    sources: list[str],
) -> None:
    import akshare as ak

    value_df = _safe_call(
        "东财估值行情",
        lambda: ak.stock_value_em(symbol=code),
        warnings,
    )
    if value_df is not None and not value_df.empty:
        row = value_df.iloc[-1]
        snapshot.market_quote = MarketQuote(
            as_of=_cell(row.get("数据日期")),
            close_price=_fmt_price(row.get("当日收盘价")),
            change_pct=_fmt_pct(row.get("当日涨跌幅")),
            total_market_cap=_fmt_market_cap(row.get("总市值")),
            float_market_cap=_fmt_market_cap(row.get("流通市值")),
            pe_ttm=_fmt_ratio_number(row.get("PE(TTM)")),
            pe_static=_fmt_ratio_number(row.get("PE(静)")),
            pb=_fmt_ratio_number(row.get("市净率")),
            ps=_fmt_ratio_number(row.get("市销率")),
        )
        sources.append("东方财富-个股估值")

    end = date.today()
    start = end - timedelta(days=90)
    daily_df = _safe_call(
        "新浪日行情",
        lambda: ak.stock_zh_a_daily(
            symbol=_to_sina_symbol(code),
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
            adjust="qfq",
        ),
        warnings,
    )
    if daily_df is not None and not daily_df.empty:
        snapshot.price_trend = _price_trend_from_daily(daily_df)
        if snapshot.price_trend:
            sources.append("新浪财经-日行情")

    holder_df = _safe_call(
        "新浪流通股东",
        lambda: ak.stock_circulate_stock_holder(symbol=code),
        warnings,
    )
    if holder_df is not None and not holder_df.empty:
        as_of = holder_df["截止日期"].max()
        part = holder_df[holder_df["截止日期"] == as_of].head(5)
        snapshot.top_shareholders = [
            Shareholder(
                name=str(row["股东名称"]).strip(),
                shares=_fmt_share_count(row.get("持股数量")),
                ratio=_fmt_ratio_as_pct(row.get("占流通股比例")),
                as_of=_cell(as_of),
            )
            for _, row in part.iterrows()
            if _cell(row.get("股东名称"))
        ]
        if snapshot.top_shareholders:
            sources.append(f"新浪财经-十大流通股东（截至 {str(as_of)[:10]}）")

    inst_df = _fetch_institute_hold(code, warnings)
    if inst_df is not None and not inst_df.empty:
        snapshot.institutional_holdings = [
            InstitutionalHolding(
                name=str(row.get("持股机构简称") or row.get("持股机构全称") or "").strip(),
                shares=_fmt_share_count(row.get("最新持股数") or row.get("持股数")),
                ratio=_fmt_ratio_as_pct(row.get("最新占流通股比例") or row.get("占流通股比例")),
            )
            for _, row in inst_df.head(6).iterrows()
            if _cell(row.get("持股机构简称") or row.get("持股机构全称"))
        ]
        if snapshot.institutional_holdings:
            sources.append("东方财富-机构持股")

    report_df = _safe_call(
        "个股研报",
        lambda: ak.stock_research_report_em(symbol=code),
        warnings,
    )
    if report_df is not None and not report_df.empty:
        snapshot.research_reports = []
        for _, row in report_df.head(6).iterrows():
            title = _cell(row.get("报告名称"))
            if not title:
                continue
            title = _scrub_rating_words(title)
            snapshot.research_reports.append(
                ResearchReport(
                    date=_cell(row.get("日期")) or "",
                    title=title,
                    org=_cell(row.get("机构")),
                )
            )
        if snapshot.research_reports:
            sources.append("东方财富-个股研报")

    div_df = _safe_call(
        "同花顺分红",
        lambda: ak.stock_fhps_detail_ths(symbol=code),
        warnings,
    )
    if div_df is not None and not div_df.empty:
        snapshot.dividends_recent = []
        for _, row in div_df.head(5).iterrows():
            snapshot.dividends_recent.append(
                DividendRecord(
                    report_period=_cell(row.get("报告期")),
                    announce_date=_cell(row.get("实施公告日") or row.get("董事会日期")),
                    plan=_cell(row.get("分红方案说明")),
                )
            )
        if snapshot.dividends_recent:
            sources.append("同花顺-分红详情")

    unlock_df = _safe_call(
        "限售解禁",
        lambda: ak.stock_restricted_release_queue_em(symbol=code),
        warnings,
    )
    if unlock_df is not None and not unlock_df.empty:
        snapshot.restricted_unlocks = []
        for _, row in unlock_df.head(4).iterrows():
            snapshot.restricted_unlocks.append(
                RestrictedUnlock(
                    unlock_date=_cell(row.get("解禁时间")),
                    ratio=_fmt_ratio_as_pct(row.get("占总市值比例") or row.get("占流通市值比例")),
                    type_label=_cell(row.get("限售股类型")),
                )
            )
        if snapshot.restricted_unlocks:
            sources.append("东方财富-限售解禁")

    lhb_df = _safe_call(
        "龙虎榜日期",
        lambda: ak.stock_lhb_stock_detail_date_em(symbol=code),
        warnings,
    )
    if lhb_df is not None and not lhb_df.empty:
        dates = [_cell(row.get("交易日")) for _, row in lhb_df.head(5).iterrows()]
        snapshot.lhb_dates = [d for d in dates if d]
        if snapshot.lhb_dates:
            sources.append("东方财富-龙虎榜上榜日期")


_RATING_WORDS = (
    "买入",
    "卖出",
    "增持",
    "减持",
    "强烈推荐",
    "低估",
    "高估",
    "目标价",
)


def _scrub_rating_words(text: str) -> str:
    for word in _RATING_WORDS:
        text = text.replace(word, "")
    return text.strip()


def _fetch_institute_hold(code: str, warnings: list[str]) -> pd.DataFrame | None:
    import akshare as ak

    today = date.today()
    quarter = (today.month - 1) // 3 + 1
    candidates = [f"{today.year}{quarter}"]
    if quarter > 1:
        candidates.append(f"{today.year}{quarter - 1}")
    else:
        candidates.append(f"{today.year - 1}4")
    for q in candidates:
        df = _safe_call(
            f"机构持股({q})",
            lambda quarter=q: ak.stock_institute_hold_detail(stock=code, quarter=quarter),
            warnings,
            retries=1,
        )
        if df is not None and not df.empty:
            return df
    return None


def _fmt_price(value: Any) -> str | None:
    try:
        if value is None or pd.isna(value):
            return None
        num = float(value)
        if math.isnan(num) or math.isinf(num):
            return None
        return f"{num:.2f}元"
    except (TypeError, ValueError):
        return _cell(value)


def _fmt_market_cap(value: Any) -> str | None:
    try:
        if value is None or pd.isna(value):
            return None
        num = float(value)
        if math.isnan(num) or math.isinf(num):
            return None
        if abs(num) >= 1e8:
            return f"{num / 1e8:.2f}亿元"
        return f"{num:.2f}元"
    except (TypeError, ValueError):
        return _cell(value)


def _fmt_ratio_number(value: Any) -> str | None:
    try:
        if value is None or pd.isna(value):
            return None
        num = float(value)
        if math.isnan(num) or math.isinf(num):
            return None
        return f"{num:.2f}"
    except (TypeError, ValueError):
        return _cell(value)


def _fmt_share_count(value: Any) -> str | None:
    try:
        if value is None or pd.isna(value):
            return None
        num = float(value)
        if math.isnan(num) or math.isinf(num):
            return None
        if abs(num) >= 1e8:
            return f"{num / 1e8:.2f}亿股"
        if abs(num) >= 1e4:
            return f"{num / 1e4:.2f}万股"
        return f"{num:.0f}股"
    except (TypeError, ValueError):
        return _cell(value)


def _price_trend_from_daily(df: pd.DataFrame) -> PriceTrend | None:
    if df is None or df.empty:
        return None
    ordered = df.sort_values("date")
    first = ordered.iloc[0]
    last = ordered.iloc[-1]
    try:
        start_close = float(first["close"])
        end_close = float(last["close"])
        change = (end_close / start_close - 1) * 100 if start_close else None
    except (TypeError, ValueError, KeyError):
        start_close = None
        end_close = None
        change = None
    turnover = None
    if "turnover" in ordered.columns:
        try:
            turnover = float(ordered["turnover"].mean()) * 100
        except (TypeError, ValueError):
            turnover = None
    high = _fmt_price(ordered["high"].max()) if "high" in ordered.columns else None
    low = _fmt_price(ordered["low"].min()) if "low" in ordered.columns else None
    return PriceTrend(
        window="近约三个月",
        start_date=_cell(first.get("date")),
        end_date=_cell(last.get("date")),
        start_close=_fmt_price(start_close) if start_close is not None else None,
        end_close=_fmt_price(end_close) if end_close is not None else None,
        change_pct=_fmt_pct(change) if change is not None else None,
        period_high=high,
        period_low=low,
        avg_turnover_rate=_fmt_pct(turnover) if turnover is not None else None,
    )


def _segments(df: pd.DataFrame, kind: str) -> list[Segment]:
    if "分类类型" not in df.columns:
        return []
    part = df[df["分类类型"] == kind]
    return _segments_from_frame(part)


def _segments_from_frame(df: pd.DataFrame) -> list[Segment]:
    items: list[Segment] = []
    if df is None or df.empty:
        return items
    ranked = df.copy()
    if "收入比例" in ranked.columns:
        ranked = ranked.sort_values("收入比例", ascending=False)
    for _, row in ranked.head(6).iterrows():
        name = _cell(row.get("主营构成"))
        if not name or name in {"其他", "其他(补充)", "其他主营"}:
            continue
        items.append(
            Segment(
                name=name,
                revenue=_fmt_yi(row.get("主营收入")),
                revenue_ratio=_fmt_ratio_as_pct(row.get("收入比例")),
                gross_margin=_fmt_ratio_as_pct(row.get("毛利率")),
            )
        )
    return items


def _periods_from_indicators(df: pd.DataFrame) -> list[PeriodMetrics]:
    ordered = df.copy()
    if "REPORT_DATE" in ordered.columns:
        ordered = ordered.sort_values("REPORT_DATE", ascending=False)
    periods: list[PeriodMetrics] = []
    for _, row in ordered.head(4).iterrows():
        period = _cell(_first_col(row, ["REPORT_DATE", "报告日期"]))
        if not period:
            continue
        periods.append(
            PeriodMetrics(
                period=period[:10],
                report_type=_cell(_first_col(row, ["REPORT_DATE_NAME", "REPORT_TYPE"])),
                revenue=_fmt_yi(_first_col(row, ["TOTALOPERATEREVE"])),
                revenue_yoy=_fmt_pct(_first_col(row, ["TOTALOPERATEREVETZ"])),
                net_profit=_fmt_yi(_first_col(row, ["PARENTNETPROFIT"])),
                net_profit_yoy=_fmt_pct(_first_col(row, ["PARENTNETPROFITTZ"])),
                gross_margin=_fmt_pct(_first_col(row, ["XSMLL"])),
                net_margin=_fmt_pct(_first_col(row, ["XSJLL"])),
                roe=_fmt_pct(_first_col(row, ["ROEJQ"])),
                operating_cash_flow=_fmt_per_share(_first_col(row, ["MGJYXJJE"])),
                asset_liability_ratio=_fmt_pct(_first_col(row, ["ZCFZL"])),
            )
        )
    return periods


def _periods_from_statements(
    profit_df: pd.DataFrame | None,
    cash_df: pd.DataFrame | None,
) -> list[PeriodMetrics]:
    if profit_df is None or profit_df.empty:
        return []
    cash_map: dict[str, Any] = {}
    if cash_df is not None and not cash_df.empty:
        date_col = "REPORT_DATE" if "REPORT_DATE" in cash_df.columns else cash_df.columns[0]
        for _, row in cash_df.iterrows():
            key = str(_first_col(row, ["REPORT_DATE"]) or "")[:10]
            cash_map[key] = _first_col(
                row,
                ["NETCASH_OPERATE", "NET_CASH_FLOWS_FROM_OPERATING", "经营性现金流净额"],
            )
    ordered = profit_df.copy()
    if "REPORT_DATE" in ordered.columns:
        ordered = ordered.sort_values("REPORT_DATE", ascending=False)
    periods: list[PeriodMetrics] = []
    for _, row in ordered.head(4).iterrows():
        period = _cell(_first_col(row, ["REPORT_DATE"]))
        if not period:
            continue
        key = period[:10]
        periods.append(
            PeriodMetrics(
                period=key,
                report_type=_cell(_first_col(row, ["REPORT_DATE_NAME", "REPORT_TYPE"])),
                revenue=_fmt_yi(
                    _first_col(row, ["TOTAL_OPERATE_INCOME", "OPERATE_INCOME", "营业总收入", "营业收入"])
                ),
                net_profit=_fmt_yi(
                    _first_col(row, ["PARENT_NETPROFIT", "NETPROFIT", "归属于母公司股东的净利润", "净利润"])
                ),
                operating_cash_flow=_fmt_yi(cash_map.get(key)),
            )
        )
    return periods

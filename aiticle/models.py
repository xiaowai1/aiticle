from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Segment(BaseModel):
    name: str
    revenue: str | None = None
    revenue_ratio: str | None = None
    gross_margin: str | None = None


class PeriodMetrics(BaseModel):
    period: str
    report_type: str | None = None
    revenue: str | None = None
    revenue_yoy: str | None = None
    net_profit: str | None = None
    net_profit_yoy: str | None = None
    gross_margin: str | None = None
    net_margin: str | None = None
    roe: str | None = None
    operating_cash_flow: str | None = None
    asset_liability_ratio: str | None = None


class Announcement(BaseModel):
    date: str
    title: str
    url: str | None = None


class MarketQuote(BaseModel):
    as_of: str | None = None
    close_price: str | None = None
    change_pct: str | None = None
    total_market_cap: str | None = None
    float_market_cap: str | None = None
    pe_ttm: str | None = None
    pe_static: str | None = None
    pb: str | None = None
    ps: str | None = None


class PriceTrend(BaseModel):
    window: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    start_close: str | None = None
    end_close: str | None = None
    change_pct: str | None = None
    period_high: str | None = None
    period_low: str | None = None
    avg_turnover_rate: str | None = None


class Shareholder(BaseModel):
    name: str
    shares: str | None = None
    ratio: str | None = None
    as_of: str | None = None


class InstitutionalHolding(BaseModel):
    name: str
    shares: str | None = None
    ratio: str | None = None


class ResearchReport(BaseModel):
    date: str
    title: str
    org: str | None = None


class DividendRecord(BaseModel):
    report_period: str | None = None
    announce_date: str | None = None
    plan: str | None = None


class RestrictedUnlock(BaseModel):
    unlock_date: str | None = None
    ratio: str | None = None
    type_label: str | None = None


class CompanySnapshot(BaseModel):
    code: str
    em_symbol: str
    name: str | None = None
    full_name: str | None = None
    industry: str | None = None
    market: str | None = None
    list_date: str | None = None
    establish_date: str | None = None
    website: str | None = None
    office_address: str | None = None
    legal_person: str | None = None
    main_business: str | None = None
    business_scope: str | None = None
    profile: str | None = None
    total_share: str | None = None
    product_segments: list[Segment] = Field(default_factory=list)
    region_segments: list[Segment] = Field(default_factory=list)
    industry_segments: list[Segment] = Field(default_factory=list)
    periods: list[PeriodMetrics] = Field(default_factory=list)
    announcements: list[Announcement] = Field(default_factory=list)
    market_quote: MarketQuote | None = None
    price_trend: PriceTrend | None = None
    top_shareholders: list[Shareholder] = Field(default_factory=list)
    institutional_holdings: list[InstitutionalHolding] = Field(default_factory=list)
    research_reports: list[ResearchReport] = Field(default_factory=list)
    dividends_recent: list[DividendRecord] = Field(default_factory=list)
    restricted_unlocks: list[RestrictedUnlock] = Field(default_factory=list)
    lhb_dates: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    fetch_warnings: list[str] = Field(default_factory=list)

    def to_prompt_dict(self) -> dict[str, Any]:
        return self.model_dump()


class WechatArticle(BaseModel):
    title: str
    digest: str = ""
    body_markdown: str

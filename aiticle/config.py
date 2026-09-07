from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"
DATA_DIR = ROOT / "data"
# 微信草稿 API 必填封面；仅占位，请在草稿箱里自行替换
PLACEHOLDER_COVER = Path(__file__).resolve().parent / "assets" / "placeholder_cover.jpg"

DEFAULT_VERTICAL = "stock"


class VerticalMeta(BaseModel):
    id: str
    label: str
    description: str
    implemented: bool
    env_prefix: str = ""


VERTICAL_REGISTRY: dict[str, VerticalMeta] = {
    "stock": VerticalMeta(
        id="stock",
        label="A股公司介绍",
        description="沪深京 A 股上市公司公开资料介绍",
        implemented=True,
        env_prefix="",
    ),
    "reserved": VerticalMeta(
        id="reserved",
        label="预留领域",
        description="第二个公众号草稿箱，内容待配置",
        implemented=False,
        env_prefix="VERTICAL_RESERVED_",
    ),
}


class VerticalConfig(BaseModel):
    """单个内容领域的运行时配置（路径、微信凭证、批量大小）。"""

    id: str
    label: str
    description: str
    implemented: bool
    wechat_app_id: str
    wechat_app_secret: str
    batch_count: int
    output_dir: Path
    data_dir: Path
    registry_path: Path
    daily_log_path: Path

    def require_wechat(self) -> None:
        if not self.wechat_app_id or not self.wechat_app_secret:
            raise RuntimeError(
                f"领域「{self.label}」未配置微信公众号凭证（{self.id}）。"
            )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com"

    wechat_app_id: str = ""
    wechat_app_secret: str = ""
    wechat_author: str = Field(default="")

    daily_company_count: int = Field(default=1, validation_alias="DAILY_COMPANY_COUNT")

    # 预留领域微信凭证（第二个公众号）
    vertical_reserved_wechat_app_id: str = Field(default="", validation_alias="VERTICAL_RESERVED_WECHAT_APP_ID")
    vertical_reserved_wechat_app_secret: str = Field(
        default="", validation_alias="VERTICAL_RESERVED_WECHAT_APP_SECRET"
    )
    vertical_reserved_daily_count: int = Field(default=1, validation_alias="VERTICAL_RESERVED_DAILY_COUNT")

    def require_deepseek(self) -> None:
        if not self.deepseek_api_key:
            raise RuntimeError("未配置 DEEPSEEK_API_KEY，请复制 .env.example 为 .env 并填入密钥。")

    def require_wechat(self) -> None:
        if not self.wechat_app_id or not self.wechat_app_secret:
            raise RuntimeError("未配置 WECHAT_APP_ID / WECHAT_APP_SECRET。")


def load_settings() -> Settings:
    return Settings()


def _resolve_stock_registry_path() -> Path:
    new = DATA_DIR / "stock" / "written_registry.json"
    old = DATA_DIR / "written_registry.json"
    if not new.exists() and old.exists():
        return old
    return new


def load_vertical_config(vertical_id: str, settings: Settings | None = None) -> VerticalConfig:
    if vertical_id not in VERTICAL_REGISTRY:
        ids = ", ".join(VERTICAL_REGISTRY.keys())
        raise RuntimeError(f"未知领域「{vertical_id}」，可用：{ids}")

    base = settings or load_settings()
    meta = VERTICAL_REGISTRY[vertical_id]

    if vertical_id == "stock":
        app_id = base.wechat_app_id
        app_secret = base.wechat_app_secret
        batch_count = base.daily_company_count
        registry_path = _resolve_stock_registry_path()
    else:
        app_id = base.vertical_reserved_wechat_app_id
        app_secret = base.vertical_reserved_wechat_app_secret
        batch_count = base.vertical_reserved_daily_count
        registry_path = DATA_DIR / vertical_id / "written_registry.json"

    data_dir = registry_path.parent
    output_dir = OUTPUT_DIR / vertical_id

    return VerticalConfig(
        id=meta.id,
        label=meta.label,
        description=meta.description,
        implemented=meta.implemented,
        wechat_app_id=app_id,
        wechat_app_secret=app_secret,
        batch_count=batch_count,
        output_dir=output_dir,
        data_dir=data_dir,
        registry_path=registry_path,
        daily_log_path=data_dir / "daily_runs.jsonl",
    )


def resolve_article_dir(vertical_id: str, code: str) -> Path:
    """文章输出目录；stock 领域兼容旧版 output/<代码> 路径。"""
    from aiticle.data.fetcher import normalize_code

    code = normalize_code(code)
    new = OUTPUT_DIR / vertical_id / code
    if new.exists():
        return new
    if vertical_id == "stock":
        legacy = OUTPUT_DIR / code
        if legacy.exists():
            return legacy
    return new

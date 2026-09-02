from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"
DATA_DIR = ROOT / "data"
# 微信草稿 API 必填封面；仅占位，请在草稿箱里自行替换
PLACEHOLDER_COVER = Path(__file__).resolve().parent / "assets" / "placeholder_cover.jpg"


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

    def require_deepseek(self) -> None:
        if not self.deepseek_api_key:
            raise RuntimeError("未配置 DEEPSEEK_API_KEY，请复制 .env.example 为 .env 并填入密钥。")

    def require_wechat(self) -> None:
        if not self.wechat_app_id or not self.wechat_app_secret:
            raise RuntimeError("未配置 WECHAT_APP_ID / WECHAT_APP_SECRET。")


def load_settings() -> Settings:
    return Settings()

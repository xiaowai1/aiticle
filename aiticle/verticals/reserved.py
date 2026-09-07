from __future__ import annotations

from aiticle.config import Settings, VerticalConfig
from aiticle.verticals.base import Vertical


class ReservedVertical(Vertical):
    """第二个公众号槽位：内容领域与提示词待后续配置。"""

    id = "reserved"
    label = "预留领域"
    description = "第二个公众号草稿箱；内容生成逻辑待配置"
    implemented = False

    def run_batch(
        self,
        settings: Settings,
        config: VerticalConfig,
        count: int | None,
    ) -> list[dict]:
        self.require_ready(config)
        return []

    def process_one(
        self,
        settings: Settings,
        config: VerticalConfig,
        target: str,
        *,
        name: str = "",
    ) -> dict:
        self.require_ready(config)
        return {}

    def status(self, config: VerticalConfig) -> str:
        creds = "已配置" if config.wechat_app_id and config.wechat_app_secret else "未配置"
        return (
            f"领域：{self.label}（{self.id}）\n"
            f"状态：内容生成尚未实现，可先配置公众号凭证并用 check-wechat 测连通性。\n"
            f"微信凭证：{creds}"
        )

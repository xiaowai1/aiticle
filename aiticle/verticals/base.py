from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiticle.config import Settings, VerticalConfig


class Vertical(ABC):
    """内容领域：各自的数据源、生成逻辑与公众号草稿箱。"""

    id: str
    label: str
    description: str
    implemented: bool = False

    @abstractmethod
    def run_batch(
        self,
        settings: Settings,
        config: VerticalConfig,
        count: int | None,
    ) -> list[dict]:
        ...

    @abstractmethod
    def process_one(
        self,
        settings: Settings,
        config: VerticalConfig,
        target: str,
        *,
        name: str = "",
    ) -> dict:
        ...

    @abstractmethod
    def status(self, config: VerticalConfig) -> str:
        """人类可读的进度摘要。"""

    def require_ready(self, config: VerticalConfig) -> None:
        if not self.implemented:
            raise RuntimeError(
                f"领域「{self.label}」（{self.id}）尚未实现内容生成，"
                "请先在 verticals 中配置后再运行。"
            )
        if not config.wechat_app_id or not config.wechat_app_secret:
            raise RuntimeError(
                f"领域「{self.label}」未配置微信公众号凭证，请检查 .env 中对应变量。"
            )

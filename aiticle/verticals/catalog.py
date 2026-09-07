from __future__ import annotations

from aiticle.verticals.base import Vertical
from aiticle.verticals.reserved import ReservedVertical
from aiticle.verticals.stock import StockVertical

_VERTICALS: dict[str, Vertical] = {
    "stock": StockVertical(),
    "reserved": ReservedVertical(),
}

VERTICAL_IDS: tuple[str, ...] = tuple(_VERTICALS.keys())


def get_vertical(vertical_id: str) -> Vertical:
    if vertical_id not in _VERTICALS:
        raise RuntimeError(
            f"未知领域「{vertical_id}」，可用：{', '.join(VERTICAL_IDS)}"
        )
    return _VERTICALS[vertical_id]


def list_verticals() -> list[Vertical]:
    return list(_VERTICALS.values())

from __future__ import annotations

from typing import Any


def is_yes(value: Any) -> bool:
    return str(value or "").strip().upper() in {"YES", "Y", "TRUE", "1", "ACTIVE"}


def tier_factor(tier: str) -> float:
    return {
        "TIER_1": 1.00,
        "TIER_2": 0.75,
        "TIER_3": 0.50,
        "TIER_4": 0.25,
    }.get(
        str(tier).strip().upper(),
        0.50,
    )

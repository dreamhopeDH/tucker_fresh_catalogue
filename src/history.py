from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from .models import Product
from .pricing import discount_percent, sanitized_price


PERTH = ZoneInfo("Australia/Perth")


class HistoryStore(Protocol):
    def get_checkpoint(self, checkpoint_date: str) -> dict | None: ...
    def capture_checkpoint(self, checkpoint_date: str, captured_at: str) -> dict: ...
    def get_tracked_products(self) -> list[str]: ...
    def add_tracked_products(
        self, product_rows: list[tuple[str, str, str, str | None]]
    ) -> None: ...
    def insert_price_history(self, rows: list[dict]) -> None: ...


@dataclass(frozen=True)
class HistoryCheckpoint:
    checkpoint_date: str
    profile_id: int
    favourite_ids: tuple[str, ...]
    reused: bool


def scheduled_history_enabled(
    enabled: bool, fixture: bool, max_products: int | None
) -> bool:
    return enabled and not fixture and max_products is None


def perth_checkpoint_date(now: datetime) -> str:
    if now.tzinfo is None:
        raise ValueError("checkpoint time must be timezone-aware")
    return now.astimezone(PERTH).date().isoformat()


def _checkpoint_from_row(row: dict, reused: bool) -> HistoryCheckpoint:
    try:
        favourites = json.loads(row["favourites_json"])
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("Saved history checkpoint is invalid") from error
    if not isinstance(favourites, list) or not all(
        isinstance(item, str) and item for item in favourites
    ):
        raise ValueError("Saved history checkpoint favourites are invalid")
    return HistoryCheckpoint(
        checkpoint_date=str(row["checkpoint_date"]),
        profile_id=int(row["profile_id"]),
        favourite_ids=tuple(sorted(set(favourites))),
        reused=reused,
    )


def ensure_checkpoint(
    store: HistoryStore, checkpoint_date: str, captured_at: str
) -> HistoryCheckpoint:
    existing = store.get_checkpoint(checkpoint_date)
    if existing is not None:
        return _checkpoint_from_row(existing, True)
    return _checkpoint_from_row(
        store.capture_checkpoint(checkpoint_date, captured_at), False
    )


def product_history_observation(
    product_id: str,
    checkpoint_date: str,
    observed_at: str,
    current_products: dict[str, Product],
) -> dict:
    product = current_products.get(product_id)
    if product is None:
        return {
            "product_id": product_id,
            "checkpoint_date": checkpoint_date,
            "observed_at": observed_at,
            "is_special": 0,
            "regular_price_cents": None,
            "special_price_cents": None,
            "saving_cents": None,
            "discount_percent": 0.0,
            "price_unit": None,
            "offer_text": None,
        }
    price = sanitized_price(product)
    return {
        "product_id": product_id,
        "checkpoint_date": checkpoint_date,
        "observed_at": observed_at,
        "is_special": 1,
        **price,
        "discount_percent": discount_percent(
            price["regular_price_cents"], price["special_price_cents"]
        ),
    }


def promote_and_record_history(
    store: HistoryStore,
    checkpoint: HistoryCheckpoint,
    products: list[Product],
    observed_at: str,
) -> dict[str, int]:
    current = {product.product_id: product for product in products}
    existing = set(store.get_tracked_products())
    newly_tracked = sorted(set(checkpoint.favourite_ids) - existing)
    if newly_tracked:
        store.add_tracked_products(
            [
                (
                    product_id,
                    checkpoint.checkpoint_date,
                    observed_at,
                    current[product_id].raw_name if product_id in current else None,
                )
                for product_id in newly_tracked
            ]
        )
    tracked = sorted(existing | set(checkpoint.favourite_ids))
    rows = [
        product_history_observation(
            product_id, checkpoint.checkpoint_date, observed_at, current
        )
        for product_id in tracked
    ]
    store.insert_price_history(rows)
    return {
        "newly_tracked_count": len(newly_tracked),
        "total_tracked_count": len(tracked),
        "history_special_count": sum(row["is_special"] == 1 for row in rows),
        "history_no_special_count": sum(row["is_special"] == 0 for row in rows),
        "history_unpriced_special_count": sum(
            row["is_special"] == 1 and row["discount_percent"] is None
            for row in rows
        ),
    }

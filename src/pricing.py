from __future__ import annotations

from .models import Product


def valid_discount_prices(
    regular_price_cents: int | None, special_price_cents: int | None
) -> bool:
    return (
        regular_price_cents is not None
        and special_price_cents is not None
        and regular_price_cents > 0
        and 0 <= special_price_cents <= regular_price_cents
    )


def discount_bucket(
    regular_price_cents: int | None, special_price_cents: int | None
) -> str | None:
    """Classify valid prices with exact integer comparisons; return None if invalid."""
    if not valid_discount_prices(regular_price_cents, special_price_cents):
        return None
    assert regular_price_cents is not None and special_price_cents is not None
    if special_price_cents * 2 < regular_price_cents:
        return "over_50"
    if special_price_cents * 2 == regular_price_cents:
        return "exactly_50"
    if special_price_cents * 5 <= regular_price_cents * 3:
        return "forty_to_under_50"
    return "under_40"


def discount_percent(
    regular_price_cents: int | None, special_price_cents: int | None
) -> float | None:
    if not valid_discount_prices(regular_price_cents, special_price_cents):
        return None
    assert regular_price_cents is not None and special_price_cents is not None
    return round(
        (regular_price_cents - special_price_cents) * 100 / regular_price_cents,
        1,
    )


def sanitized_price(product: Product) -> dict[str, int | str | None]:
    """Return the exact conservative price fields used by catalogue and history."""
    regular_price = product.regular_price_cents
    saving = product.saving_cents
    inconsistent = (
        regular_price is not None
        and product.special_price_cents is not None
        and saving is not None
        and regular_price - product.special_price_cents != saving
    )
    if inconsistent:
        saving = None
        if product.price_unit and "approx" in product.price_unit.casefold():
            regular_price = None
    return {
        "regular_price_cents": regular_price,
        "special_price_cents": product.special_price_cents,
        "saving_cents": saving,
        "offer_text": product.normalized_offer_text,
        "price_unit": product.price_unit,
    }

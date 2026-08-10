from __future__ import annotations

from collections import defaultdict

from .models import Product, ProductFamily, PromotionGroup


def promotion_key(product: Product) -> tuple[int | None, int | None, str]:
    return (
        product.regular_price_cents,
        product.special_price_cents,
        product.normalized_offer_text,
    )


def split_families_by_promotion(
    families: list[ProductFamily],
) -> list[PromotionGroup]:
    result: list[PromotionGroup] = []
    for family in families:
        groups: dict[tuple[int | None, int | None, str], list[Product]] = defaultdict(list)
        for product in family.products:
            groups[promotion_key(product)].append(product)
        for products in groups.values():
            result.append(PromotionGroup(family.family_id, family.family_stem, products))
    return result

from dataclasses import replace

from src.models import Product, ProductFamily
from src.offers import split_families_by_promotion


BASE = Product("a", "A", "a", "https://e/a", None, None, "1kg", "family", None, 500, 300, 200, "special", 0)


def group_with(second: Product):
    family = ProductFamily("family-a", "family", [BASE, second])
    return split_families_by_promotion([family])


def test_same_promotion_shares_group():
    assert len(group_with(replace(BASE, product_id="b", source_order=1))) == 1


def test_each_promotion_key_field_splits_group():
    changes = [
        {"special_price_cents": 350},
        {"regular_price_cents": 550},
        {"normalized_offer_text": "two for"},
        {"regular_price_cents": None, "special_price_cents": None},
    ]
    for values in changes:
        second = replace(BASE, product_id="b", source_order=1, **values)
        assert len(group_with(second)) == 2

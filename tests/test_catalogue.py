from pathlib import Path

import pytest

from src.catalogue import build_catalogue, discount_bucket, write_catalogue_files
from src.models import Product, PromotionGroup, UncertainProduct


def product(
    product_id: str,
    order: int,
    regular: int | None = 200,
    special: int | None = 100,
    *,
    family_stem: str | None = None,
    variant: str | None = None,
) -> Product:
    stem = family_stem or product_id
    saving = regular - special if regular is not None and special is not None else None
    return Product(
        product_id,
        f"Product {product_id}",
        product_id,
        f"https://e/{product_id}",
        None,
        None,
        "1kg",
        stem,
        variant,
        regular,
        special,
        saving,
        "special",
        order,
    )


def catalogue_for(
    *,
    groups: list[PromotionGroup] | None = None,
    standalone: list[Product] | None = None,
    uncertain: list[UncertainProduct] | None = None,
    page_size: int = 9,
    image_manifest: dict | None = None,
    ordering_seed: int | None = None,
) -> dict:
    groups = groups or []
    standalone = standalone or []
    uncertain = uncertain or []
    source_count = sum(len(group.products) for group in groups) + len(standalone) + len(uncertain)
    return build_catalogue(
        confirmed_offer_groups=groups,
        standalone_products=standalone,
        uncertain_products=uncertain,
        image_manifest=image_manifest or {},
        page_size=page_size,
        source_product_count=source_count,
        ordering_seed=source_count if ordering_seed is None else ordering_seed,
    )


@pytest.mark.parametrize(
    ("regular", "special", "expected"),
    [
        (100, 49, "over_50"),
        (100, 50, "exactly_50"),
        (100, 51, "forty_to_under_50"),
        (100, 60, "forty_to_under_50"),
        (100, 61, "under_40"),
        (300, 149, "over_50"),
    ],
)
def test_discount_bucket_uses_exact_integer_boundaries(regular, special, expected):
    assert discount_bucket(regular, special) == expected


@pytest.mark.parametrize(
    ("regular", "special"),
    [(None, 100), (200, None), (0, 0), (200, -1), (100, 101)],
)
def test_discount_bucket_rejects_invalid_prices(regular, special):
    assert discount_bucket(regular, special) is None


def item_ids(catalogue: dict, group_id: str | None = None) -> list[str]:
    return [
        item["id"]
        for page in catalogue["pages"]
        if group_id is None or page["discount_group"] == group_id
        for item in page["items"]
    ]


def test_deterministic_random_order_repeats_for_same_seed():
    products = [product(f"item-{index:02}", index, 100, 49) for index in range(20)]

    first = catalogue_for(standalone=products, ordering_seed=3754)
    second = catalogue_for(standalone=list(reversed(products)), ordering_seed=3754)

    assert item_ids(first) == item_ids(second)
    assert first["manifest"]["ordering"] == {
        "mode": "deterministic_random",
        "seed": 3754,
    }


def test_different_ordering_seed_changes_a_representative_group():
    products = [product(f"item-{index:02}", index, 100, 49) for index in range(30)]

    first = catalogue_for(standalone=products, ordering_seed=3754)
    second = catalogue_for(standalone=products, ordering_seed=3755)

    assert item_ids(first) != item_ids(second)


def test_each_discount_group_is_paginated_independently():
    over_50 = [product(f"over-{index}", index, 100, 49) for index in range(10)]
    exactly_50 = [
        product(f"exact-{index}", 20 + index, 100, 50) for index in range(10)
    ]
    catalogue = catalogue_for(standalone=over_50 + exactly_50)

    assert [page["discount_group"] for page in catalogue["pages"]] == [
        "over_50",
        "over_50",
        "exactly_50",
        "exactly_50",
    ]
    assert [len(page["items"]) for page in catalogue["pages"]] == [9, 1, 9, 1]
    assert all(
        all(item["id"].startswith("over-") for item in page["items"])
        for page in catalogue["pages"][:2]
    )
    assert all(
        all(item["id"].startswith("exact-") for item in page["items"])
        for page in catalogue["pages"][2:]
    )


def test_uncertain_products_enter_their_bucket_after_normal_items():
    uncertain_over = product("uncertain-over", 1, 100, 49)
    uncertain_under = product("uncertain-under", 2, 100, 70)
    catalogue = catalogue_for(
        standalone=[
            product("normal-over", 10, 100, 40),
            product("normal-under", 11, 100, 80),
        ],
        uncertain=[
            UncertainProduct(uncertain_over, "normal-over", 90),
            UncertainProduct(uncertain_under, "normal-under", 88),
        ],
    )

    over_page, under_page = catalogue["pages"]
    assert over_page["discount_group"] == "over_50"
    assert [item["id"] for item in over_page["items"]] == [
        "normal-over",
        "uncertain-over",
    ]
    assert under_page["discount_group"] == "under_40"
    assert [item["id"] for item in under_page["items"]] == [
        "normal-under",
        "uncertain-under",
    ]
    assert "uncertain_start_page" not in catalogue["manifest"]


def test_randomization_preserves_normal_invalid_uncertain_boundaries():
    normal_valid = [product(f"normal-valid-{index}", index, 100, 70) for index in range(5)]
    normal_invalid = [product(f"normal-invalid-{index}", 10 + index, None, 70) for index in range(3)]
    uncertain_valid = [
        UncertainProduct(product(f"uncertain-valid-{index}", 20 + index, 100, 70), "x", 90)
        for index in range(4)
    ]
    uncertain_invalid = [
        UncertainProduct(product(f"uncertain-invalid-{index}", 30 + index, None, 70), "x", 90)
        for index in range(2)
    ]

    catalogue = catalogue_for(
        standalone=normal_invalid + normal_valid,
        uncertain=uncertain_invalid + uncertain_valid,
        ordering_seed=3754,
    )
    ids = item_ids(catalogue, "under_40")

    assert all(item.startswith("normal-valid-") for item in ids[:5])
    assert all(item.startswith("normal-invalid-") for item in ids[5:8])
    assert all(item.startswith("uncertain-valid-") for item in ids[8:12])
    assert all(item.startswith("uncertain-invalid-") for item in ids[12:])


def test_different_promotions_in_one_family_become_separate_display_items():
    original = product("original", 3, 400, 200, family_stem="brand chips", variant="Original")
    barbecue = product("barbecue", 4, 400, 200, family_stem="brand chips", variant="BBQ")
    large = product("large", 5, 500, 350, family_stem="brand chips", variant="Large")
    catalogue = catalogue_for(
        groups=[
            PromotionGroup("chips", "brand chips", [original, barbecue]),
            PromotionGroup("chips", "brand chips", [large]),
        ]
    )

    exact_page, under_page = catalogue["pages"]
    assert exact_page["discount_group"] == "exactly_50"
    assert [product["product_id"] for product in exact_page["items"][0]["products"]] == [
        "original",
        "barbecue",
    ]
    assert len(exact_page["items"][0]["offers"]) == 1
    assert under_page["discount_group"] == "under_40"
    assert [product["product_id"] for product in under_page["items"][0]["products"]] == [
        "large"
    ]


def test_missing_price_falls_back_to_end_of_group_four_with_null_discount():
    catalogue = catalogue_for(
        standalone=[
            product("missing", 1, None, 100),
            product("valid", 9, 100, 70),
        ]
    )

    page = catalogue["pages"][0]
    assert page["discount_group"] == "under_40"
    assert [item["id"] for item in page["items"]] == ["valid", "missing"]
    assert page["items"][-1]["discount_percent"] is None


def test_manifest_keeps_all_group_metadata_and_image_keys(tmp_path: Path):
    object_key = "test/products/item/a81bd34f12345678.webp"
    catalogue = catalogue_for(
        standalone=[product("item", 0, 200, 100)],
        image_manifest={"item": {"status": "downloaded", "object_key": object_key}},
    )

    assert [group["id"] for group in catalogue["manifest"]["discount_groups"]] == [
        "over_50",
        "exactly_50",
        "forty_to_under_50",
        "under_40",
    ]
    assert catalogue["manifest"]["discount_groups"][0]["start_page"] is None
    assert catalogue["manifest"]["discount_groups"][1] == {
        "id": "exactly_50",
        "label": "half price",
        "item_count": 1,
        "start_page": 1,
        "page_count": 1,
    }
    assert catalogue["pages"][0]["items"][0]["products"][0]["image_key"] == object_key
    assert catalogue["manifest"]["search_index"] == "data/search-index.json"
    assert "https://" not in str(catalogue)

    write_catalogue_files(catalogue, tmp_path)
    page_json = (tmp_path / "pages" / "1.json").read_text(encoding="utf-8")
    assert '"discount_group": "exactly_50"' in page_json
    assert (tmp_path / "search-index.json").exists()


def test_search_index_is_lightweight_searchable_and_points_to_catalogue_pages():
    original = product(
        "original",
        0,
        family_stem="brand chips",
        variant="Sea Salt",
    )
    barbecue = product(
        "barbecue",
        1,
        family_stem="brand chips",
        variant="Smoky BBQ",
    )
    catalogue = catalogue_for(
        groups=[PromotionGroup("chips", "brand chips", [original, barbecue])],
        standalone=[product("coffee", 2, 100, 70)],
    )

    entries = catalogue["search_index"]["items"]
    family = next(entry for entry in entries if entry["id"].startswith("chips--"))
    coffee = next(entry for entry in entries if entry["id"] == "coffee")

    assert family["name"] == "Brand Chips"
    assert family["page"] == 1
    assert "Sea Salt" in family["search_text"]
    assert "Smoky BBQ" in family["search_text"]
    assert family["details"]
    assert coffee["page"] == 2
    assert "products" not in family
    assert "offers" not in family

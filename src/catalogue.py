from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .models import Product, PromotionGroup, UncertainProduct


DISCOUNT_GROUPS = (
    ("over_50", "More than 50% off"),
    ("exactly_50", "half price"),
    ("forty_to_under_50", "40% to 50% off"),
    ("under_40", "Less than 40% off"),
)
FALLBACK_DISCOUNT_GROUP = "under_40"


def _valid_discount_prices(
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
    if not _valid_discount_prices(regular_price_cents, special_price_cents):
        return None
    assert regular_price_cents is not None and special_price_cents is not None
    if special_price_cents * 2 < regular_price_cents:
        return "over_50"
    if special_price_cents * 2 == regular_price_cents:
        return "exactly_50"
    if special_price_cents * 5 <= regular_price_cents * 3:
        return "forty_to_under_50"
    return "under_40"


def _discount_percent(
    regular_price_cents: int | None, special_price_cents: int | None
) -> float | None:
    if not _valid_discount_prices(regular_price_cents, special_price_cents):
        return None
    assert regular_price_cents is not None and special_price_cents is not None
    return round((regular_price_cents - special_price_cents) * 100 / regular_price_cents, 1)


def _price(product: Product) -> dict:
    return {
        "regular_price_cents": product.regular_price_cents,
        "special_price_cents": product.special_price_cents,
        "saving_cents": product.saving_cents,
        "offer_text": product.normalized_offer_text,
    }


def _product_view(product: Product, image_manifest: dict) -> dict:
    image = image_manifest.get(product.product_id, {})
    return {
        "product_id": product.product_id,
        "name": product.raw_name,
        "variant": product.variant_hint,
        "size": product.size_text,
        "image_key": image.get("object_key") if image.get("status") == "downloaded" else None,
    }


def _with_discount(item: dict) -> tuple[str, bool, dict]:
    offer = item["offers"][0]
    bucket = discount_bucket(
        offer["regular_price_cents"], offer["special_price_cents"]
    )
    item["discount_percent"] = _discount_percent(
        offer["regular_price_cents"], offer["special_price_cents"]
    )
    return bucket or FALLBACK_DISCOUNT_GROUP, bucket is None, item


def _promotion_item(group: PromotionGroup, image_manifest: dict) -> dict:
    products = sorted(group.products, key=lambda product: product.source_order)
    return {
        "type": "family",
        "id": f"{group.family_id}--{products[0].product_id}",
        "name": group.family_stem.title(),
        "source_order": products[0].source_order,
        "products": [_product_view(product, image_manifest) for product in products],
        "offers": [
            {
                **_price(products[0]),
                "product_ids": [product.product_id for product in products],
            }
        ],
    }


def _product_item(product: Product, image_manifest: dict, item_type: str = "product") -> dict:
    return {
        "type": item_type,
        "id": product.product_id,
        "name": product.raw_name,
        "source_order": product.source_order,
        "products": [_product_view(product, image_manifest)],
        "offers": [{**_price(product), "product_ids": [product.product_id]}],
    }


def build_catalogue(
    confirmed_offer_groups: list[PromotionGroup],
    standalone_products: list[Product],
    uncertain_products: list[UncertainProduct],
    image_manifest: dict,
    page_size: int,
    source_product_count: int,
) -> dict:
    if page_size <= 0:
        raise ValueError("page_size must be greater than zero")

    grouped: dict[str, dict[str, list[tuple[bool, dict]]]] = {
        group_id: {"normal": [], "uncertain": []} for group_id, _ in DISCOUNT_GROUPS
    }

    normal_items = [
        *[_promotion_item(group, image_manifest) for group in confirmed_offer_groups],
        *[_product_item(product, image_manifest) for product in standalone_products],
    ]
    for item in normal_items:
        bucket, invalid, classified_item = _with_discount(item)
        grouped[bucket]["normal"].append((invalid, classified_item))

    for uncertain in uncertain_products:
        item = _product_item(uncertain.product, image_manifest, "uncertain")
        item.update(
            {
                "candidate_product_id": uncertain.candidate_product_id,
                "similarity": round(uncertain.similarity, 1),
            }
        )
        bucket, invalid, classified_item = _with_discount(item)
        grouped[bucket]["uncertain"].append((invalid, classified_item))

    pages: list[dict] = []
    discount_group_summaries: list[dict] = []
    display_item_count = 0
    for group_id, label in DISCOUNT_GROUPS:
        sections = grouped[group_id]
        normal = [
            item
            for _, item in sorted(
                sections["normal"], key=lambda entry: (entry[0], entry[1]["source_order"])
            )
        ]
        uncertain = [
            item
            for _, item in sorted(
                sections["uncertain"], key=lambda entry: (entry[0], entry[1]["source_order"])
            )
        ]
        items = normal + uncertain
        item_count = len(items)
        page_count = (item_count + page_size - 1) // page_size
        start_page = len(pages) + 1 if page_count else None
        for index in range(0, item_count, page_size):
            pages.append(
                {
                    "page": len(pages) + 1,
                    "discount_group": group_id,
                    "discount_group_label": label,
                    "items": items[index : index + page_size],
                }
            )
        discount_group_summaries.append(
            {
                "id": group_id,
                "label": label,
                "item_count": item_count,
                "start_page": start_page,
                "page_count": page_count,
            }
        )
        display_item_count += item_count

    return {
        "manifest": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_product_count": source_product_count,
            "display_item_count": display_item_count,
            "page_size": page_size,
            "page_count": len(pages),
            "discount_groups": discount_group_summaries,
            "pages": [f"data/pages/{index}.json" for index in range(1, len(pages) + 1)],
        },
        "pages": pages,
    }


def write_catalogue_files(catalogue: dict, output_directory: Path) -> None:
    pages_directory = output_directory / "pages"
    if pages_directory.exists():
        shutil.rmtree(pages_directory)
    pages_directory.mkdir(parents=True, exist_ok=True)
    (output_directory / "manifest.json").write_text(
        json.dumps(catalogue["manifest"], indent=2), encoding="utf-8"
    )
    for page in catalogue["pages"]:
        (pages_directory / f"{page['page']}.json").write_text(
            json.dumps(page, indent=2), encoding="utf-8"
        )

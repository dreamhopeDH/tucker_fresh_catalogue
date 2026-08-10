from __future__ import annotations

import json
import math
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .models import Product, PromotionGroup, UncertainProduct


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


def build_catalogue(
    confirmed_offer_groups: list[PromotionGroup],
    standalone_products: list[Product],
    uncertain_products: list[UncertainProduct],
    image_manifest: dict,
    page_size: int,
    source_product_count: int,
) -> dict:
    family_groups: dict[str, list[PromotionGroup]] = defaultdict(list)
    for group in confirmed_offer_groups:
        family_groups[group.family_id].append(group)

    main_items: list[dict] = []
    for family_id, groups in family_groups.items():
        all_products = sorted(
            {product.product_id: product for group in groups for product in group.products}.values(),
            key=lambda product: product.source_order,
        )
        main_items.append(
            {
                "type": "family",
                "id": family_id,
                "name": groups[0].family_stem.title(),
                "source_order": all_products[0].source_order,
                "products": [_product_view(product, image_manifest) for product in all_products],
                "offers": [
                    {
                        **_price(group.products[0]),
                        "product_ids": [product.product_id for product in group.products],
                    }
                    for group in groups
                ],
            }
        )
    for product in standalone_products:
        main_items.append(
            {
                "type": "product",
                "id": product.product_id,
                "name": product.raw_name,
                "source_order": product.source_order,
                "products": [_product_view(product, image_manifest)],
                "offers": [{**_price(product), "product_ids": [product.product_id]}],
            }
        )
    main_items.sort(key=lambda item: item["source_order"])

    uncertain_items = [
        {
            "type": "uncertain",
            "id": item.product.product_id,
            "name": item.product.raw_name,
            "source_order": item.product.source_order,
            "candidate_product_id": item.candidate_product_id,
            "similarity": round(item.similarity, 1),
            "products": [_product_view(item.product, image_manifest)],
            "offers": [{**_price(item.product), "product_ids": [item.product.product_id]}],
        }
        for item in sorted(uncertain_products, key=lambda item: item.product.source_order)
    ]
    items = main_items + uncertain_items
    pages = [items[index : index + page_size] for index in range(0, len(items), page_size)]
    uncertain_start_page = (
        math.floor(len(main_items) / page_size) + 1 if uncertain_items else None
    )
    return {
        "manifest": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_product_count": source_product_count,
            "display_item_count": len(items),
            "page_size": page_size,
            "page_count": len(pages),
            "uncertain_start_page": uncertain_start_page,
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
    for index, items in enumerate(catalogue["pages"], start=1):
        (pages_directory / f"{index}.json").write_text(
            json.dumps({"page": index, "items": items}, indent=2), encoding="utf-8"
        )

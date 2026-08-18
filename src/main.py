from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict
from pathlib import Path

from .b2_store import B2ImageStore
from .catalogue import build_catalogue, write_catalogue_files
from .config import ROOT, Settings
from .grouping import group_products, load_grouping_rules, load_manual_overrides
from .images import sync_images
from .models import RawProduct
from .normalize import normalize_products
from .offers import split_families_by_promotion
from .scrape import fetch_specials


LOGGER = logging.getLogger(__name__)


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def _load_fixture(path: Path) -> list[RawProduct]:
    return [RawProduct(**item) for item in json.loads(path.read_text(encoding="utf-8"))]


def image_sync_allows_catalogue(image_stats: dict[str, int | bool]) -> bool:
    return image_stats.get("image_sync_complete") is True


def run(fixture: Path | None = None, skip_images: bool = False) -> dict:
    settings = Settings.from_env()
    settings.validate()
    rules = load_grouping_rules(ROOT / "config" / "grouping_rules.yml")
    overrides = load_manual_overrides(ROOT / "config" / "manual_overrides.yml")

    LOGGER.info("SCRAPE")
    if fixture:
        raw_products = _load_fixture(fixture)
        advertised_product_count = None
        retrieval_strategy = "fixture"
        name_az_unique_count = None
        name_za_unique_count = None
        alphabetical_overlap_count = None
        final_union_unique_count = len(raw_products)
    else:
        scrape_result = fetch_specials(
            source_url=settings.source_specials_url,
            max_products=settings.max_products,
            delay_min_seconds=settings.list_page_delay_min_seconds,
            delay_max_seconds=settings.list_page_delay_max_seconds,
        )
        raw_products = scrape_result.products
        advertised_product_count = scrape_result.advertised_product_count
        retrieval_strategy = scrape_result.retrieval_strategy
        name_az_unique_count = scrape_result.name_az_unique_count
        name_za_unique_count = scrape_result.name_za_unique_count
        alphabetical_overlap_count = scrape_result.alphabetical_overlap_count
        final_union_unique_count = scrape_result.final_union_unique_count
    if settings.max_products is not None:
        raw_products = raw_products[: settings.max_products]
    _write_json(settings.output_directory / "raw-products.json", [asdict(item) for item in raw_products])

    LOGGER.info("NORMALIZE")
    products = normalize_products(raw_products, rules.get("flavor_terms", []))
    _write_json(settings.output_directory / "normalized-products.json", [asdict(item) for item in products])

    LOGGER.info("GROUP")
    grouping = group_products(products, rules, overrides)
    _write_json(settings.output_directory / "grouping-result.json", asdict(grouping))
    offer_groups = split_families_by_promotion(grouping.confirmed_families)

    LOGGER.info("SYNC_IMAGES")
    if skip_images or fixture:
        image_manifest = {
            product.product_id: {
                "source_image_url": product.image_url,
                "object_key": None,
                "status": "missing",
            }
            for product in products
        }
        image_stats: dict[str, int | bool] = {
            "downloaded": 0,
            "skipped": 0,
            "missing": len(products),
            "failed": 0,
            "stopped_after_failures": False,
            "image_sync_complete": True,
            "stopped_after_budget": False,
            "remaining": 0,
        }
    else:
        settings.require_b2()
        store = B2ImageStore(
            endpoint=settings.b2_endpoint or "",
            key_id=settings.b2_key_id or "",
            application_key=settings.b2_application_key or "",
            bucket=settings.b2_bucket or "",
            prefix=settings.b2_prefix,
        )
        image_manifest, image_stats = sync_images(products, store, settings)

    ordering_seed = (
        advertised_product_count
        if advertised_product_count is not None
        else len(products)
    )
    summary = {
        "mode": "full" if settings.max_products is None else "limited",
        "requested_product_limit": settings.max_products,
        "retrieval_strategy": retrieval_strategy,
        "source_advertised_product_count": advertised_product_count,
        "name_az_unique_count": name_az_unique_count,
        "name_za_unique_count": name_za_unique_count,
        "alphabetical_overlap_count": alphabetical_overlap_count,
        "final_union_unique_count": final_union_unique_count,
        "actual_product_count": len(products),
        "ordering_mode": "deterministic_random",
        "ordering_seed": ordering_seed,
        "confirmed_family_count": len(grouping.confirmed_families),
        "standalone_product_count": len(grouping.standalone_products),
        "uncertain_product_count": len(grouping.uncertain_products),
        **image_stats,
        "display_item_count": None,
        "discount_groups": [],
        "page_count": None,
    }
    if not image_sync_allows_catalogue(image_stats):
        _write_json(settings.output_directory / "run-summary.json", summary)
        if image_stats["stopped_after_budget"]:
            reason = "the time budget was reached"
        elif image_stats["stopped_after_failures"]:
            reason = "10 consecutive image requests failed"
        else:
            reason = "the complete current product set was not traversed"
        LOGGER.warning(
            "Image warm-up is incomplete because %s. Progress has been saved to the "
            "B2 manifest. Run the workflow again to continue. No new catalogue was deployed.",
            reason,
        )
        return summary

    LOGGER.info("BUILD_CATALOGUE")
    catalogue = build_catalogue(
        confirmed_offer_groups=offer_groups,
        standalone_products=grouping.standalone_products,
        uncertain_products=grouping.uncertain_products,
        image_manifest=image_manifest,
        page_size=settings.page_size,
        source_product_count=len(products),
        ordering_seed=ordering_seed,
    )
    write_catalogue_files(catalogue, settings.site_data_directory)
    _write_json(settings.output_directory / "catalogue-manifest.json", catalogue["manifest"])
    summary.update(
        {
            "display_item_count": catalogue["manifest"]["display_item_count"],
            "discount_groups": catalogue["manifest"]["discount_groups"],
            "page_count": catalogue["manifest"]["page_count"],
        }
    )
    _write_json(settings.output_directory / "run-summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Tucker Fresh catalogue")
    parser.add_argument("--fixture", type=Path, help="Read RawProduct JSON instead of the live site")
    parser.add_argument("--skip-images", action="store_true", help="Use placeholders; intended for local debugging")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    summary = run(args.fixture, args.skip_images)
    LOGGER.info("Complete: %s", json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()

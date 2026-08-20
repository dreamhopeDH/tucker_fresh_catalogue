import json

import httpx

from src.catalogue import build_catalogue, write_catalogue_files
from src.grouping import group_products
from src.models import Product
from src.scrape import NAME_ASCENDING_SORT, fetch_specials


def product(index: int) -> Product:
    prices = ((100, 49), (100, 50), (100, 60), (100, 61))
    regular, special = prices[index % len(prices)]
    return Product(
        product_id=f"product-{index}",
        raw_name=f"Synthetic Product {index}",
        normalized_name=f"synthetic product {index}",
        product_url=f"https://example.test/products/{index}",
        image_url=None,
        brand_hint="synthetic",
        size_text=None,
        family_stem=f"synthetic product {index}",
        variant_hint=None,
        regular_price_cents=regular,
        special_price_cents=special,
        saving_cents=regular - special,
        normalized_offer_text="special",
        source_order=index,
    )


def test_several_thousand_products_group_and_paginate_without_mixed_pages(tmp_path):
    products = [product(index) for index in range(4_000)]
    grouping = group_products(products)
    assert grouping.confirmed_families == []
    assert grouping.uncertain_products == []
    assert len(grouping.standalone_products) == 4_000

    catalogue = build_catalogue(
        confirmed_offer_groups=[],
        standalone_products=grouping.standalone_products,
        uncertain_products=[],
        image_manifest={},
        page_size=9,
        source_product_count=len(products),
        ordering_seed=len(products),
    )

    summaries = catalogue["manifest"]["discount_groups"]
    assert [summary["item_count"] for summary in summaries] == [1_000] * 4
    assert [summary["page_count"] for summary in summaries] == [112] * 4
    assert catalogue["manifest"]["page_size"] == 9
    assert catalogue["manifest"]["page_count"] == 448
    assert all(len(page["items"]) <= 9 for page in catalogue["pages"])
    assert len(catalogue["search_index"]["items"]) == 4_000
    assert all(
        page["discount_group"]
        == next(
            summary["id"]
            for summary in summaries
            if summary["start_page"] is not None
            and summary["start_page"]
            <= page["page"]
            < summary["start_page"] + summary["page_count"]
        )
        for page in catalogue["pages"]
    )
    assert [len(page["items"]) for page in catalogue["pages"] if page["page"] in {112, 224, 336, 448}] == [1, 1, 1, 1]

    write_catalogue_files(catalogue, tmp_path)
    page_files = sorted((tmp_path / "pages").glob("*.json"))
    assert len(page_files) == 448
    assert json.loads((tmp_path / "manifest.json").read_text())["page_count"] == 448
    assert len(json.loads((tmp_path / "search-index.json").read_text())["items"]) == 4_000

    repeated = build_catalogue(
        confirmed_offer_groups=[],
        standalone_products=list(reversed(grouping.standalone_products)),
        uncertain_products=[],
        image_manifest={},
        page_size=9,
        source_product_count=len(products),
        ordering_seed=len(products),
    )
    first_order = [item["id"] for page in catalogue["pages"] for item in page["items"]]
    repeated_order = [item["id"] for page in repeated["pages"] for item in page["items"]]
    assert first_order == repeated_order
    assert catalogue["search_index"] == repeated["search_index"]


def test_several_thousand_products_recover_from_bidirectional_windows():
    def html(ids: range, sort_by: str) -> str:
        cards = "".join(
            f'<article data-product-id="p{index}" data-product-name="Product {index:04}" '
            f'data-product-url="/products/{index}" data-regular-price="$2" '
            f'data-special-price="$1"></article>'
            for index in ids
        )
        return (
            cards
            + '<span>4000 results</span>'
            + f'<div role="navigation" aria-label="Pagination"><a rel="next" '
            f'href="/search?page=2&amp;q%5B%5D=special%3A1&amp;sort_by={sort_by}">Next</a></div>'
        )

    def handler(request: httpx.Request):
        sort_by = request.url.params["sort_by"]
        ids = range(0, 2400) if sort_by == NAME_ASCENDING_SORT else range(3999, 1599, -1)
        return httpx.Response(200, text=html(ids, sort_by), request=request)

    result = fetch_specials(
        "https://example.test/specials",
        None,
        0,
        0,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _: None,
        result_window_pages=1,
    )

    assert result.name_az_unique_count == 2400
    assert result.name_za_unique_count == 2400
    assert result.alphabetical_overlap_count == 800
    assert result.final_union_unique_count == 4000
    assert len(result.products) == 4000

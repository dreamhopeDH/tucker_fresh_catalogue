from __future__ import annotations

import logging
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup, Tag

from .models import RawProduct
from .normalize import normalize_product_url


LOGGER = logging.getLogger(__name__)
TRANSIENT_STATUS = {429, 500, 502, 503, 504}
MYFOODLINK_RESULT_WINDOW_PAGES = 50
NAME_ASCENDING_SORT = "name"
NAME_DESCENDING_SORT = "name_descending"


@dataclass(frozen=True)
class ScrapeResult:
    products: list[RawProduct]
    advertised_product_count: int | None
    retrieval_strategy: str
    name_az_unique_count: int | None
    name_za_unique_count: int | None
    alphabetical_overlap_count: int | None
    final_union_unique_count: int


@dataclass(frozen=True)
class PaginationMetadata:
    advertised_product_count: int | None
    next_url: str | None


@dataclass(frozen=True)
class _WindowResult:
    products: dict[str, RawProduct]
    advertised_product_count: int
    reached_window_limit: bool


def parse_price_cents(value: str | None) -> int | None:
    if not value:
        return None
    normalized = value.replace(",", "")
    dollar_match = re.search(r"\$\s*(\d+(?:\.\d{1,2})?)", normalized)
    if dollar_match:
        return round(float(dollar_match.group(1)) * 100)
    cents_match = re.search(r"(\d+)\s*(?:c\b|¢)", normalized, re.IGNORECASE)
    if cents_match:
        return int(cents_match.group(1))
    match = re.search(r"(\d+(?:\.\d{1,2})?)", normalized)
    return round(float(match.group(1)) * 100) if match else None


def _text(card: Tag, selectors: tuple[str, ...]) -> str | None:
    for selector in selectors:
        node = card.select_one(selector)
        if node and node.get_text(" ", strip=True):
            return node.get_text(" ", strip=True)
    return None


def _attribute(card: Tag, selectors: tuple[str, ...], attribute: str) -> str | None:
    for selector in selectors:
        node = card.select_one(selector)
        if node and node.get(attribute):
            return str(node.get(attribute))
    return None


def parse_specials_page(html: str, page_url: str, source_order: int = 0) -> list[RawProduct]:
    soup = BeautifulSoup(html, "html.parser")
    cards: list[Tag] = []
    for selector in (
        "[data-product-id]",
        ".product-card",
        ".product-item",
        "article.product",
        ".talker[data-talker]",
    ):
        cards = list(soup.select(selector))
        if cards:
            break
    if not cards:
        raise ValueError("Specials page structure was not recognized: no product cards found")

    scraped_at = datetime.now(timezone.utc).isoformat()
    products: list[RawProduct] = []
    for offset, card in enumerate(cards):
        try:
            name = (
                card.get("data-product-name")
                or _attribute(card, (".talker__name[title]",), "title")
                or _text(card, (".product-name", ".name", "h2", "h3"))
            )
            href = card.get("data-product-url") or _attribute(
                card, ("a.product-link", ".talker__imagery a[href]", "a[href]"), "href"
            )
            if not name or not href:
                raise ValueError("missing name or URL")
            image = (
                card.get("data-image-url")
                or _attribute(card, ("img[data-src]",), "data-src")
                or _attribute(card, (".talker__imagery img[src]", "img[src]"), "src")
            )
            source_product_id = card.get("data-product-id")
            if not source_product_id and str(card.get("id", "")).startswith("line_"):
                source_product_id = str(card.get("id"))[len("line_") :]
            offer_text = (
                card.get("data-offer")
                or _text(card, (".offer", ".promotion"))
                or _text(card, (".talker__sticker--Deal .talker__sticker__label",))
            )
            if not offer_text and "talker--Special" in card.get("class", []):
                offer_text = "Special"
            price_unit = card.get("data-price-unit") or _text(
                card, (".talker__prices__sell .price__units", ".price__units")
            )
            products.append(
                RawProduct(
                    source_product_id=str(source_product_id) if source_product_id else None,
                    name=str(name),
                    product_url=urljoin(page_url, str(href)),
                    image_url=urljoin(page_url, str(image)) if image else None,
                    regular_price_cents=parse_price_cents(
                        card.get("data-regular-price")
                        or _text(
                            card,
                            (".regular-price", ".was-price", ".talker__prices__was"),
                        )
                    ),
                    special_price_cents=parse_price_cents(
                        card.get("data-special-price")
                        or _text(card, (".special-price", ".price", ".price__sell"))
                    ),
                    saving_cents=parse_price_cents(
                        card.get("data-saving")
                        or _text(
                            card,
                            (
                                ".saving",
                                ".save",
                                ".talker__sticker--Saving .talker__sticker__label",
                            ),
                        )
                    ),
                    offer_text=str(offer_text) if offer_text else None,
                    scraped_at=scraped_at,
                    source_order=source_order + offset,
                    price_unit=str(price_unit) if price_unit else None,
                )
            )
        except (TypeError, ValueError) as error:
            LOGGER.warning("Skipping unparseable product card %s: %s", offset + 1, error)
    return products


def parse_pagination_metadata(html: str, page_url: str) -> PaginationMetadata:
    soup = BeautifulSoup(html, "html.parser")
    results_match = re.search(r"\b([\d,]+)\s+results\b", soup.get_text(" ", strip=True), re.I)
    advertised_count = (
        int(results_match.group(1).replace(",", "")) if results_match else None
    )
    next_link = soup.select_one(
        '[role="navigation"][aria-label="Pagination"] a[rel~="next"]'
    )
    if not next_link or not next_link.get("href"):
        return PaginationMetadata(advertised_count, None)

    next_url = urljoin(page_url, str(next_link.get("href")))
    current_parts = urlsplit(page_url)
    next_parts = urlsplit(next_url)
    if (
        next_parts.scheme not in {"http", "https"}
        or next_parts.scheme != current_parts.scheme
        or next_parts.netloc != current_parts.netloc
        or next_parts.path != current_parts.path
    ):
        raise ValueError("Specials pagination contained an unsafe next-page URL")
    return PaginationMetadata(advertised_count, next_url)


def _product_identity(product: RawProduct) -> str:
    if product.source_product_id:
        return f"id:{product.source_product_id}"
    return f"url:{normalize_product_url(product.product_url)}"


def _material_product_fields(product: RawProduct) -> tuple:
    return (
        product.source_product_id,
        normalize_product_url(product.product_url),
        product.name,
        product.image_url,
        product.regular_price_cents,
        product.special_price_cents,
        product.saving_cents,
        product.offer_text,
        product.price_unit,
    )


def _alphabetical_url(source_url: str, sort_by: str) -> str:
    parts = urlsplit(source_url)
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            "/search",
            urlencode([("q[]", "special:1"), ("sort_by", sort_by)]),
            "",
        )
    )


def _get_page(
    client: httpx.Client,
    page_url: str,
    delay_min_seconds: float,
    delay_max_seconds: float,
    sleep,
) -> httpx.Response:
    response = None
    last_transport_error: httpx.TransportError | None = None
    for attempt in range(3):
        try:
            response = client.get(page_url)
        except httpx.TransportError as error:
            last_transport_error = error
            sleep(random.uniform(delay_min_seconds, delay_max_seconds))
            if attempt == 2:
                raise
            continue
        sleep(random.uniform(delay_min_seconds, delay_max_seconds))
        if response.status_code not in TRANSIENT_STATUS:
            break
        if attempt == 2:
            response.raise_for_status()
    if response is None:
        if last_transport_error:
            raise last_transport_error
        raise RuntimeError("List page request did not return a response")
    response.raise_for_status()
    return response


def _validate_advertised_count(
    expected: int | None,
    observed: int | None,
    *,
    sort_label: str,
    page: int,
) -> int | None:
    if observed is None:
        return expected
    if expected is not None and observed != expected:
        raise RuntimeError(
            "Source result count changed during alphabetical recovery: "
            f"expected {expected}, {sort_label} page {page} advertised {observed}. "
            "Rerun to avoid merging different catalogue states."
        )
    return observed


def _scrape_alphabetical_window(
    *,
    source_url: str,
    sort_by: str,
    sort_label: str,
    expected_count: int | None,
    result_window_pages: int,
    client: httpx.Client,
    delay_min_seconds: float,
    delay_max_seconds: float,
    sleep,
) -> _WindowResult:
    page_url = _alphabetical_url(source_url, sort_by)
    products: dict[str, RawProduct] = {}
    visited_urls: set[str] = set()
    advertised_count = expected_count

    for page in range(1, result_window_pages + 1):
        if page_url in visited_urls:
            raise RuntimeError(f"{sort_label} pagination looped to a previously requested URL")
        visited_urls.add(page_url)
        response = _get_page(
            client, page_url, delay_min_seconds, delay_max_seconds, sleep
        )
        pagination = parse_pagination_metadata(response.text, str(response.url))
        advertised_count = _validate_advertised_count(
            advertised_count,
            pagination.advertised_product_count,
            sort_label=sort_label,
            page=page,
        )
        if advertised_count is None:
            raise RuntimeError(
                f"{sort_label} did not advertise a result count; full recovery cannot "
                "be validated safely"
            )

        page_products = parse_specials_page(response.text, str(response.url))
        added = 0
        for product in page_products:
            identity = _product_identity(product)
            existing = products.get(identity)
            if existing is not None:
                if _material_product_fields(existing) != _material_product_fields(product):
                    raise RuntimeError(
                        f"{sort_label} returned conflicting copies of product {identity}"
                    )
                continue
            products[identity] = product
            added += 1
        LOGGER.info(
            "%s page %s: %s parsed, %s unique, %s cumulative",
            sort_label,
            page,
            len(page_products),
            added,
            len(products),
        )

        if len(products) == advertised_count:
            return _WindowResult(products, advertised_count, False)
        if pagination.next_url is None:
            raise RuntimeError(
                f"{sort_label} ended after {len(products)} unique products but the source "
                f"advertised {advertised_count}"
            )
        if page == result_window_pages:
            return _WindowResult(products, advertised_count, True)
        page_url = pagination.next_url

    raise AssertionError("Alphabetical result-window loop exited unexpectedly")


def _merge_alphabetical_windows(
    name_az: _WindowResult, name_za: _WindowResult
) -> tuple[list[RawProduct], int]:
    merged = dict(name_az.products)
    overlap = 0
    for identity, product in name_za.products.items():
        existing = merged.get(identity)
        if existing is None:
            merged[identity] = product
            continue
        overlap += 1
        if _material_product_fields(existing) != _material_product_fields(product):
            raise RuntimeError(
                "Alphabetical recovery found materially conflicting copies of "
                f"product {identity}; rerun to avoid merging different catalogue states"
            )

    if len(merged) != name_az.advertised_product_count:
        LOGGER.error(
            "Alphabetical recovery incomplete: advertised=%s A-Z=%s Z-A=%s "
            "overlap=%s union=%s",
            name_az.advertised_product_count,
            len(name_az.products),
            len(name_za.products),
            overlap,
            len(merged),
        )
        raise RuntimeError(
            "Alphabetical recovery was incomplete: source advertised "
            f"{name_az.advertised_product_count}, A-Z collected {len(name_az.products)}, "
            f"Z-A collected {len(name_za.products)}, overlap was {overlap}, and the "
            f"union contained {len(merged)} unique products. No incomplete catalogue "
            "will be deployed."
        )

    canonical = sorted(
        merged.items(), key=lambda entry: (entry[1].name.casefold(), entry[0])
    )
    products = [product for _, product in canonical]
    for source_order, product in enumerate(products):
        product.source_order = source_order
    return products, overlap


def _fetch_full_specials(
    *,
    source_url: str,
    result_window_pages: int,
    client: httpx.Client,
    delay_min_seconds: float,
    delay_max_seconds: float,
    sleep,
) -> ScrapeResult:
    name_az = _scrape_alphabetical_window(
        source_url=source_url,
        sort_by=NAME_ASCENDING_SORT,
        sort_label="Name A-Z",
        expected_count=None,
        result_window_pages=result_window_pages,
        client=client,
        delay_min_seconds=delay_min_seconds,
        delay_max_seconds=delay_max_seconds,
        sleep=sleep,
    )
    if len(name_az.products) == name_az.advertised_product_count:
        canonical = sorted(
            name_az.products.items(),
            key=lambda entry: (entry[1].name.casefold(), entry[0]),
        )
        products = [product for _, product in canonical]
        for source_order, product in enumerate(products):
            product.source_order = source_order
        LOGGER.info("Name Z-A was not required; Name A-Z recovered the full catalogue")
        return ScrapeResult(
            products,
            name_az.advertised_product_count,
            "name_az",
            len(name_az.products),
            None,
            0,
            len(products),
        )
    if not name_az.reached_window_limit:
        raise RuntimeError("Name A-Z recovery ended incompletely before the result window")

    name_za = _scrape_alphabetical_window(
        source_url=source_url,
        sort_by=NAME_DESCENDING_SORT,
        sort_label="Name Z-A",
        expected_count=name_az.advertised_product_count,
        result_window_pages=result_window_pages,
        client=client,
        delay_min_seconds=delay_min_seconds,
        delay_max_seconds=delay_max_seconds,
        sleep=sleep,
    )
    products, overlap = _merge_alphabetical_windows(name_az, name_za)
    LOGGER.info(
        "Alphabetical recovery complete: advertised=%s A-Z=%s Z-A=%s overlap=%s union=%s",
        name_az.advertised_product_count,
        len(name_az.products),
        len(name_za.products),
        overlap,
        len(products),
    )
    return ScrapeResult(
        products,
        name_az.advertised_product_count,
        "name_az_plus_name_za",
        len(name_az.products),
        len(name_za.products),
        overlap,
        len(products),
    )


def fetch_specials(
    source_url: str,
    max_products: int | None = 100,
    delay_min_seconds: float = 3,
    delay_max_seconds: float = 6,
    client: httpx.Client | None = None,
    sleep=time.sleep,
    result_window_pages: int = MYFOODLINK_RESULT_WINDOW_PAGES,
) -> ScrapeResult:
    if result_window_pages <= 0:
        raise ValueError("result_window_pages must be positive")
    owned_client = client is None
    client = client or httpx.Client(
        headers={"User-Agent": "PersonalTuckerCatalogue/0.1"},
        follow_redirects=True,
        timeout=30,
    )
    if max_products is None:
        try:
            return _fetch_full_specials(
                source_url=source_url,
                result_window_pages=result_window_pages,
                client=client,
                delay_min_seconds=delay_min_seconds,
                delay_max_seconds=delay_max_seconds,
                sleep=sleep,
            )
        finally:
            if owned_client:
                client.close()

    products: list[RawProduct] = []
    seen: set[str] = set()
    page = 1
    page_url = source_url
    advertised_product_count: int | None = None
    visited_urls: set[str] = set()
    try:
        while len(products) < max_products:
            if page_url in visited_urls:
                raise RuntimeError("Specials pagination looped to a previously requested URL")
            visited_urls.add(page_url)
            response = _get_page(
                client,
                page_url,
                delay_min_seconds,
                delay_max_seconds,
                sleep,
            )
            pagination = parse_pagination_metadata(response.text, str(response.url))
            if pagination.advertised_product_count is not None:
                if advertised_product_count is None:
                    advertised_product_count = pagination.advertised_product_count
                elif pagination.advertised_product_count != advertised_product_count:
                    raise RuntimeError(
                        "Source result count changed during pagination: "
                        f"expected {advertised_product_count}, page {page} advertised "
                        f"{pagination.advertised_product_count}"
                    )
            page_products = parse_specials_page(response.text, str(response.url), len(products))
            added = 0
            for raw in page_products:
                key = raw.source_product_id or normalize_product_url(raw.product_url)
                if key in seen:
                    continue
                seen.add(key)
                raw.source_order = len(products)
                products.append(raw)
                added += 1
                if len(products) >= max_products:
                    break
            LOGGER.info(
                "Page %s: %s parsed, %s unique, %s cumulative",
                page,
                len(page_products),
                added,
                len(products),
            )
            if len(products) >= max_products:
                break
            if added == 0:
                raise RuntimeError(
                    f"Specials page {page} added no unique products before the catalogue ended"
                )
            if pagination.next_url is None:
                expected_for_run = None
                if advertised_product_count is not None:
                    expected_for_run = min(max_products, advertised_product_count)
                if expected_for_run is not None and len(products) != expected_for_run:
                    raise RuntimeError(
                        "Specials scrape was incomplete: source advertised "
                        f"{advertised_product_count} products but {len(products)} unique products "
                        "were collected"
                    )
                LOGGER.info("Final page: %s", page)
                break
            page_url = pagination.next_url
            page += 1
    finally:
        if owned_client:
            client.close()
    if not products:
        raise RuntimeError("Scrape produced no products; refusing to build an empty catalogue")
    LOGGER.info("Expected source products: %s", advertised_product_count or "unknown")
    LOGGER.info("Actual unique products: %s", len(products))
    return ScrapeResult(
        products,
        advertised_product_count,
        "limited_top_products",
        None,
        None,
        None,
        len(products),
    )

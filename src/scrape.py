from __future__ import annotations

import logging
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup, Tag

from .models import RawProduct
from .normalize import normalize_product_url


LOGGER = logging.getLogger(__name__)
TRANSIENT_STATUS = {429, 500, 502, 503, 504}


@dataclass(frozen=True)
class ScrapeResult:
    products: list[RawProduct]
    advertised_product_count: int | None


@dataclass(frozen=True)
class PaginationMetadata:
    advertised_product_count: int | None
    next_url: str | None


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
            offer_text = card.get("data-offer") or _text(card, (".offer", ".promotion"))
            if not offer_text and "talker--Special" in card.get("class", []):
                offer_text = "Special"
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
                        or _text(card, (".saving", ".save", ".talker__sticker__label"))
                    ),
                    offer_text=str(offer_text) if offer_text else None,
                    scraped_at=scraped_at,
                    source_order=source_order + offset,
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


def fetch_specials(
    source_url: str,
    max_products: int | None = 100,
    delay_min_seconds: float = 3,
    delay_max_seconds: float = 6,
    client: httpx.Client | None = None,
    sleep=time.sleep,
) -> ScrapeResult:
    owned_client = client is None
    client = client or httpx.Client(
        headers={"User-Agent": "PersonalTuckerCatalogue/0.1"},
        follow_redirects=True,
        timeout=30,
    )
    products: list[RawProduct] = []
    seen: set[str] = set()
    page = 1
    page_url = source_url
    advertised_product_count: int | None = None
    visited_urls: set[str] = set()
    try:
        while max_products is None or len(products) < max_products:
            if page_url in visited_urls:
                raise RuntimeError("Specials pagination looped to a previously requested URL")
            visited_urls.add(page_url)
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
                if max_products is not None and len(products) >= max_products:
                    break
            LOGGER.info(
                "Page %s: %s parsed, %s unique, %s cumulative",
                page,
                len(page_products),
                added,
                len(products),
            )
            if max_products is not None and len(products) >= max_products:
                break
            if added == 0:
                raise RuntimeError(
                    f"Specials page {page} added no unique products before the catalogue ended"
                )
            if pagination.next_url is None:
                expected_for_run = None
                if advertised_product_count is not None:
                    expected_for_run = (
                        advertised_product_count
                        if max_products is None
                        else min(max_products, advertised_product_count)
                    )
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
    return ScrapeResult(products, advertised_product_count)

from __future__ import annotations

import logging
import random
import re
import time
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup, Tag

from .models import RawProduct
from .normalize import normalize_product_url


LOGGER = logging.getLogger(__name__)
TRANSIENT_STATUS = {429, 500, 502, 503, 504}


def parse_price_cents(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"\$?\s*(\d+(?:[.,]\d{1,2})?)", value.replace(",", ""))
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
    for selector in ("[data-product-id]", ".product-card", ".product-item", "article.product"):
        cards = list(soup.select(selector))
        if cards:
            break
    if not cards:
        raise ValueError("Specials page structure was not recognized: no product cards found")

    scraped_at = datetime.now(timezone.utc).isoformat()
    products: list[RawProduct] = []
    for offset, card in enumerate(cards):
        try:
            name = card.get("data-product-name") or _text(
                card, (".product-name", ".name", "h2", "h3")
            )
            href = card.get("data-product-url") or _attribute(
                card, ("a.product-link", "a[href]"), "href"
            )
            if not name or not href:
                raise ValueError("missing name or URL")
            image = card.get("data-image-url") or _attribute(
                card, ("img[data-src]", "img[src]"), "data-src"
            ) or _attribute(card, ("img[src]",), "src")
            products.append(
                RawProduct(
                    source_product_id=str(card.get("data-product-id")) if card.get("data-product-id") else None,
                    name=str(name),
                    product_url=urljoin(page_url, str(href)),
                    image_url=urljoin(page_url, str(image)) if image else None,
                    regular_price_cents=parse_price_cents(
                        card.get("data-regular-price") or _text(card, (".regular-price", ".was-price"))
                    ),
                    special_price_cents=parse_price_cents(
                        card.get("data-special-price") or _text(card, (".special-price", ".price"))
                    ),
                    saving_cents=parse_price_cents(
                        card.get("data-saving") or _text(card, (".saving", ".save"))
                    ),
                    offer_text=card.get("data-offer") or _text(card, (".offer", ".promotion")),
                    scraped_at=scraped_at,
                    source_order=source_order + offset,
                )
            )
        except (TypeError, ValueError) as error:
            LOGGER.warning("Skipping unparseable product card %s: %s", offset + 1, error)
    return products


def _page_url(base_url: str, page: int) -> str:
    parts = urlsplit(base_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["page"] = str(page)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def fetch_specials(
    source_url: str,
    max_products: int | None = 100,
    delay_min_seconds: float = 3,
    delay_max_seconds: float = 6,
    client: httpx.Client | None = None,
    sleep=time.sleep,
) -> list[RawProduct]:
    owned_client = client is None
    client = client or httpx.Client(
        headers={"User-Agent": "PersonalTuckerCatalogue/0.1"},
        follow_redirects=True,
        timeout=30,
    )
    products: list[RawProduct] = []
    seen: set[str] = set()
    page = 1
    try:
        while max_products is None or len(products) < max_products:
            url = source_url if page == 1 else _page_url(source_url, page)
            response = None
            last_transport_error: httpx.TransportError | None = None
            for attempt in range(3):
                try:
                    response = client.get(url)
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
            if not page_products or added == 0:
                break
            page += 1
    finally:
        if owned_client:
            client.close()
    if not products:
        raise RuntimeError("Scrape produced no products; refusing to build an empty catalogue")
    return products

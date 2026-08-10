from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import Product, RawProduct


SIZE_PATTERN = re.compile(
    r"\b(?:\d+\s*x\s*\d+(?:\.\d+)?\s*(?:kg|g|ml|l)|"
    r"\d+(?:\.\d+)?\s*(?:kg|g|ml|l)|\d+\s*(?:pk|pack))\b",
    re.IGNORECASE,
)


def normalize_name(value: str) -> str:
    value = value.lower().replace("’", "'").replace("‘", "'")
    value = re.sub(r"[^\w\s.'x-]", " ", value, flags=re.UNICODE)
    value = re.sub(r"\s+", " ", value)
    return value.strip(" .-")


def extract_size(value: str) -> str | None:
    match = SIZE_PATTERN.search(normalize_name(value))
    if not match:
        return None
    size = re.sub(r"\s+", " ", match.group(0).lower()).strip()
    size = re.sub(r"\s*(kg|g|ml|l|pk)$", r"\1", size)
    return size


def normalize_product_url(value: str) -> str:
    parts = urlsplit(value)
    query = [
        (key, item)
        for key, item in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), path, urlencode(sorted(query)), "")
    )


def normalize_offer_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").lower()).strip()


def _family_parts(name: str, flavor_terms: list[str]) -> tuple[str, str | None]:
    without_size = SIZE_PATTERN.sub(" ", name)
    matched = [term for term in flavor_terms if re.search(rf"\b{re.escape(term)}\b", without_size)]
    stem = without_size
    for term in sorted(matched, key=len, reverse=True):
        stem = re.sub(rf"\b{re.escape(term)}\b", " ", stem)
    return re.sub(r"\s+", " ", stem).strip(), ", ".join(matched) or None


def normalize_product(raw: RawProduct, flavor_terms: list[str] | None = None) -> Product:
    terms = [normalize_name(term) for term in (flavor_terms or [])]
    normalized = normalize_name(raw.name)
    family_stem, variant = _family_parts(normalized, terms)
    product_url = normalize_product_url(raw.product_url)
    product_id = raw.source_product_id or hashlib.sha256(product_url.encode()).hexdigest()[:16]
    first_word = normalized.split(maxsplit=1)[0] if normalized else None
    return Product(
        product_id=str(product_id),
        raw_name=raw.name.strip(),
        normalized_name=normalized,
        product_url=product_url,
        image_url=raw.image_url,
        brand_hint=first_word,
        size_text=extract_size(normalized),
        family_stem=family_stem,
        variant_hint=variant,
        regular_price_cents=raw.regular_price_cents,
        special_price_cents=raw.special_price_cents,
        saving_cents=raw.saving_cents,
        normalized_offer_text=normalize_offer_text(raw.offer_text),
        source_order=raw.source_order,
    )


def normalize_products(
    raw_products: list[RawProduct], flavor_terms: list[str] | None = None
) -> list[Product]:
    return [normalize_product(product, flavor_terms) for product in raw_products]

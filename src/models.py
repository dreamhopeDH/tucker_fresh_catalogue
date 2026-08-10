from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RawProduct:
    source_product_id: str | None
    name: str
    product_url: str
    image_url: str | None
    regular_price_cents: int | None
    special_price_cents: int | None
    saving_cents: int | None
    offer_text: str | None
    scraped_at: str
    source_order: int


@dataclass
class Product:
    product_id: str
    raw_name: str
    normalized_name: str
    product_url: str
    image_url: str | None
    brand_hint: str | None
    size_text: str | None
    family_stem: str
    variant_hint: str | None
    regular_price_cents: int | None
    special_price_cents: int | None
    saving_cents: int | None
    normalized_offer_text: str
    source_order: int
    category_id: str | None = None


@dataclass
class ProductFamily:
    family_id: str
    family_stem: str
    products: list[Product] = field(default_factory=list)


@dataclass
class UncertainProduct:
    product: Product
    candidate_product_id: str
    similarity: float


@dataclass
class GroupingResult:
    confirmed_families: list[ProductFamily]
    standalone_products: list[Product]
    uncertain_products: list[UncertainProduct]


@dataclass
class PromotionGroup:
    family_id: str
    family_stem: str
    products: list[Product]

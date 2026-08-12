from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import yaml
from rapidfuzz.fuzz import ratio

from .models import GroupingResult, Product, ProductFamily, UncertainProduct


UNCERTAIN_SIMILARITY_THRESHOLD = 82


def load_grouping_rules(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_manual_overrides(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {"merge": data.get("merge", []), "exclude": data.get("exclude", [])}


def _pair_set(entries: list) -> set[frozenset[str]]:
    pairs: set[frozenset[str]] = set()
    for entry in entries:
        if isinstance(entry, list) and len(entry) == 2:
            pairs.add(frozenset(map(str, entry)))
    return pairs


def group_products(
    products: list[Product],
    rules: dict | None = None,
    overrides: dict | None = None,
) -> GroupingResult:
    del rules  # Name rules are applied during normalization; boundary retained by the spec.
    overrides = overrides or {"merge": [], "exclude": []}
    excluded = _pair_set(overrides.get("exclude", []))
    forced_groups = [list(map(str, item)) for item in overrides.get("merge", []) if isinstance(item, list)]
    by_id = {product.product_id: product for product in products}
    assigned: set[str] = set()
    families: list[ProductFamily] = []

    for ids in forced_groups:
        members = sorted((by_id[item] for item in ids if item in by_id), key=lambda p: p.source_order)
        if len(members) >= 2:
            families.append(ProductFamily(f"manual-{members[0].product_id}", members[0].family_stem, members))
            assigned.update(product.product_id for product in members)

    buckets: dict[tuple[str, str], list[Product]] = defaultdict(list)
    for product in products:
        if product.product_id not in assigned and product.size_text:
            buckets[(product.family_stem, product.size_text)].append(product)

    for (stem, _size), candidates in buckets.items():
        available = [
            product
            for product in candidates
            if not any(
                frozenset((product.product_id, other.product_id)) in excluded
                for other in candidates
                if other is not product
            )
        ]
        if len(available) >= 2:
            available.sort(key=lambda p: p.source_order)
            families.append(ProductFamily(f"family-{available[0].product_id}", stem, available))
            assigned.update(product.product_id for product in available)

    remaining = [product for product in products if product.product_id not in assigned]
    uncertain_ids: set[str] = set()
    uncertain: list[UncertainProduct] = []
    fuzzy_candidates: dict[str, list[Product]] = defaultdict(list)
    for product in remaining:
        if product.size_text:
            fuzzy_candidates[product.size_text].append(product)
    for candidates in fuzzy_candidates.values():
        for index, product in enumerate(candidates):
            best: tuple[float, Product] | None = None
            for candidate in candidates[index + 1 :]:
                if frozenset((product.product_id, candidate.product_id)) in excluded:
                    continue
                score = float(ratio(product.family_stem, candidate.family_stem))
                if score >= UNCERTAIN_SIMILARITY_THRESHOLD and (
                    best is None or score > best[0]
                ):
                    best = (score, candidate)
            if best:
                uncertain.append(UncertainProduct(product, best[1].product_id, best[0]))
                uncertain.append(UncertainProduct(best[1], product.product_id, best[0]))
                uncertain_ids.update((product.product_id, best[1].product_id))

    unique_uncertain = {item.product.product_id: item for item in uncertain}
    standalone = [product for product in remaining if product.product_id not in uncertain_ids]
    families.sort(key=lambda family: min(p.source_order for p in family.products))
    standalone.sort(key=lambda product: product.source_order)
    return GroupingResult(
        families,
        standalone,
        sorted(unique_uncertain.values(), key=lambda item: item.product.source_order),
    )

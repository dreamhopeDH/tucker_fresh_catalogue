from src.grouping import group_products
from src.models import RawProduct
from src.normalize import normalize_product


FLAVORS = ["bbq", "chicken", "original"]


def product(product_id: str, name: str, order: int):
    raw = RawProduct(product_id, name, f"https://example.test/{product_id}", None, 500, 300, 200, "special", "now", order)
    return normalize_product(raw, FLAVORS)


def test_exact_family_variants_merge_but_different_size_does_not():
    products = [
        product("a", "Smith Chips BBQ 170g", 0),
        product("b", "Smith Chips Chicken 170g", 1),
        product("c", "Smith Chips BBQ 300g", 2),
    ]
    result = group_products(products)
    assert [[item.product_id for item in family.products] for family in result.confirmed_families] == [["a", "b"]]
    assert [item.product_id for item in result.standalone_products] == ["c"]


def test_similar_but_not_exact_names_are_uncertain_and_unique_is_standalone():
    products = [
        product("a", "Harvest Oat Crackers Original 200g", 0),
        product("b", "Harvest Oats Cracker Classic 200g", 1),
        product("c", "Completely Different Milk 2L", 2),
    ]
    result = group_products(products)
    assert {item.product.product_id for item in result.uncertain_products} == {"a", "b"}
    assert [item.product_id for item in result.standalone_products] == ["c"]


def test_manual_exclusion_overrides_exact_automatic_group():
    products = [
        product("a", "Smith Chips BBQ 170g", 0),
        product("b", "Smith Chips Chicken 170g", 1),
    ]
    result = group_products(products, overrides={"merge": [], "exclude": [["a", "b"]]})
    assert result.confirmed_families == []
    assert [item.product_id for item in result.standalone_products] == ["a", "b"]


def test_manual_merge_has_highest_priority():
    products = [product("a", "One Product 1kg", 0), product("b", "Other Product 2kg", 1)]
    result = group_products(products, overrides={"merge": [["a", "b"]], "exclude": []})
    assert [item.product_id for item in result.confirmed_families[0].products] == ["a", "b"]

from src.models import RawProduct
from src.normalize import extract_size, normalize_name, normalize_product


def raw(name: str) -> RawProduct:
    return RawProduct("1", name, "https://example.test/p/1", None, None, None, None, None, "now", 0)


def test_normalize_name_case_punctuation_apostrophe_and_spaces():
    assert normalize_name("  SMITH’S!!!   Chips -- BBQ  ") == "smith's chips -- bbq"


def test_extract_common_sizes():
    cases = {
        "Chips 170g": "170g",
        "Flour 1kg": "1kg",
        "Yoghurt 1.5kg": "1.5kg",
        "Drink 375ml": "375ml",
        "Milk 1L": "1l",
        "Snack 2 x 100g": "2 x 100g",
        "Cans 6pk": "6pk",
        "Tissues 12 pack": "12 pack",
        "Cola 24 x 375ml": "24 x 375ml",
    }
    for value, expected in cases.items():
        assert extract_size(value) == expected
    assert extract_size("Loose bananas") is None


def test_normalize_product_preserves_raw_and_builds_family_stem():
    product = normalize_product(raw("Smith's Chips BBQ 170g"), ["bbq", "chicken"])
    assert product.raw_name == "Smith's Chips BBQ 170g"
    assert product.family_stem == "smith's chips"
    assert product.variant_hint == "bbq"
    assert product.size_text == "170g"

from src.catalogue import build_catalogue
from src.models import Product, UncertainProduct


def product(product_id: str, order: int) -> Product:
    return Product(product_id, f"Product {product_id}", product_id, f"https://e/{product_id}", None, None, "1kg", product_id, None, 200, 100, 100, "special", order)


def test_catalogue_keeps_uncertain_items_last_and_paginates_by_display_item():
    standalone = [product(str(index), index) for index in range(10)]
    uncertain_product = product("uncertain", 2)
    object_key = "test/products/0/a81bd34f12345678.webp"
    catalogue = build_catalogue(
        confirmed_offer_groups=[],
        standalone_products=standalone,
        uncertain_products=[UncertainProduct(uncertain_product, "2", 90)],
        image_manifest={
            "0": {"status": "downloaded", "object_key": object_key}
        },
        page_size=9,
        source_product_count=11,
    )
    assert catalogue["manifest"]["page_count"] == 2
    assert catalogue["manifest"]["uncertain_start_page"] == 2
    assert catalogue["pages"][-1][-1]["type"] == "uncertain"
    assert "image_base_url" not in catalogue["manifest"]
    assert catalogue["pages"][0][0]["products"][0]["image_key"] == object_key
    assert "https://" not in str(catalogue)

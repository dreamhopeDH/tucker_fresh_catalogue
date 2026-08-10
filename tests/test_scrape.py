from pathlib import Path

import httpx

from src.scrape import fetch_specials, parse_specials_page


FIXTURE = Path(__file__).parent / "fixtures" / "specials-page.html"
TALKER_FIXTURE = Path(__file__).parent / "fixtures" / "specials-page-talker.html"


def test_parse_product_cards_and_integer_prices():
    products = parse_specials_page(FIXTURE.read_text(), "https://example.test/specials")
    assert products[0].source_product_id == "101"
    assert products[0].product_url == "https://example.test/products/chips-bbq"
    assert products[0].special_price_cents == 350
    assert products[0].regular_price_cents == 500
    assert products[0].saving_cents == 150


def test_parse_current_talker_cards_and_cents_saving():
    products = parse_specials_page(
        TALKER_FIXTURE.read_text(), "https://broadway.example.test/specials"
    )

    assert [product.source_product_id for product in products] == ["abc123", "def456"]
    assert products[0].name == "Example Crackers Sea Salt 125g"
    assert products[0].product_url == (
        "https://broadway.example.test/lines/example-crackers-sea-salt-125g"
    )
    assert products[0].image_url == "https://cdn.example.test/images/crackers.png"
    assert products[0].regular_price_cents == 500
    assert products[0].special_price_cents == 350
    assert products[0].saving_cents == 150
    assert products[0].offer_text == "Special"
    assert products[1].saving_cents == 51


def test_pagination_deduplicates_and_stops_at_limit():
    first = FIXTURE.read_text()
    second = first.replace('data-product-id="101"', 'data-product-id="103"', 1).replace("chips-bbq", "chips-new", 1)
    calls = []

    def handler(request: httpx.Request):
        calls.append(str(request.url))
        return httpx.Response(200, text=first if len(calls) == 1 else second, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    products = fetch_specials("https://example.test/specials", 3, 0, 0, client=client, sleep=lambda _: None)
    assert [product.source_product_id for product in products] == ["101", "102", "103"]
    assert len(calls) == 2


def test_temporary_transport_failure_is_retried_with_rate_limit():
    attempts = 0

    def handler(request: httpx.Request):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectError("temporary", request=request)
        return httpx.Response(200, text=FIXTURE.read_text(), request=request)

    sleeps = []
    client = httpx.Client(transport=httpx.MockTransport(handler))
    products = fetch_specials(
        "https://example.test/specials", 1, 0, 0, client=client, sleep=sleeps.append
    )
    assert len(products) == 1
    assert attempts == 2
    assert sleeps == [0, 0]

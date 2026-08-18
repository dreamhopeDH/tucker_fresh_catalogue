from pathlib import Path

import httpx
import pytest

from src.scrape import (
    NAME_ASCENDING_SORT,
    NAME_DESCENDING_SORT,
    fetch_specials,
    parse_pagination_metadata,
    parse_specials_page,
)


FIXTURE = Path(__file__).parent / "fixtures" / "specials-page.html"
TALKER_FIXTURE = Path(__file__).parent / "fixtures" / "specials-page-talker.html"


def with_pagination(html: str, total: int, next_page: int | None) -> str:
    next_link = (
        f'<a rel="next" href="/specials?page={next_page}&amp;q%5B%5D=special%3A1">Next</a>'
        if next_page is not None
        else ""
    )
    return (
        html
        + f'<div class="search-results__header"><span>{total} results</span></div>'
        + f'<div role="navigation" aria-label="Pagination">{next_link}</div>'
    )


def product_cards(start: int, count: int) -> str:
    return "".join(
        f'<article data-product-id="{index}" data-product-name="Product {index}" '
        f'data-product-url="/products/{index}" data-regular-price="$2" '
        f'data-special-price="$1"></article>'
        for index in range(start, start + count)
    )


def named_product_cards(ids: list[str], *, conflicting_id: str | None = None) -> str:
    return "".join(
        f'<article data-product-id="{product_id}" '
        f'data-product-name="Product {product_id}" '
        f'data-product-url="/products/{product_id}" data-regular-price="$2" '
        f'data-special-price="{("$1.25" if product_id == conflicting_id else "$1")}"></article>'
        for product_id in ids
    )


def alphabetical_page(
    ids: list[str], total: int, sort_by: str, next_page: int | None
) -> str:
    next_link = (
        f'<a rel="next" href="/search?page={next_page}&amp;q%5B%5D=special%3A1'
        f'&amp;sort_by={sort_by}">Next</a>'
        if next_page is not None
        else ""
    )
    return (
        named_product_cards(ids)
        + f'<div class="search-results__header"><span>{total} results</span></div>'
        + f'<div role="navigation" aria-label="Pagination">{next_link}</div>'
    )


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


def test_parses_advertised_count_and_safe_next_link():
    metadata = parse_pagination_metadata(
        with_pagination(FIXTURE.read_text(), 3_754, 2),
        "https://example.test/specials",
    )
    assert metadata.advertised_product_count == 3754
    assert metadata.next_url == (
        "https://example.test/specials?page=2&q%5B%5D=special%3A1"
    )


def test_pagination_deduplicates_and_stops_at_limit():
    first = with_pagination(FIXTURE.read_text(), 4, 2)
    second = with_pagination(
        FIXTURE.read_text()
        .replace('data-product-id="101"', 'data-product-id="103"', 1)
        .replace("chips-bbq", "chips-new", 1),
        4,
        None,
    )
    calls = []

    def handler(request: httpx.Request):
        calls.append(str(request.url))
        return httpx.Response(200, text=first if len(calls) == 1 else second, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = fetch_specials("https://example.test/specials", 3, 0, 0, client=client, sleep=lambda _: None)
    assert [product.source_product_id for product in result.products] == ["101", "102", "103"]
    assert len(calls) == 2


def test_full_recovery_stops_after_name_az_when_one_window_is_complete():
    calls = []

    def handler(request: httpx.Request):
        calls.append(str(request.url))
        return httpx.Response(
            200,
            text=alphabetical_page(["a", "b", "c", "d"], 4, NAME_ASCENDING_SORT, None),
            request=request,
        )

    result = fetch_specials(
        "https://example.test/specials",
        None,
        0,
        0,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _: None,
    )

    assert result.retrieval_strategy == "name_az"
    assert result.name_az_unique_count == 4
    assert result.name_za_unique_count is None
    assert result.final_union_unique_count == 4
    assert len(calls) == 1
    assert calls[0] == (
        "https://example.test/search?q%5B%5D=special%3A1&sort_by=name"
    )


def test_full_recovery_unions_both_alphabetical_directions():
    calls = []

    def handler(request: httpx.Request):
        calls.append(str(request.url))
        sort_by = request.url.params["sort_by"]
        ids = ["a", "b", "c", "d", "e"] if sort_by == NAME_ASCENDING_SORT else ["h", "g", "f", "e", "d"]
        return httpx.Response(
            200,
            text=alphabetical_page(ids, 8, sort_by, 2),
            request=request,
        )

    result = fetch_specials(
        "https://example.test/specials",
        None,
        0,
        0,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _: None,
        result_window_pages=1,
    )

    assert [product.source_product_id for product in result.products] == list("abcdefgh")
    assert [product.source_order for product in result.products] == list(range(8))
    assert result.retrieval_strategy == "name_az_plus_name_za"
    assert result.name_az_unique_count == 5
    assert result.name_za_unique_count == 5
    assert result.alphabetical_overlap_count == 2
    assert result.final_union_unique_count == 8
    assert len(calls) == 2


def test_full_recovery_rejects_an_incomplete_union():
    def handler(request: httpx.Request):
        sort_by = request.url.params["sort_by"]
        ids = ["a", "b", "c", "d", "e"] if sort_by == NAME_ASCENDING_SORT else ["h", "g", "f", "e", "d"]
        return httpx.Response(
            200,
            text=alphabetical_page(ids, 9, sort_by, 2),
            request=request,
        )

    with pytest.raises(RuntimeError, match="union contained 8 unique products"):
        fetch_specials(
            "https://example.test/specials",
            None,
            0,
            0,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            sleep=lambda _: None,
            result_window_pages=1,
        )


def test_full_recovery_rejects_count_change_between_directions():
    def handler(request: httpx.Request):
        sort_by = request.url.params["sort_by"]
        total = 8 if sort_by == NAME_ASCENDING_SORT else 9
        ids = ["a", "b", "c", "d", "e"] if sort_by == NAME_ASCENDING_SORT else ["h", "g", "f", "e", "d"]
        return httpx.Response(
            200,
            text=alphabetical_page(ids, total, sort_by, 2),
            request=request,
        )

    with pytest.raises(RuntimeError, match="page 1 advertised 9"):
        fetch_specials(
            "https://example.test/specials",
            None,
            0,
            0,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            sleep=lambda _: None,
            result_window_pages=1,
        )


def test_full_recovery_rejects_materially_conflicting_duplicate():
    def handler(request: httpx.Request):
        sort_by = request.url.params["sort_by"]
        ids = ["a", "b", "c"] if sort_by == NAME_ASCENDING_SORT else ["d", "c", "b"]
        html = alphabetical_page(ids, 4, sort_by, 2)
        if sort_by == NAME_DESCENDING_SORT:
            html = html.replace('data-special-price="$1"', 'data-special-price="$1.25"', 2)
        return httpx.Response(200, text=html, request=request)

    with pytest.raises(RuntimeError, match="materially conflicting copies"):
        fetch_specials(
            "https://example.test/specials",
            None,
            0,
            0,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            sleep=lambda _: None,
            result_window_pages=1,
        )


def test_full_recovery_never_requests_page_51():
    calls = []

    def handler(request: httpx.Request):
        calls.append(str(request.url))
        sort_by = request.url.params["sort_by"]
        page = int(request.url.params.get("page", "1"))
        product_id = page - 1 if sort_by == NAME_ASCENDING_SORT else 75 - page
        return httpx.Response(
            200,
            text=alphabetical_page([str(product_id)], 75, sort_by, page + 1),
            request=request,
        )

    result = fetch_specials(
        "https://example.test/specials",
        None,
        0,
        0,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _: None,
    )

    assert len(result.products) == 75
    assert len(calls) == 100
    assert not any("page=51" in url for url in calls)


def test_full_recovery_fails_on_unexpected_markup():
    def handler(request: httpx.Request):
        return httpx.Response(
            200,
            text='<span>4 results</span><p>Unexpected response</p>',
            request=request,
        )

    with pytest.raises(ValueError, match="no product cards"):
        fetch_specials(
            "https://example.test/specials",
            None,
            0,
            0,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            sleep=lambda _: None,
        )


def test_limited_mode_still_stops_at_one_hundred_products():
    calls = 0

    def handler(request: httpx.Request):
        nonlocal calls
        calls += 1
        start = (calls - 1) * 60
        return httpx.Response(
            200,
            text=with_pagination(product_cards(start, 60), 180, calls + 1),
            request=request,
        )

    result = fetch_specials(
        "https://example.test/specials",
        100,
        0,
        0,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _: None,
    )
    assert len(result.products) == 100
    assert result.products[-1].source_product_id == "99"
    assert calls == 2


def test_limited_mode_rejects_terminal_page_before_requested_limit():
    def handler(request: httpx.Request):
        return httpx.Response(
            200,
            text=with_pagination(product_cards(0, 60), 180, None),
            request=request,
        )

    with pytest.raises(RuntimeError, match="advertised 180 products but 60"):
        fetch_specials(
            "https://example.test/specials",
            100,
            0,
            0,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            sleep=lambda _: None,
        )


def test_temporary_transport_failure_is_retried_with_rate_limit():
    attempts = 0

    def handler(request: httpx.Request):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectError("temporary", request=request)
        return httpx.Response(200, text=with_pagination(FIXTURE.read_text(), 2, None), request=request)

    sleeps = []
    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = fetch_specials(
        "https://example.test/specials", 1, 0, 0, client=client, sleep=sleeps.append
    )
    assert len(result.products) == 1
    assert attempts == 2
    assert sleeps == [0, 0]

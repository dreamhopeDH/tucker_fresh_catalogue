from dataclasses import replace
from io import BytesIO

import httpx
from PIL import Image

from src.config import Settings
from src.images import convert_image, sync_images
from src.models import Product


def make_product(product_id: str, image_url: str | None, order: int) -> Product:
    return Product(product_id, product_id, product_id, f"https://e/{product_id}", image_url, None, None, product_id, None, 200, 100, 100, "", order)


def image_bytes(mode: str = "RGBA") -> bytes:
    stream = BytesIO()
    color = (255, 0, 0, 120) if mode == "RGBA" else (255, 0, 0)
    Image.new(mode, (100, 50), color).save(stream, "PNG")
    return stream.getvalue()


def test_convert_image_outputs_256_webp_and_accepts_transparency(tmp_path):
    destination = tmp_path / "product.webp"
    convert_image(image_bytes(), destination)
    with Image.open(destination) as image:
        assert image.format == "WEBP"
        assert image.size == (256, 256)
        assert image.getbbox() is not None


class FakeStore:
    def __init__(self):
        self.manifest = {
            "same": {"source_image_url": "https://e/same.png", "object_key": "test/same.webp", "status": "downloaded"}
        }
        self.images = []
        self.manifest_uploads = 0

    def download_manifest(self):
        return dict(self.manifest)

    def upload_manifest(self, manifest):
        self.manifest = dict(manifest)
        self.manifest_uploads += 1

    def upload_image(self, local_path, object_key):
        assert local_path.exists()
        self.images.append(object_key)


class FakeClient:
    def __init__(self):
        self.requests = []

    def get(self, url):
        self.requests.append(url)
        return httpx.Response(200, content=image_bytes("RGB"), request=httpx.Request("GET", url))

    def close(self):
        pass


class SequenceClient:
    def __init__(self, statuses):
        self.statuses = iter(statuses)
        self.requests = 0

    def get(self, url):
        self.requests += 1
        status, headers = next(self.statuses)
        return httpx.Response(
            status,
            headers=headers,
            content=image_bytes("RGB") if status == 200 else b"",
            request=httpx.Request("GET", url),
        )


def test_sync_resumes_skips_missing_and_downloads_sequentially(tmp_path):
    settings = replace(
        Settings.from_env(),
        output_directory=tmp_path,
        image_delay_min_seconds=0,
        image_delay_max_seconds=0,
        b2_prefix="test",
    )
    products = [
        make_product("same", "https://e/same.png", 0),
        make_product("missing", None, 1),
        make_product("new", "https://e/new.png", 2),
    ]
    store = FakeStore()
    client = FakeClient()
    sleeps = []
    manifest, stats = sync_images(products, store, settings, client=client, sleep=sleeps.append)
    assert client.requests == ["https://e/new.png"]
    assert sleeps == [0]
    assert stats["skipped"] == 1
    assert stats["missing"] == 1
    assert stats["downloaded"] == 1
    assert manifest["new"]["status"] == "downloaded"
    assert store.images[0].startswith("test/products/new/")
    assert store.manifest_uploads == 1


def test_sync_handles_one_hundred_images_without_concurrency(tmp_path):
    settings = replace(
        Settings.from_env(),
        output_directory=tmp_path,
        image_delay_min_seconds=0,
        image_delay_max_seconds=0,
    )
    products = [make_product(f"p{index}", f"https://e/{index}.png", index) for index in range(100)]
    store = FakeStore()
    store.manifest = {}
    client = FakeClient()
    sleeps = []
    _, stats = sync_images(products, store, settings, client=client, sleep=sleeps.append)
    assert len(client.requests) == 100
    assert len(sleeps) == 100
    assert stats["downloaded"] == 100
    assert len(store.images) == 100
    assert store.manifest_uploads == 21
    assert stats["image_sync_complete"] is True


def test_404_is_missing_without_retry_and_429_honors_retry_after(tmp_path):
    settings = replace(
        Settings.from_env(),
        output_directory=tmp_path,
        image_delay_min_seconds=0,
        image_delay_max_seconds=0,
    )
    missing_store = FakeStore()
    missing_store.manifest = {}
    missing_client = SequenceClient([(404, {})])
    _, missing_stats = sync_images(
        [make_product("missing-remote", "https://e/404.png", 0)],
        missing_store,
        settings,
        client=missing_client,
        sleep=lambda _: None,
    )
    assert missing_client.requests == 1
    assert missing_stats["missing"] == 1

    retry_store = FakeStore()
    retry_store.manifest = {}
    retry_client = SequenceClient([(429, {"Retry-After": "12"}), (200, {})])
    sleeps = []
    _, retry_stats = sync_images(
        [make_product("retry", "https://e/retry.png", 0)],
        retry_store,
        settings,
        client=retry_client,
        sleep=sleeps.append,
    )
    assert retry_client.requests == 2
    assert sleeps == [12, 0]
    assert retry_stats["downloaded"] == 1


def test_image_sync_budget_saves_progress_and_next_run_resumes(tmp_path):
    clock = [0.0]

    def monotonic():
        return clock[0]

    def sleep(seconds):
        clock[0] += seconds

    settings = replace(
        Settings.from_env(),
        output_directory=tmp_path,
        b2_prefix="prod",
        image_delay_min_seconds=6,
        image_delay_max_seconds=6,
        image_sync_budget_seconds=10,
    )
    products = [
        make_product(f"p{index}", f"https://e/{index}.png", index) for index in range(3)
    ]
    store = FakeStore()
    store.manifest = {}

    manifest, first_stats = sync_images(
        products,
        store,
        settings,
        client=FakeClient(),
        sleep=sleep,
        monotonic=monotonic,
    )
    assert first_stats["downloaded"] == 2
    assert first_stats["image_sync_complete"] is False
    assert first_stats["stopped_after_budget"] is True
    assert first_stats["remaining"] == 1
    assert set(manifest) == {"p0", "p1"}
    assert all(key.startswith("prod/products/") for key in store.images)
    assert store.manifest_uploads >= 1

    clock[0] = 0
    resumed_client = FakeClient()
    _, second_stats = sync_images(
        products,
        store,
        replace(settings, image_sync_budget_seconds=100),
        client=resumed_client,
        sleep=sleep,
        monotonic=monotonic,
    )
    assert resumed_client.requests == ["https://e/2.png"]
    assert second_stats["skipped"] == 2
    assert second_stats["downloaded"] == 1
    assert second_stats["image_sync_complete"] is True
    assert second_stats["stopped_after_budget"] is False
    assert second_stats["remaining"] == 0


def test_ten_consecutive_failures_mark_early_traversal_incomplete(tmp_path):
    settings = replace(
        Settings.from_env(),
        output_directory=tmp_path,
        image_delay_min_seconds=0,
        image_delay_max_seconds=0,
        image_max_attempts=1,
    )
    products = [
        make_product(f"p{index}", f"https://e/{index}.png", index)
        for index in range(11)
    ]
    store = FakeStore()
    store.manifest = {}
    client = SequenceClient([(500, {}) for _ in range(10)])

    _, stats = sync_images(
        products,
        store,
        settings,
        client=client,
        sleep=lambda _: None,
    )

    assert client.requests == 10
    assert stats["failed"] == 10
    assert stats["image_sync_complete"] is False
    assert stats["stopped_after_failures"] is True
    assert stats["remaining"] == 1
    assert store.manifest_uploads >= 1


def test_full_traversal_with_isolated_image_failures_remains_complete(tmp_path):
    settings = replace(
        Settings.from_env(),
        output_directory=tmp_path,
        image_delay_min_seconds=0,
        image_delay_max_seconds=0,
        image_max_attempts=1,
    )
    products = [
        make_product(f"p{index}", f"https://e/{index}.png", index)
        for index in range(3)
    ]
    store = FakeStore()
    store.manifest = {}
    client = SequenceClient([(500, {}), (200, {}), (404, {})])

    _, stats = sync_images(
        products,
        store,
        settings,
        client=client,
        sleep=lambda _: None,
    )

    assert client.requests == 3
    assert stats["failed"] == 1
    assert stats["missing"] == 1
    assert stats["downloaded"] == 1
    assert stats["image_sync_complete"] is True
    assert stats["stopped_after_failures"] is False
    assert stats["remaining"] == 0

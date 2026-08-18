from __future__ import annotations

import hashlib
import logging
import random
import time
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import httpx
from botocore.exceptions import BotoCoreError, ClientError
from PIL import Image, ImageOps

from .config import Settings
from .models import Product


LOGGER = logging.getLogger(__name__)


def image_has_changed(previous_url: str | None, current_url: str | None) -> bool:
    return previous_url != current_url


def image_object_key(prefix: str, product_id: str, image_url: str) -> str:
    url_hash = hashlib.sha256(image_url.encode("utf-8")).hexdigest()[:16]
    return f"{prefix.strip('/')}/products/{product_id}/{url_hash}.webp"


def convert_image(source: bytes | BytesIO | Path, destination: Path) -> None:
    if isinstance(source, Path):
        image_context = Image.open(source)
    else:
        image_context = Image.open(source if isinstance(source, BytesIO) else BytesIO(source))
    with image_context as original:
        image = ImageOps.exif_transpose(original)
        image.thumbnail((256, 256), Image.Resampling.LANCZOS)
        if "A" in image.getbands():
            canvas = Image.new("RGBA", (256, 256), (255, 255, 255, 0))
            canvas.alpha_composite(image.convert("RGBA"), ((256 - image.width) // 2, (256 - image.height) // 2))
        else:
            canvas = Image.new("RGB", (256, 256), "white")
            canvas.paste(image.convert("RGB"), ((256 - image.width) // 2, (256 - image.height) // 2))
        destination.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(destination, "WEBP", quality=78, method=6)


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def sync_images(
    products: list[Product],
    store,
    settings: Settings,
    client: httpx.Client | None = None,
    sleep=time.sleep,
    monotonic=time.monotonic,
) -> tuple[dict, dict[str, int | bool]]:
    manifest = store.download_manifest()
    stats: dict[str, int | bool] = {
        "downloaded": 0,
        "skipped": 0,
        "missing": 0,
        "failed": 0,
        "stopped_after_failures": False,
        "image_sync_complete": True,
        "stopped_after_budget": False,
        "remaining": 0,
    }
    owned_client = client is None
    client = client or httpx.Client(
        headers={"User-Agent": "PersonalTuckerCatalogue/0.1"},
        follow_redirects=True,
        timeout=settings.image_timeout_seconds,
    )
    work_directory = settings.output_directory / ".image-work"
    completed_since_upload = 0
    consecutive_failures = 0
    started_at = monotonic()

    try:
        for index, product in enumerate(sorted(products, key=lambda item: item.source_order), start=1):
            existing = manifest.get(product.product_id, {})
            if not product.image_url:
                manifest[product.product_id] = {
                    "source_image_url": None,
                    "object_key": None,
                    "status": "missing",
                    "updated_at": _timestamp(),
                }
                stats["missing"] = int(stats["missing"]) + 1
                LOGGER.info("[%s/%s] missing", index, len(products))
                completed_since_upload += 1
                consecutive_failures = 0
            elif (
                not image_has_changed(existing.get("source_image_url"), product.image_url)
                and existing.get("status") == "downloaded"
            ):
                stats["skipped"] = int(stats["skipped"]) + 1
                LOGGER.info("[%s/%s] skipped", index, len(products))
                consecutive_failures = 0
            else:
                object_key = image_object_key(settings.b2_prefix, product.product_id, product.image_url)
                status = "failed"
                for attempt in range(1, settings.image_max_attempts + 1):
                    if (
                        settings.image_sync_budget_seconds is not None
                        and monotonic() - started_at >= settings.image_sync_budget_seconds
                    ):
                        stats["image_sync_complete"] = False
                        stats["stopped_after_budget"] = True
                        stats["remaining"] = len(products) - index + 1
                        LOGGER.warning(
                            "Image sync budget reached before request %s/%s; %s products remain",
                            index,
                            len(products),
                            stats["remaining"],
                        )
                        break
                    response = None
                    try:
                        response = client.get(product.image_url)
                        if response.status_code == 404:
                            status = "missing"
                        elif response.status_code == 429:
                            status = "retry"
                        else:
                            response.raise_for_status()
                            local_path = work_directory / f"{product.product_id}.webp"
                            convert_image(response.content, local_path)
                            store.upload_image(local_path, object_key)
                            local_path.unlink(missing_ok=True)
                            status = "downloaded"
                    except (httpx.HTTPError, BotoCoreError, ClientError, OSError, ValueError) as error:
                        LOGGER.warning("Image %s attempt %s failed: %s", product.product_id, attempt, error)
                        status = "failed"

                    delay = random.uniform(
                        settings.image_delay_min_seconds,
                        settings.image_delay_max_seconds,
                    )
                    if response is not None and response.status_code == 429:
                        retry_after = response.headers.get("Retry-After")
                        try:
                            delay = max(delay, float(retry_after)) if retry_after else max(delay, 300)
                        except ValueError:
                            delay = max(delay, 300)
                    elif status == "failed" and attempt == 2:
                        delay += 30
                    sleep(delay)

                    if status in {"downloaded", "missing"}:
                        break
                    if attempt == settings.image_max_attempts:
                        status = "failed"

                if stats["stopped_after_budget"]:
                    break

                manifest[product.product_id] = {
                    "source_image_url": product.image_url,
                    "object_key": object_key if status == "downloaded" else None,
                    "status": status,
                    "updated_at": _timestamp(),
                }
                stats[status] = int(stats[status]) + 1
                LOGGER.info("[%s/%s] %s", index, len(products), status)
                completed_since_upload += 1
                if status == "failed":
                    consecutive_failures += 1
                else:
                    consecutive_failures = 0

            if completed_since_upload >= 5:
                store.upload_manifest(manifest)
                completed_since_upload = 0
            if consecutive_failures >= 10:
                remaining = len(products) - index
                if remaining > 0:
                    stats["image_sync_complete"] = False
                    stats["stopped_after_failures"] = True
                    stats["remaining"] = remaining
                    LOGGER.error(
                        "Stopping image requests after 10 consecutive failures; "
                        "%s products remain",
                        remaining,
                    )
                    break
    finally:
        store.upload_manifest(manifest)
        if owned_client:
            client.close()
    return manifest, stats

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _optional_int(name: str, default: int | None) -> int | None:
    value = os.getenv(name)
    if value is None:
        return default
    if value.strip().lower() in {"", "none"}:
        return None
    return int(value)


def _optional_float(name: str, default: float | None) -> float | None:
    value = os.getenv(name)
    if value is None:
        return default
    if value.strip().lower() in {"", "none"}:
        return None
    return float(value)


@dataclass(frozen=True)
class Settings:
    source_specials_url: str
    max_products: int | None
    page_size: int
    list_page_delay_min_seconds: float
    list_page_delay_max_seconds: float
    image_delay_min_seconds: float
    image_delay_max_seconds: float
    image_timeout_seconds: float
    image_max_attempts: int
    image_sync_budget_seconds: float | None
    b2_endpoint: str | None
    b2_key_id: str | None
    b2_application_key: str | None
    b2_bucket: str | None
    b2_prefix: str
    cloudflare_account_id: str | None
    cloudflare_api_token: str | None
    cloudflare_pages_project: str | None
    output_directory: Path = ROOT / "output"
    site_data_directory: Path = ROOT / "web" / "public" / "data"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            source_specials_url=os.getenv(
                "SOURCE_SPECIALS_URL",
                "https://broadway.shop.tuckerfresh.com.au/specials",
            ),
            max_products=_optional_int("MAX_PRODUCTS", 100),
            page_size=int(os.getenv("PAGE_SIZE", "9")),
            list_page_delay_min_seconds=float(
                os.getenv("LIST_PAGE_DELAY_MIN_SECONDS", "3")
            ),
            list_page_delay_max_seconds=float(
                os.getenv("LIST_PAGE_DELAY_MAX_SECONDS", "6")
            ),
            image_delay_min_seconds=float(os.getenv("IMAGE_DELAY_MIN_SECONDS", "5")),
            image_delay_max_seconds=float(os.getenv("IMAGE_DELAY_MAX_SECONDS", "8")),
            image_timeout_seconds=float(os.getenv("IMAGE_TIMEOUT_SECONDS", "30")),
            image_max_attempts=int(os.getenv("IMAGE_MAX_ATTEMPTS", "3")),
            image_sync_budget_seconds=_optional_float("IMAGE_SYNC_BUDGET_SECONDS", None),
            b2_endpoint=os.getenv("B2_ENDPOINT"),
            b2_key_id=os.getenv("B2_KEY_ID"),
            b2_application_key=os.getenv("B2_APPLICATION_KEY"),
            b2_bucket=os.getenv("B2_BUCKET"),
            b2_prefix=os.getenv("B2_PREFIX", "test").strip("/"),
            cloudflare_account_id=os.getenv("CLOUDFLARE_ACCOUNT_ID"),
            cloudflare_api_token=os.getenv("CLOUDFLARE_API_TOKEN"),
            cloudflare_pages_project=os.getenv("CLOUDFLARE_PAGES_PROJECT"),
        )

    def require_b2(self) -> None:
        missing = [
            name
            for name, value in {
                "B2_ENDPOINT": self.b2_endpoint,
                "B2_KEY_ID": self.b2_key_id,
                "B2_APPLICATION_KEY": self.b2_application_key,
                "B2_BUCKET": self.b2_bucket,
            }.items()
            if not value
        ]
        if missing:
            raise ValueError("Missing required B2 configuration: " + ", ".join(missing))

    def validate(self) -> None:
        if self.max_products is not None and self.max_products <= 0:
            raise ValueError("MAX_PRODUCTS must be positive or empty")
        if self.page_size <= 0:
            raise ValueError("PAGE_SIZE must be positive")
        if self.list_page_delay_min_seconds > self.list_page_delay_max_seconds:
            raise ValueError("List page delay minimum exceeds maximum")
        if self.image_delay_min_seconds > self.image_delay_max_seconds:
            raise ValueError("Image delay minimum exceeds maximum")
        if (
            self.image_sync_budget_seconds is not None
            and self.image_sync_budget_seconds <= 0
        ):
            raise ValueError("IMAGE_SYNC_BUDGET_SECONDS must be positive or empty")

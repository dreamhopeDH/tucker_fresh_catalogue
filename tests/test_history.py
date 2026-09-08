from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

import pytest

import src.main as main_module
from src.config import Settings
from src.history import (
    ensure_checkpoint,
    product_history_observation,
    promote_and_record_history,
    scheduled_history_enabled,
)
from src.models import Product


def product(
    product_id: str,
    regular: int | None = 200,
    special: int | None = 100,
    *,
    saving: int | None = 100,
    price_unit: str | None = None,
) -> Product:
    return Product(
        product_id=product_id,
        raw_name=f"Product {product_id}",
        normalized_name=product_id,
        product_url=f"https://example.test/{product_id}",
        image_url=None,
        brand_hint=None,
        size_text=None,
        family_stem=product_id,
        variant_hint=None,
        regular_price_cents=regular,
        special_price_cents=special,
        saving_cents=saving,
        normalized_offer_text="special",
        source_order=0,
        price_unit=price_unit,
    )


class FakeHistoryStore:
    def __init__(self, favourites=(), tracked=()):
        self.current_favourites = list(favourites)
        self.tracked = set(tracked)
        self.checkpoints = {}
        self.history = {}
        self.capture_calls = 0

    def get_checkpoint(self, date):
        return self.checkpoints.get(date)

    def capture_checkpoint(self, date, captured_at):
        self.capture_calls += 1
        row = {
            "checkpoint_date": date,
            "profile_id": 1,
            "favourites_json": __import__("json").dumps(self.current_favourites),
        }
        self.checkpoints.setdefault(date, row)
        return self.checkpoints[date]

    def get_tracked_products(self):
        return sorted(self.tracked)

    def add_tracked_products(self, rows):
        self.tracked.update(row[0] for row in rows)

    def insert_price_history(self, rows):
        for row in rows:
            self.history.setdefault((row["product_id"], row["checkpoint_date"]), row)


def test_removed_before_checkpoint_is_not_tracked_but_favourite_at_checkpoint_is_permanent():
    store = FakeHistoryStore(favourites=["kept"])
    checkpoint = ensure_checkpoint(store, "2026-09-02", "now")
    metrics = promote_and_record_history(store, checkpoint, [product("kept"), product("removed")], "now")
    assert store.tracked == {"kept"}
    assert metrics["newly_tracked_count"] == 1

    store.current_favourites = []
    next_checkpoint = ensure_checkpoint(store, "2026-09-09", "later")
    metrics = promote_and_record_history(store, next_checkpoint, [], "later")
    assert store.tracked == {"kept"}
    assert metrics["history_no_special_count"] == 1
    assert store.history[("kept", "2026-09-09")]["discount_percent"] == 0


def test_tracked_special_records_real_discount_and_absent_new_favourite_gets_zero():
    store = FakeHistoryStore(favourites=["new-absent"], tracked=["current"])
    checkpoint = ensure_checkpoint(store, "2026-09-02", "now")
    metrics = promote_and_record_history(store, checkpoint, [product("current", 300, 149, saving=151)], "now")
    assert store.history[("current", "2026-09-02")]["discount_percent"] == 50.3
    assert store.history[("new-absent", "2026-09-02")]["is_special"] == 0
    assert store.history[("new-absent", "2026-09-02")]["discount_percent"] == 0
    assert metrics["history_special_count"] == 1
    assert metrics["history_no_special_count"] == 1


def test_approximate_inconsistent_special_reuses_conservative_null_pricing():
    approximate = product(
        "approx", 799, 100, saving=300, price_unit="each approximately"
    )
    row = product_history_observation(
        "approx", "2026-09-02", "now", {"approx": approximate}
    )
    assert row["is_special"] == 1
    assert row["regular_price_cents"] is None
    assert row["saving_cents"] is None
    assert row["discount_percent"] is None


def test_checkpoint_rerun_reuses_original_snapshot_and_history_insert_is_idempotent():
    store = FakeHistoryStore(favourites=["first"])
    first = ensure_checkpoint(store, "2026-09-02", "now")
    store.current_favourites = ["changed"]
    rerun = ensure_checkpoint(store, "2026-09-02", "later")
    assert first.favourite_ids == rerun.favourite_ids == ("first",)
    assert rerun.reused is True
    assert store.capture_calls == 1
    promote_and_record_history(store, first, [product("first")], "now")
    original = dict(store.history[("first", "2026-09-02")])
    promote_and_record_history(store, rerun, [product("first", 400, 300, saving=100)], "later")
    assert store.history[("first", "2026-09-02")] == original


def test_only_scheduled_unlimited_live_runs_enable_history():
    assert scheduled_history_enabled(True, False, None) is True
    assert scheduled_history_enabled(False, False, None) is False
    assert scheduled_history_enabled(True, True, None) is False
    assert scheduled_history_enabled(True, False, 100) is False


def test_d1_migration_schema_and_single_owner_constraint():
    database = sqlite3.connect(":memory:")
    migration = Path("web/migrations/0001_personal_state_and_history.sql").read_text()
    database.executescript(migration)
    database.execute(
        "INSERT INTO profiles (sync_code, history_enabled, customization_json, created_at, updated_at) VALUES (?, 1, '{}', 'now', 'now')",
        ("tf1_" + "a" * 32,),
    )
    with pytest.raises(sqlite3.IntegrityError):
        database.execute(
            "INSERT INTO profiles (sync_code, history_enabled, customization_json, created_at, updated_at) VALUES (?, 1, '{}', 'now', 'now')",
            ("tf1_" + "b" * 32,),
        )


def test_d1_checkpoint_failure_happens_before_scrape_or_image_work(monkeypatch, tmp_path):
    settings = replace(
        Settings.from_env(),
        max_products=None,
        history_checkpoint_enabled=True,
        cloudflare_account_id="account",
        cloudflare_d1_database_id="database",
        cloudflare_d1_api_token="token",
        output_directory=tmp_path,
    )
    touched = {"scrape": False, "images": False}

    class BrokenStore:
        def __init__(self, *_args):
            raise RuntimeError("D1 unavailable")

    monkeypatch.setattr(main_module.Settings, "from_env", classmethod(lambda cls: settings))
    monkeypatch.setattr(main_module, "D1HistoryStore", BrokenStore)
    monkeypatch.setattr(main_module, "fetch_specials", lambda **_kwargs: touched.__setitem__("scrape", True))
    monkeypatch.setattr(main_module, "sync_images", lambda *_args: touched.__setitem__("images", True))

    with pytest.raises(RuntimeError, match="D1 unavailable"):
        main_module.run()
    assert touched == {"scrape": False, "images": False}

from src.config import Settings


def test_local_default_remains_limited_to_one_hundred(monkeypatch):
    monkeypatch.delenv("MAX_PRODUCTS", raising=False)
    assert Settings.from_env().max_products == 100


def test_production_unlimited_value_and_image_budget_are_parsed(monkeypatch):
    monkeypatch.setenv("MAX_PRODUCTS", "none")
    monkeypatch.setenv("IMAGE_SYNC_BUDGET_SECONDS", "18000")
    settings = Settings.from_env()
    assert settings.max_products is None
    assert settings.image_sync_budget_seconds == 18_000

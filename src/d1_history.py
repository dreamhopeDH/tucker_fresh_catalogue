from __future__ import annotations

import json
from collections.abc import Iterable

import httpx


class D1HistoryStore:
    def __init__(
        self,
        account_id: str,
        database_id: str,
        api_token: str,
        client: httpx.Client | None = None,
    ) -> None:
        self._owned_client = client is None
        self._client = client or httpx.Client(timeout=30)
        self._url = (
            "https://api.cloudflare.com/client/v4/accounts/"
            f"{account_id}/d1/database/{database_id}/query"
        )
        self._headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }

    def close(self) -> None:
        if self._owned_client:
            self._client.close()

    def __enter__(self) -> "D1HistoryStore":
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    def _request(self, statements: list[dict]) -> list[dict]:
        payload: dict = statements[0] if len(statements) == 1 else {"batch": statements}
        response = self._client.post(self._url, headers=self._headers, json=payload)
        response.raise_for_status()
        body = response.json()
        if not body.get("success"):
            raise RuntimeError("Cloudflare D1 request failed")
        result = body.get("result")
        if not isinstance(result, list) or any(not row.get("success", False) for row in result):
            raise RuntimeError("Cloudflare D1 statement failed")
        return result

    def query(self, sql: str, params: list | None = None) -> list[dict]:
        result = self._request([{"sql": sql, "params": params or []}])[0]
        rows = result.get("results", [])
        if not isinstance(rows, list):
            raise RuntimeError("Cloudflare D1 returned invalid rows")
        return rows

    def execute_many(self, statements: Iterable[dict], chunk_size: int = 50) -> None:
        pending: list[dict] = []
        for statement in statements:
            pending.append(statement)
            if len(pending) >= chunk_size:
                self._request(pending)
                pending = []
        if pending:
            self._request(pending)

    def get_checkpoint(self, checkpoint_date: str) -> dict | None:
        rows = self.query(
            "SELECT checkpoint_date, profile_id, favourites_json "
            "FROM history_checkpoints WHERE checkpoint_date = ?",
            [checkpoint_date],
        )
        return rows[0] if rows else None

    def capture_checkpoint(self, checkpoint_date: str, captured_at: str) -> dict:
        profiles = self.query(
            "SELECT id FROM profiles WHERE history_enabled = 1 ORDER BY id"
        )
        if len(profiles) != 1:
            raise RuntimeError("Scheduled history requires exactly one enabled profile")
        profile_id = int(profiles[0]["id"])
        favourites = self.query(
            "SELECT product_id FROM profile_favourites WHERE profile_id = ? "
            "ORDER BY product_id",
            [profile_id],
        )
        snapshot = json.dumps([row["product_id"] for row in favourites], separators=(",", ":"))
        self._request(
            [{
                "sql": "INSERT OR IGNORE INTO history_checkpoints "
                "(checkpoint_date, profile_id, captured_at, favourites_json) "
                "VALUES (?, ?, ?, ?)",
                "params": [checkpoint_date, profile_id, captured_at, snapshot],
            }]
        )
        saved = self.get_checkpoint(checkpoint_date)
        if saved is None:
            raise RuntimeError("History checkpoint could not be saved")
        return saved

    def get_tracked_products(self) -> list[str]:
        return [
            row["product_id"]
            for row in self.query("SELECT product_id FROM tracked_products ORDER BY product_id")
        ]

    def add_tracked_products(
        self, product_rows: list[tuple[str, str, str, str | None]]
    ) -> None:
        self.execute_many(
            {
                "sql": "INSERT OR IGNORE INTO tracked_products "
                "(product_id, first_checkpoint_date, first_tracked_at, last_known_name) "
                "VALUES (?, ?, ?, ?)",
                "params": list(row),
            }
            for row in product_rows
        )

    def insert_price_history(self, rows: list[dict]) -> None:
        columns = (
            "product_id", "checkpoint_date", "observed_at", "is_special",
            "regular_price_cents", "special_price_cents", "saving_cents",
            "discount_percent", "price_unit", "offer_text",
        )
        self.execute_many(
            {
                "sql": "INSERT INTO price_history (" + ", ".join(columns) + ") "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(product_id, checkpoint_date) DO NOTHING",
                "params": [row[column] for column in columns],
            }
            for row in rows
        )

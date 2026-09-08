import assert from "node:assert/strict";
import test from "node:test";

import { onRequestPost as restoreProfile } from "../functions/api/profile/restore.ts";
import {
  onRequestGet as getProfileState,
  onRequestPut as putProfileState,
} from "../functions/api/profile/state.ts";
import { onRequestGet as getProductHistory } from "../functions/api/history/[productId].ts";
import {
  DEFAULT_CUSTOMIZATIONS,
  PROFILE_COOKIE,
  validateDurableState,
} from "../functions/_shared/personal.ts";
import { historyPlotValues } from "../src/history.ts";
import {
  COLOUR_STORAGE_KEY,
  durableState,
  parseColours,
} from "../src/personal-state.ts";

type Profile = {
  id: number;
  sync_code: string;
  history_enabled: number;
  customization_json: string;
  updated_at: string;
};

class FakeStatement {
  db: FakeD1;
  sql: string;
  values: unknown[];
  constructor(db: FakeD1, sql: string, values: unknown[] = []) {
    this.db = db;
    this.sql = sql;
    this.values = values;
  }
  bind(...values: unknown[]) { return new FakeStatement(this.db, this.sql, values); }
  async first<T>(): Promise<T | null> {
    if (this.sql.includes("FROM profiles WHERE sync_code")) {
      const profile = this.db.profiles.find((row) => row.sync_code === this.values[0]);
      return (profile ?? null) as T | null;
    }
    return null;
  }
  async all<T>(): Promise<{ results: T[] }> {
    if (this.sql.includes("FROM profile_favourites")) {
      return {
        results: this.db.favourites
          .filter((row) => row.profile_id === this.values[0])
          .map((row) => ({ product_id: row.product_id })) as T[],
      };
    }
    if (this.sql.includes("FROM history_checkpoints")) {
      const productId = String(this.values[1]);
      if (!this.db.tracked.has(productId)) return { results: [] };
      return { results: this.db.history.filter((row) => row.product_id === productId) as T[] };
    }
    return { results: [] };
  }
}

class FakeD1 {
  profiles: Profile[] = [];
  favourites: { profile_id: number; product_id: string }[] = [];
  tracked = new Set<string>();
  history: Record<string, unknown>[] = [];
  lastBatchSize = 0;
  prepare(sql: string) { return new FakeStatement(this, sql); }
  async batch(statements: FakeStatement[]) {
    this.lastBatchSize = statements.length;
    for (const statement of statements) {
      if (statement.sql.startsWith("INSERT INTO profiles")) {
        this.profiles.push({
          id: this.profiles.length + 1,
          sync_code: String(statement.values[0]),
          history_enabled: 0,
          customization_json: String(statement.values[1]),
          updated_at: String(statement.values[3]),
        });
      } else if (statement.sql.startsWith("UPDATE profiles")) {
        const profile = this.profiles.find((row) => row.id === statement.values[2]);
        if (profile) {
          profile.customization_json = String(statement.values[0]);
          profile.updated_at = String(statement.values[1]);
        }
      } else if (statement.sql.startsWith("DELETE FROM profile_favourites")) {
        const profileId = typeof statement.values[0] === "number"
          ? statement.values[0]
          : this.profiles.find((row) => row.sync_code === statement.values[0])?.id;
        this.favourites = this.favourites.filter((row) => row.profile_id !== profileId);
      } else if (statement.sql.startsWith("INSERT INTO profile_favourites")) {
        const profileId = typeof statement.values[0] === "number"
          ? statement.values[0]
          : this.profiles.find((row) => row.sync_code === statement.values[0])?.id;
        const productIds = JSON.parse(String(statement.values[1])) as string[];
        this.favourites.push(...productIds.map((productId) => ({
          profile_id: Number(profileId),
          product_id: productId,
        })));
      }
    }
    return statements.map(() => ({ success: true }));
  }
}

test("existing colour JSON and durable favourites remain compatible", () => {
  const stored = JSON.stringify({ page: "#112233", price: "#445566", saving: "#778899", card: "#aabbcc" });
  const colours = parseColours(stored);
  assert.equal(COLOUR_STORAGE_KEY, "tucker-catalogue-colours-v1");
  assert.equal(colours.card, "#aabbcc");
  assert.deepEqual(durableState(["variant-b", "variant-a", "variant-b"], colours), {
    favourites: ["variant-a", "variant-b"],
    customizations: colours,
  });
  assert.ok(!("location" in durableState([], colours)));
});

test("personal state validation caps favourites and rejects unknown colours", () => {
  const valid = validateDurableState({
    favourites: ["b", "a", "a"],
    customizations: DEFAULT_CUSTOMIZATIONS,
  });
  assert.deepEqual(valid?.favourites, ["a", "b"]);
  assert.equal(validateDurableState({
    favourites: Array.from({ length: 201 }, (_, index) => `p-${index}`),
    customizations: DEFAULT_CUSTOMIZATIONS,
  }), null);
  assert.deepEqual(validateDurableState({
    favourites: Array.from({ length: 201 }, () => "one-product"),
    customizations: DEFAULT_CUSTOMIZATIONS,
  })?.favourites, ["one-product"]);
  assert.equal(validateDurableState({
    favourites: [],
    customizations: { ...DEFAULT_CUSTOMIZATIONS, header: "#000000" },
  }), null);
});

test("invalid restore leaves the profile cookie unchanged", async () => {
  const db = new FakeD1();
  const request = new Request("https://example.test/api/profile/restore", {
    method: "POST",
    headers: { "Content-Type": "application/json", Cookie: `${PROFILE_COOKIE}=tf1_${"a".repeat(32)}` },
    body: JSON.stringify({ sync_code: `tf1_${"b".repeat(32)}` }),
  });
  const response = await restoreProfile({ request, env: { PERSONAL_DB: db } } as never);
  assert.equal(response.status, 404);
  assert.equal(response.headers.get("Set-Cookie"), null);
});

test("state GET without a valid cookie returns a clean no-profile response", async () => {
  const response = await getProfileState({
    request: new Request("https://example.test/api/profile/state"),
    env: { PERSONAL_DB: new FakeD1() },
  } as never);
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("Cache-Control"), "no-store");
  assert.equal((await response.json() as { has_profile: boolean }).has_profile, false);
});

test("state PUT fully replaces existing favourites without including location", async () => {
  const code = `tf1_${"d".repeat(32)}`;
  const db = new FakeD1();
  db.profiles.push({
    id: 3,
    sync_code: code,
    history_enabled: 0,
    customization_json: JSON.stringify(DEFAULT_CUSTOMIZATIONS),
    updated_at: "old",
  });
  db.favourites.push({ profile_id: 3, product_id: "old-product" });
  const request = new Request("https://example.test/api/profile/state", {
    method: "PUT",
    headers: { "Content-Type": "application/json", Cookie: `${PROFILE_COOKIE}=${code}` },
    body: JSON.stringify({
      favourites: ["family-b", "family-a", "family-b"],
      customizations: { ...DEFAULT_CUSTOMIZATIONS, price: "#123456" },
    }),
  });
  const response = await putProfileState({ request, env: { PERSONAL_DB: db } } as never);
  const state = await response.json() as { favourites: string[] };
  assert.equal(response.status, 200);
  assert.deepEqual(state.favourites, ["family-a", "family-b"]);
  assert.deepEqual(db.favourites, [
    { profile_id: 3, product_id: "family-a" },
    { profile_id: 3, product_id: "family-b" },
  ]);
  assert.equal(db.lastBatchSize, 3);
});

test("first state PUT creates an anonymous profile with an HttpOnly 128-bit code", async () => {
  const db = new FakeD1();
  const request = new Request("https://example.test/api/profile/state", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ favourites: ["product-1"], customizations: DEFAULT_CUSTOMIZATIONS }),
  });
  const response = await putProfileState({ request, env: { PERSONAL_DB: db } } as never);
  const body = await response.json() as Record<string, unknown>;
  assert.equal(response.status, 200);
  assert.equal("sync_code" in body, false);
  assert.match(response.headers.get("Set-Cookie") ?? "", /^tf_profile=tf1_[a-f0-9]{32};/);
  assert.match(response.headers.get("Set-Cookie") ?? "", /HttpOnly; Secure; SameSite=Lax/);
  assert.equal(db.profiles[0].history_enabled, 0);
  assert.deepEqual(db.favourites, [{ profile_id: 1, product_id: "product-1" }]);
});

test("valid restore returns favourites and colours and switches profile", async () => {
  const code = `tf1_${"c".repeat(32)}`;
  const db = new FakeD1();
  db.profiles.push({
    id: 7,
    sync_code: code,
    history_enabled: 1,
    customization_json: JSON.stringify({ ...DEFAULT_CUSTOMIZATIONS, page: "#123456" }),
    updated_at: "2026-09-07T00:00:00Z",
  });
  db.favourites.push({ profile_id: 7, product_id: "family-a" }, { profile_id: 7, product_id: "family-b" });
  const request = new Request("https://example.test/api/profile/restore", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sync_code: code }),
  });
  const response = await restoreProfile({ request, env: { PERSONAL_DB: db } } as never);
  const state = await response.json() as { favourites: string[]; customizations: { page: string }; history_enabled: boolean };
  assert.equal(response.status, 200);
  assert.match(response.headers.get("Set-Cookie") ?? "", new RegExp(`^${PROFILE_COOKIE}=${code};`));
  assert.deepEqual(state.favourites, ["family-a", "family-b"]);
  assert.equal(state.customizations.page, "#123456");
  assert.equal(state.history_enabled, true);
});

test("history keeps no-special at zero and unavailable/unpriced special as gaps", () => {
  const base = {
    date: "2026-09-02",
    regular_price_cents: null,
    special_price_cents: null,
    saving_cents: null,
    price_unit: null,
    offer_text: null,
  };
  assert.deepEqual(historyPlotValues([
    { ...base, available: true, is_special: false, discount_percent: 99 },
    { ...base, available: false, is_special: null, discount_percent: null },
    { ...base, available: true, is_special: true, discount_percent: null },
    { ...base, available: true, is_special: true, discount_percent: 50 },
  ]), [0, null, null, 50]);
});

test("history endpoint remains scoped to the requested stable product ID", async () => {
  const code = `tf1_${"e".repeat(32)}`;
  const db = new FakeD1();
  db.profiles.push({ id: 9, sync_code: code, history_enabled: 1, customization_json: "{}", updated_at: "now" });
  db.tracked.add("product-a");
  db.history.push(
    { product_id: "product-a", checkpoint_date: "2026-09-02", observed_at: "now", is_special: 1, regular_price_cents: 200, special_price_cents: 100, saving_cents: 100, discount_percent: 50, price_unit: null, offer_text: "special" },
    { product_id: "product-b", checkpoint_date: "2026-09-02", observed_at: "now", is_special: 1, regular_price_cents: 400, special_price_cents: 100, saving_cents: 300, discount_percent: 75, price_unit: null, offer_text: "special" },
  );
  const request = new Request("https://example.test/api/history/product-a", {
    headers: { Cookie: `${PROFILE_COOKIE}=${code}` },
  });
  const response = await getProductHistory({
    request,
    env: { PERSONAL_DB: db },
    params: { productId: "product-a" },
  } as never);
  const body = await response.json() as { product_id: string; points: { discount_percent: number }[] };
  assert.equal(response.status, 200);
  assert.equal(body.product_id, "product-a");
  assert.deepEqual(body.points.map((point) => point.discount_percent), [50]);
});

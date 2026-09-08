export interface PersonalEnv {
  PERSONAL_DB: D1Database;
}

export const PROFILE_COOKIE = "tf_profile";
export const MAX_FAVOURITES = 200;
export const DEFAULT_CUSTOMIZATIONS = {
  page: "#ffd900",
  price: "#ed1c24",
  saving: "#ffd900",
  card: "#ffffff",
} as const;

export type Customizations = Record<keyof typeof DEFAULT_CUSTOMIZATIONS, string>;
export type DurableState = {
  favourites: string[];
  customizations: Customizations;
};

const PRODUCT_ID = /^[A-Za-z0-9._:-]{1,128}$/;
const SYNC_CODE = /^tf1_[a-f0-9]{32}$/;

export function jsonResponse(value: unknown, init: ResponseInit = {}): Response {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json; charset=utf-8");
  headers.set("Cache-Control", "no-store");
  return new Response(JSON.stringify(value), { ...init, headers });
}

export function validProductId(value: unknown): value is string {
  return typeof value === "string" && PRODUCT_ID.test(value);
}

export function validSyncCode(value: unknown): value is string {
  return typeof value === "string" && SYNC_CODE.test(value);
}

export function generateSyncCode(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return `tf1_${[...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("")}`;
}

export function profileCookie(syncCode: string): string {
  return `${PROFILE_COOKIE}=${syncCode}; Path=/; Max-Age=315360000; HttpOnly; Secure; SameSite=Lax`;
}

export function syncCodeFromRequest(request: Request): string | null {
  const header = request.headers.get("Cookie") ?? "";
  for (const part of header.split(";")) {
    const [name, ...rest] = part.trim().split("=");
    if (name === PROFILE_COOKIE) {
      const value = rest.join("=");
      return validSyncCode(value) ? value : null;
    }
  }
  return null;
}

export function parseCustomizations(value: unknown): Customizations | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const record = value as Record<string, unknown>;
  const keys = Object.keys(DEFAULT_CUSTOMIZATIONS);
  if (Object.keys(record).some((key) => !keys.includes(key))) return null;
  const result = { ...DEFAULT_CUSTOMIZATIONS } as Customizations;
  for (const key of keys as (keyof Customizations)[]) {
    const candidate = record[key];
    if (candidate === undefined) continue;
    if (typeof candidate !== "string" || !/^#[0-9a-f]{6}$/i.test(candidate)) {
      return null;
    }
    result[key] = candidate.toLowerCase();
  }
  return result;
}

export function validateDurableState(value: unknown): DurableState | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const record = value as Record<string, unknown>;
  if (
    Object.keys(record).some((key) => !["favourites", "customizations"].includes(key))
    || !Array.isArray(record.favourites)
  ) return null;
  if (!record.favourites.every(validProductId)) return null;
  const favourites = [...new Set(record.favourites)].sort();
  if (favourites.length > MAX_FAVOURITES) return null;
  const customizations = parseCustomizations(record.customizations);
  if (!customizations) return null;
  return {
    favourites,
    customizations,
  };
}

export async function readJson(request: Request): Promise<unknown> {
  const length = Number(request.headers.get("Content-Length") ?? "0");
  if (Number.isFinite(length) && length > 32_768) throw new Error("body_too_large");
  const text = await request.text();
  if (text.length > 32_768) throw new Error("body_too_large");
  return JSON.parse(text);
}

type ProfileRow = { id: number; history_enabled: number; customization_json: string; updated_at: string };

export async function findProfile(db: D1Database, syncCode: string | null): Promise<ProfileRow | null> {
  if (!syncCode) return null;
  return db.prepare(
    "SELECT id, history_enabled, customization_json, updated_at FROM profiles WHERE sync_code = ?",
  ).bind(syncCode).first<ProfileRow>();
}

export async function profileState(db: D1Database, profile: ProfileRow): Promise<object> {
  const result = await db.prepare(
    "SELECT product_id FROM profile_favourites WHERE profile_id = ? ORDER BY product_id",
  ).bind(profile.id).all<{ product_id: string }>();
  const parsed = (() => {
    try { return parseCustomizations(JSON.parse(profile.customization_json)); }
    catch { return null; }
  })();
  return {
    has_profile: true,
    favourites: result.results.map((row) => row.product_id),
    customizations: parsed ?? { ...DEFAULT_CUSTOMIZATIONS },
    history_enabled: profile.history_enabled === 1,
    metadata: { updated_at: profile.updated_at },
  };
}

export function noProfileState(): object {
  return {
    has_profile: false,
    favourites: [],
    customizations: { ...DEFAULT_CUSTOMIZATIONS },
    history_enabled: false,
    metadata: null,
  };
}

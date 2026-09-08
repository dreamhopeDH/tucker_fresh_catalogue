import {
  findProfile,
  jsonResponse,
  syncCodeFromRequest,
  validProductId,
  type PersonalEnv,
} from "../../_shared/personal.ts";

type HistoryRow = {
  checkpoint_date: string;
  observed_at: string | null;
  is_special: number | null;
  regular_price_cents: number | null;
  special_price_cents: number | null;
  saving_cents: number | null;
  discount_percent: number | null;
  price_unit: string | null;
  offer_text: string | null;
};

export const onRequestGet: PagesFunction<PersonalEnv, "productId"> = async (context) => {
  const productId = Array.isArray(context.params.productId)
    ? context.params.productId[0]
    : context.params.productId;
  if (!validProductId(productId)) return jsonResponse({ error: "Invalid product ID" }, { status: 400 });
  const db = context.env.PERSONAL_DB;
  const profile = await findProfile(db, syncCodeFromRequest(context.request));
  if (!profile) return jsonResponse({ error: "Profile required" }, { status: 401 });
  if (profile.history_enabled !== 1) return jsonResponse({ error: "History unavailable" }, { status: 403 });
  const result = await db.prepare(
    "SELECT c.checkpoint_date, h.observed_at, h.is_special, h.regular_price_cents, "
    + "h.special_price_cents, h.saving_cents, h.discount_percent, h.price_unit, h.offer_text "
    + "FROM history_checkpoints c JOIN tracked_products t ON t.product_id = ? "
    + "LEFT JOIN price_history h "
    + "ON h.checkpoint_date = c.checkpoint_date AND h.product_id = ? "
    + "WHERE c.profile_id = ? AND c.checkpoint_date >= t.first_checkpoint_date "
    + "ORDER BY c.checkpoint_date",
  ).bind(productId, productId, profile.id).all<HistoryRow>();
  return jsonResponse({
    product_id: productId,
    points: result.results.map((row) => ({
      date: row.checkpoint_date,
      available: row.observed_at !== null,
      is_special: row.is_special === null ? null : row.is_special === 1,
      regular_price_cents: row.regular_price_cents,
      special_price_cents: row.special_price_cents,
      saving_cents: row.saving_cents,
      discount_percent: row.discount_percent,
      price_unit: row.price_unit,
      offer_text: row.offer_text,
    })),
  });
};

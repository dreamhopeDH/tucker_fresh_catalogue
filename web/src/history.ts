export type HistoryPoint = {
  date: string;
  available: boolean;
  is_special: boolean | null;
  discount_percent: number | null;
  regular_price_cents: number | null;
  special_price_cents: number | null;
  saving_cents: number | null;
  price_unit: string | null;
  offer_text: string | null;
};

export function historyPlotValues(points: readonly HistoryPoint[]): (number | null)[] {
  return points.map((point) => {
    if (!point.available) return null;
    if (point.is_special === false) return 0;
    return typeof point.discount_percent === "number" ? point.discount_percent : null;
  });
}

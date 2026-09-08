export const COLOUR_STORAGE_KEY = "tucker-catalogue-colours-v1";
export const PERSONAL_SYNC_PENDING_KEY = "tucker-catalogue-personal-sync-pending-v1";
export const DEFAULT_COLOURS = {
  page: "#ffd900",
  price: "#ed1c24",
  saving: "#ffd900",
  card: "#ffffff",
} as const;

export type ColourKey = keyof typeof DEFAULT_COLOURS;
export type Colours = Record<ColourKey, string>;
export type RemotePersonalState = {
  has_profile: boolean;
  favourites: string[];
  customizations: Colours;
  history_enabled: boolean;
  metadata: { updated_at: string } | null;
};

export function validColour(value: unknown): value is string {
  return typeof value === "string" && /^#[0-9a-f]{6}$/i.test(value);
}

export function parseColours(value: string | null): Colours {
  try {
    const stored = JSON.parse(value ?? "{}") as Record<string, unknown>;
    return Object.fromEntries(
      (Object.keys(DEFAULT_COLOURS) as ColourKey[]).map((key) => [
        key,
        validColour(stored[key]) ? stored[key].toLowerCase() : DEFAULT_COLOURS[key],
      ]),
    ) as Colours;
  } catch {
    return { ...DEFAULT_COLOURS };
  }
}

export function isDefaultColours(colours: Colours): boolean {
  return (Object.keys(DEFAULT_COLOURS) as ColourKey[])
    .every((key) => colours[key] === DEFAULT_COLOURS[key]);
}

export function durableState(
  favourites: Iterable<string>,
  customizations: Colours,
): { favourites: string[]; customizations: Colours } {
  return {
    favourites: [...new Set(favourites)].sort(),
    customizations: { ...customizations },
  };
}

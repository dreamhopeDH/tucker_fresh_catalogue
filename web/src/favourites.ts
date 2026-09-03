export const FAVOURITES_STORAGE_KEY = "tucker-catalogue-favourites-v1";
export const LOCATION_STORAGE_KEY = "tucker-catalogue-location-v1";

export type FavouriteEntry = {
  id: string;
  page: number;
  product_ids: string[];
};

export type PageDescriptor =
  | { kind: "favourite"; key: string; itemIds: string[] }
  | { kind: "catalogue"; key: string; sourcePage: number };

export function parseFavouriteIds(value: string | null): string[] {
  if (!value) return [];
  try {
    const parsed: unknown = JSON.parse(value);
    if (!Array.isArray(parsed)) return [];
    return [...new Set(parsed.filter((item): item is string => typeof item === "string" && item.length > 0))].sort();
  } catch {
    return [];
  }
}

export function hasFavouriteProduct(
  productIds: readonly string[],
  favouriteIds: ReadonlySet<string>,
): boolean {
  return productIds.some((productId) => favouriteIds.has(productId));
}

export function toggleFavouriteProducts(
  currentIds: Iterable<string>,
  productIds: readonly string[],
): string[] {
  const updated = new Set(currentIds);
  const remove = hasFavouriteProduct(productIds, updated);
  productIds.forEach((productId) => remove ? updated.delete(productId) : updated.add(productId));
  return [...updated].sort();
}

export function currentFavouriteEntries<T extends FavouriteEntry>(
  entries: readonly T[],
  favouriteIds: ReadonlySet<string>,
): T[] {
  return entries.filter((entry) => hasFavouriteProduct(entry.product_ids, favouriteIds));
}

export function buildPageDescriptors(
  favouriteItemIds: readonly string[],
  cataloguePageCount: number,
  pageSize: number,
): PageDescriptor[] {
  if (pageSize <= 0) throw new Error("pageSize must be greater than zero");
  const descriptors: PageDescriptor[] = [];
  for (let index = 0; index < favouriteItemIds.length; index += pageSize) {
    descriptors.push({
      kind: "favourite",
      key: `favourite:${Math.floor(index / pageSize) + 1}`,
      itemIds: favouriteItemIds.slice(index, index + pageSize),
    });
  }
  for (let sourcePage = 1; sourcePage <= cataloguePageCount; sourcePage += 1) {
    descriptors.push({ kind: "catalogue", key: `catalogue:${sourcePage}`, sourcePage });
  }
  return descriptors;
}

export function descriptorPosition(
  descriptors: readonly PageDescriptor[],
  key: string | null,
): number | null {
  if (!key) return null;
  const index = descriptors.findIndex((descriptor) => descriptor.key === key);
  return index < 0 ? null : index + 1;
}

export function cataloguePagePosition(
  descriptors: readonly PageDescriptor[],
  sourcePage: number,
): number | null {
  return descriptorPosition(descriptors, `catalogue:${sourcePage}`);
}

export function favouriteItemPosition(
  descriptors: readonly PageDescriptor[],
  itemId: string,
): number | null {
  const index = descriptors.findIndex(
    (descriptor) => descriptor.kind === "favourite" && descriptor.itemIds.includes(itemId),
  );
  return index < 0 ? null : index + 1;
}

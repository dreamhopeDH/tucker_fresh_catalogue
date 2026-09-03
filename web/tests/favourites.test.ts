import assert from "node:assert/strict";
import test from "node:test";

import {
  buildPageDescriptors,
  cataloguePagePosition,
  currentFavouriteEntries,
  descriptorPosition,
  favouriteItemPosition,
  parseFavouriteIds,
  toggleFavouriteProducts,
} from "../src/favourites.ts";

test("favourite storage parsing is defensive and deterministic", () => {
  assert.deepEqual(parseFavouriteIds(null), []);
  assert.deepEqual(parseFavouriteIds("not json"), []);
  assert.deepEqual(parseFavouriteIds(JSON.stringify(["b", 2, "a", "b", ""])), ["a", "b"]);
});

test("a grouped item adds and removes all of its stable product IDs", () => {
  assert.deepEqual(toggleFavouriteProducts([], ["original", "barbecue"]), ["barbecue", "original"]);
  assert.deepEqual(
    toggleFavouriteProducts(["barbecue", "coffee", "original"], ["original", "barbecue"]),
    ["coffee"],
  );
});

test("only favourites present in the current specials index are resolved", () => {
  const entries = [
    { id: "current", page: 4, product_ids: ["current-product"] },
    { id: "other", page: 7, product_ids: ["other-product"] },
  ];
  const favourites = new Set(["current-product", "no-longer-on-special"]);
  assert.deepEqual(currentFavouriteEntries(entries, favourites), [entries[0]]);
});

test("favourite pages precede catalogue pages without duplicate display positions", () => {
  const favouriteIds = Array.from({ length: 15 }, (_, index) => `item-${index + 1}`);
  const descriptors = buildPageDescriptors(favouriteIds, 3, 9);

  assert.equal(descriptors.length, 5);
  assert.deepEqual(descriptors[0], {
    kind: "favourite",
    key: "favourite:1",
    itemIds: favouriteIds.slice(0, 9),
  });
  assert.deepEqual(descriptors[1], {
    kind: "favourite",
    key: "favourite:2",
    itemIds: favouriteIds.slice(9),
  });
  assert.equal(cataloguePagePosition(descriptors, 1), 3);
  assert.equal(descriptorPosition(descriptors, "catalogue:3"), 5);
  assert.equal(favouriteItemPosition(descriptors, "item-15"), 2);
});

test("no empty favourite page is created", () => {
  const descriptors = buildPageDescriptors([], 2, 9);
  assert.deepEqual(descriptors, [
    { kind: "catalogue", key: "catalogue:1", sourcePage: 1 },
    { kind: "catalogue", key: "catalogue:2", sourcePage: 2 },
  ]);
});

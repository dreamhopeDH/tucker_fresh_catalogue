import assert from "node:assert/strict";
import test from "node:test";

import { buildB2Target, normalizeObjectKey } from "../functions/images/[[path]].ts";

test("normalizes only configured production product WebP object keys", () => {
  assert.equal(
    normalizeObjectKey(["prod", "products", "product-123", "a81bd34f12345678.webp"], "prod"),
    "prod/products/product-123/a81bd34f12345678.webp",
  );
  assert.equal(
    normalizeObjectKey("prod/products/product-123/a81bd34f12345678.webp", "prod"),
    "prod/products/product-123/a81bd34f12345678.webp",
  );
  assert.equal(normalizeObjectKey(["test", "products", "product-123", "a81bd34f12345678.webp"], "prod"), null);
  assert.equal(normalizeObjectKey(["prod", "state", "image-manifest.json"], "prod"), null);
  assert.equal(normalizeObjectKey(["prod", "products", "product-123", "image.jpg"], "prod"), null);
  assert.equal(normalizeObjectKey(["prod", "products", "product-123", "short.webp"], "prod"), null);
  assert.equal(
    normalizeObjectKey(["prod", "products", "product-123", "nested", "a81bd34f12345678.webp"], "prod"),
    null,
  );
});

test("rejects traversal and malformed path segments", () => {
  for (const path of [
    ["prod", "products", "..", "a81bd34f12345678.webp"],
    ["prod", "products", "%2e%2e", "a81bd34f12345678.webp"],
    ["prod", "products", "product%2Fsecret", "a81bd34f12345678.webp"],
    ["prod", "products", "product\\secret", "a81bd34f12345678.webp"],
    [],
  ]) {
    assert.equal(normalizeObjectKey(path, "prod"), null);
  }
});

test("derives the B2 S3 region and builds a path-style object URL", () => {
  assert.deepEqual(
    buildB2Target(
      "https://s3.us-west-004.backblazeb2.com/",
      "private-catalogue",
      "prod/products/product 123/a81bd34f.webp",
    ),
    {
      url: "https://s3.us-west-004.backblazeb2.com/private-catalogue/prod/products/product%20123/a81bd34f.webp",
      region: "us-west-004",
    },
  );
});

test("rejects non-B2 endpoints and unsafe bucket configuration", () => {
  assert.equal(buildB2Target("https://example.com/", "bucket", "prod/products/p/x.webp"), null);
  assert.equal(
    buildB2Target("https://s3.us-west-004.backblazeb2.com/", "bad/bucket", "prod/products/p/x.webp"),
    null,
  );
});

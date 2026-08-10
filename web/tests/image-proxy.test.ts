import assert from "node:assert/strict";
import test from "node:test";

import { buildB2Target, normalizeObjectKey } from "../functions/images/[[path]].ts";

test("normalizes only test product WebP object keys", () => {
  assert.equal(
    normalizeObjectKey(["test", "products", "product-123", "a81bd34f12345678.webp"]),
    "test/products/product-123/a81bd34f12345678.webp",
  );
  assert.equal(
    normalizeObjectKey("test/products/product-123/a81bd34f12345678.webp"),
    "test/products/product-123/a81bd34f12345678.webp",
  );
  assert.equal(normalizeObjectKey(["test", "state", "image-manifest.json"]), null);
  assert.equal(normalizeObjectKey(["test", "products", "product-123", "image.jpg"]), null);
});

test("rejects traversal and malformed path segments", () => {
  for (const path of [
    ["test", "products", "..", "secret.webp"],
    ["test", "products", "%2e%2e", "secret.webp"],
    ["test", "products", "product%2Fsecret", "image.webp"],
    ["test", "products", "product\\secret", "image.webp"],
    [],
  ]) {
    assert.equal(normalizeObjectKey(path), null);
  }
});

test("derives the B2 S3 region and builds a path-style object URL", () => {
  assert.deepEqual(
    buildB2Target(
      "https://s3.us-west-004.backblazeb2.com/",
      "private-catalogue",
      "test/products/product 123/a81bd34f.webp",
    ),
    {
      url: "https://s3.us-west-004.backblazeb2.com/private-catalogue/test/products/product%20123/a81bd34f.webp",
      region: "us-west-004",
    },
  );
});

test("rejects non-B2 endpoints and unsafe bucket configuration", () => {
  assert.equal(buildB2Target("https://example.com/", "bucket", "test/products/p/x.webp"), null);
  assert.equal(
    buildB2Target("https://s3.us-west-004.backblazeb2.com/", "bad/bucket", "test/products/p/x.webp"),
    null,
  );
});

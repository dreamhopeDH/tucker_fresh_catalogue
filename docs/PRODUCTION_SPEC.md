# Tucker Fresh catalogue production specification

This is the active source of truth for the Tucker Fresh weekly-specials
catalogue. It promotes the validated 100-product test pipeline to the complete
current specials catalogue without changing its architecture.

## Scope and architecture

The production flow remains:

```text
Tucker Fresh server-rendered specials HTML
→ sequential httpx + BeautifulSoup scrape
→ normalization
→ deterministic family grouping
→ promotion grouping
→ four discount groups
→ static page JSON
→ Vite + vanilla TypeScript
→ existing Cloudflare Pages project
```

Images remain:

```text
Tucker Fresh image
→ sequential slow synchronizer
→ 256×256 WebP, quality 78, contained without cropping
→ private Backblaze B2
→ authenticated Cloudflare Pages Function at /images/*
→ browser
```

Do not add a database, backend API, server framework, frontend framework,
accounts, categories, admin UI, queue, PWA, Service Worker, VPS, or a separate
Worker project. Do not make the B2 bucket public.

## Production and local limits

- Production GitHub Actions sets `MAX_PRODUCTS=none` and scrapes all currently
  available unique specials.
- An unspecified local run keeps the conservative `MAX_PRODUCTS=100` default.
- Never replace the production setting with an arbitrary catalogue-size cap.
- `PAGE_SIZE` remains 9.

## Pagination and completeness

Myfoodlink exposes at most 50 pages of 48 products from one large sorted query.
Although page 50 links to page 51, page 51 returns an artificial zero-result
response. Full production recovery therefore uses the storefront's supported
alphabetical sorts:

```text
Name A-Z (`sort_by=name`)
+
Name Z-A (`sort_by=name_descending`)
+
stable product-ID deduplication
+
exact advertised-count validation
```

Each direction follows the source's server-rendered `rel="next"` links for no
more than 50 pages and never requests page 51. If Name A-Z alone reaches the
advertised count, Name Z-A is not requested. Otherwise both windows are united
by source product ID, with normalized product URL as the existing fallback.
Overlapping copies must agree on current identity, URL, name, image, price,
saving, and offer fields. A count change, conflicting overlap, or union count
different from the advertised count fails before normalization, image work, or
deployment.

Limited local runs retain the efficient bounded Top Products path and may stop
once their configured limit is reached. Retrieval order is never described as
global Top Products order because that order is not publicly recoverable beyond
the first 2,400 results.

List requests remain sequential with a random 3–6 second delay. Image requests
remain sequential with a random 5–8 second delay. Do not add concurrency,
Playwright, proxy rotation, or browser identity spoofing.

## Product ordering and grouping

After complete recovery, raw products receive a deterministic canonical internal
order by case-insensitive product name and stable identity. This makes grouping,
family membership, and image traversal reproducible; it is not display order.
Family grouping remains conservative and deterministic. Promotion grouping
remains a separate step:

```text
same family + same regular price + same special price + same offer text
→ one display item

same family + different promotion
→ separate display items
```

The four mathematical buckets remain, in order:

1. `over_50`: discount greater than 50% — “More than 50% off”
2. `exactly_50`: discount exactly 50% — “half price”
3. `forty_to_under_50`: 40% inclusive to 50% exclusive — “40% to 50% off”
4. `under_40`: discount below 40% — “Less than 40% off”

Classification uses integer-cent regular and special prices, never rounded
percentages or `saving_cents`. Each group is paginated independently; the next
group starts on a new page. Inside each discount group, display items use a
deterministic random order generated in Python with a local RNG whose seed is
exactly the advertised special-product count. Each valid/invalid and
normal/uncertain section is first sorted by stable item ID and then shuffled, so
input order does not affect output. Normal valid items precede normal
invalid-price fallback items; all normal items precede uncertain valid and then
uncertain invalid items. Invalid prices retain a null calculated discount and
the documented Group 4 fallback.

Source price units are preserved. Approximate-each prices use the compact card
label `EACH APX`; the full source wording remains available to assistive
technology. Only genuine Saving stickers populate `saving_cents`, while deal
stickers such as `3 for $3` remain offer text. If an approximate price's regular,
special, and saving values are arithmetically incompatible, catalogue output
keeps the special price and unit but suppresses misleading was/saving values,
sets the calculated discount to null, and uses the existing Group 4 fallback.

Two different weekly catalogues with the same product count intentionally reuse
the same numeric seed. Their permutations may still differ because their input
item sets differ. Browser refreshes and individual users never randomize the
catalogue.

## Production image state

Production GitHub Actions uses `B2_PREFIX=prod`:

```text
prod/products/{product_id}/{image_url_sha256_first_16}.webp
prod/state/image-manifest.json
```

The existing `test/` prefix is historical data. Production promotion never
deletes, migrates, or overwrites it. No automatic B2 garbage collection is in
scope.

Image reuse remains URL-only: unchanged URL plus `downloaded` status skips the
request immediately and does not sleep. New or changed URLs are downloaded,
converted, uploaded, and recorded. Manifest progress is uploaded every five
processed images and at stage exit.

Production sets `IMAGE_SYNC_BUDGET_SECONDS=18000`. Before each Tucker image
request, the synchronizer checks the elapsed budget. If exhausted it persists
the manifest, reports incomplete progress, exits cleanly, and does not build or
deploy a replacement catalogue. A manual rerun re-scrapes the current catalogue,
loads the same production manifest, skips completed images, and continues.

Isolated missing or failed images retain the placeholder behavior after every
current product has been visited. `image_sync_complete` is the authoritative
deployment gate. A time-budget stop or the 10-consecutive-failure guard marks
the traversal incomplete, records the remaining count, persists the manifest,
and prevents catalogue generation and deployment.

## Private image proxy

The Pages Function is `web/functions/images/[[path]].ts`. The Wrangler-managed
plaintext variable `B2_IMAGE_PREFIX=prod` restricts requests to exactly:

```text
prod/products/{product_id}/{16-hex-hash}.webp
```

It accepts GET only, rejects traversal, state files, test-prefix objects,
non-WebP objects, unsafe endpoints, and unsafe bucket values. It signs the
private S3-compatible B2 GET with `aws4fetch`, streams successful responses,
uses `caches.default`, and returns immutable cache headers.

Wrangler contains only plaintext `B2_ENDPOINT`, `B2_BUCKET`, and
`B2_IMAGE_PREFIX`. `B2_READ_KEY_ID` and `B2_READ_APPLICATION_KEY` remain
encrypted Cloudflare Pages secrets.

GitHub Actions uses a separate bucket-scoped read/write B2 key able to access
`prod/`. The Pages Function uses a separate bucket-scoped read-only key able to
access `prod/products/`. Never reuse the GitHub write key at runtime.

## Static frontend and deployment

Preserve the yellow 3×3 catalogue, product cards, swipe navigation, previous / next
controls, page selector, localStorage restoration, nearby-page lazy loading,
distant-page unloading, product detail dialog, fallback image, and active
discount-group label. The frontend creates lightweight page shells but loads
only current and adjacent page JSON. It must not eagerly render thousands of
cards.

Catalogue search remains static and framework-free. Generation writes one
lightweight `data/search-index.json` containing display-item names, variant
terms, IDs, and page numbers. The browser fetches it only when search is opened.
Selecting a result loads only its existing page JSON and reuses the existing
product-detail dialog; it does not eagerly fetch every catalogue page.

The existing Direct Upload workflow runs Wrangler from `web/` and deploys
`../output/site` to the existing `CLOUDFLARE_PAGES_PROJECT`. The `functions/`
directory therefore remains in the Pages project root.

The weekly schedule remains `17 20 * * 0` and `workflow_dispatch` remains
available. No push trigger is added. Any image-incomplete run must skip the site
build and Cloudflare deployment, leaving the current site untouched.

## Required configuration

GitHub secrets:

- `B2_KEY_ID`
- `B2_APPLICATION_KEY`
- `CLOUDFLARE_API_TOKEN`

GitHub variables:

- `B2_ENDPOINT`
- `B2_BUCKET`
- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_PAGES_PROJECT`

Cloudflare Pages encrypted secrets:

- `B2_READ_KEY_ID`
- `B2_READ_APPLICATION_KEY`

Cloudflare plaintext runtime variables are versioned in `web/wrangler.jsonc`.
No credentials may appear in generated JSON, browser JavaScript, source, or
logs.

## Validation and acceptance

Automated tests use fixtures and fake HTTP/S3 clients. Required commands are:

```text
pytest
cd web
npm run typecheck
npm run test:functions
npm run typecheck:functions
npm run build
```

Also validate fixture generation and a synthetic several-thousand-product
catalogue. Do not run a full live scrape or mass image download during routine
development.

A real production deployment is verified only by a successful manually
triggered GitHub Action. The first run may stop at the image budget several
times; each controlled stop must save progress and leave the deployed site
unchanged. A completed run rebuilds current pricing/grouping JSON and deploys
the full catalogue while retaining only image reuse state in B2.

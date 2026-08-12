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
search, accounts, categories, admin UI, queue, PWA, Service Worker, VPS, or a
separate Worker project. Do not make the B2 bucket public.

## Production and local limits

- Production GitHub Actions sets `MAX_PRODUCTS=none` and scrapes all currently
  available unique specials.
- An unspecified local run keeps the conservative `MAX_PRODUCTS=100` default.
- Never replace the production setting with an arbitrary catalogue-size cap.
- `PAGE_SIZE` remains 9.

## Pagination and completeness

The scraper follows the source page's server-rendered pagination `rel="next"`
link. It does not synthesize page URLs and does not request a page after a valid
terminal page. Product cards must remain recognizable on every requested page;
unexpected empty or structurally changed HTML fails loudly.

When the source advertises a result count, the scraper records it. An unlimited
run succeeds only when the number of collected unique products equals that
advertised count. A changed count during pagination or a short final result
fails before image synchronization and deployment. Limited local runs may stop
once their configured limit is reached.

List requests remain sequential with a random 3–6 second delay. Image requests
remain sequential with a random 5–8 second delay. Do not add concurrency,
Playwright, proxy rotation, or browser identity spoofing.

## Product ordering and grouping

Preserve Tucker Fresh `source_order` within each discount group. Family grouping
remains conservative and deterministic. Promotion grouping remains a separate
step:

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
group starts on a new page. Confirmed/standalone items precede uncertain items
inside the same group. Invalid prices use a null calculated discount and the
documented Group 4 fallback.

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

Isolated missing or failed images retain the placeholder behavior. The special
deployment block applies when the current product set was not fully traversed
because of the time budget.

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

The existing Direct Upload workflow runs Wrangler from `web/` and deploys
`../output/site` to the existing `CLOUDFLARE_PAGES_PROJECT`. The `functions/`
directory therefore remains in the Pages project root.

The weekly schedule remains `17 20 * * 0` and `workflow_dispatch` remains
available. No push trigger is added. A budget-incomplete run must skip the site
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

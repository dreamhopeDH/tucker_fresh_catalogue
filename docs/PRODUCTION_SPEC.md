# Tucker Fresh catalogue production specification

This is the active source of truth for the Tucker Fresh weekly-specials
catalogue. It promotes the validated 100-product test pipeline to the complete
current specials catalogue. The static catalogue architecture remains intact;
the sole later-approved exception is the narrowly scoped personal-state and
price-history D1 integration documented below.

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

The only persistence exception is one Cloudflare D1 database named
`tucker-fresh-personal`, bound as `PERSONAL_DB` to the existing Pages project,
plus narrowly scoped same-origin Pages Functions under `/api/profile/*` and
`/api/history/*`. D1 stores durable personal favourites/colour customization
and permanent favourite price history only. The catalogue and search remain
generated static JSON, and B2 remains private and image-only.

Do not add an account system, public history-ingest endpoint, database server,
server framework, frontend framework, categories, admin UI, queue, PWA, Service
Worker, VPS, or a separate Worker project. Do not make the B2 bucket public.

## Production and local limits

- Production GitHub Actions sets `MAX_PRODUCTS=none` and scrapes all currently
  available unique specials.
- An unspecified local run keeps the conservative `MAX_PRODUCTS=100` default.
- Never replace the production setting with an arbitrary catalogue-size cap.
- `PAGE_SIZE` remains 9.

## Pagination and completeness

Myfoodlink exposes at most 50 pages of 48 products from one large sorted query.
Page 50 may omit its next link or link to page 51, which returns an artificial
zero-result response. After validating page 50, the scraper always treats it as
the result-window boundary and never depends on that next link. Full production
recovery therefore uses the storefront's supported alphabetical sorts:

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
terms, stable member product IDs, and page numbers. The browser fetches it when
search is opened or when saved favourites must be reconciled with current
specials.
Search input rendering is debounced by 500 milliseconds. Results initially show
10 lazy-loaded thumbnails and append up to 20 more only when the user selects
the large “Search more” button.
Selecting a result loads only its existing page JSON and reuses the existing
product-detail dialog; it does not eagerly fetch every catalogue page.

The product dialog exposes a large star beside the promotion price. Stable
product IDs and the four colour customizations remain immediate, backward-
compatible `localStorage` state and asynchronously synchronize to an anonymous
D1 profile through an HttpOnly permanent Sync Code cookie. Location/page state
remains device-local and is never synchronized. API failure never prevents the
catalogue, favourites, or colours from working locally. Existing users with
durable local state silently bootstrap a profile; passive visitors do not.
Stored IDs are intersected with the current search index so products absent
from the current specials are not shown. Current favourites
form client-generated 9-item pages before the four discount groups and are
filtered from their original static pages. Original pages are not globally
repacked because that would require eagerly loading the catalogue. Navigation
uses stable favourite/catalogue page descriptors so search jumps, horizontal
swiping, nearby-page loading, and saved-page restoration remain coherent as
the number of favourite pages changes.

A small settings control sits in the top-right header area and opens a native
dialog with a prominent warning badge. Four native colour controls independently
customize the page background, price circles, saving labels, and nine product
boxes. Default restores the original yellow, red, and white palette. Colour
changes update locally immediately and debounce remote writes.

## Personal state and permanent price history

Migration `web/migrations/0001_personal_state_and_history.sql` defines
`profiles`, `profile_favourites`, `history_checkpoints`, `tracked_products`, and
`price_history`. A partial unique index permits at most one
`history_enabled=1` owner profile. Permanent Sync Codes contain at least 128
bits of server-generated entropy and are intentionally stored as plaintext in
D1. They never enter generated catalogue JSON, API state responses, or browser
storage. Frontend JavaScript handles a code only transiently when consuming an
explicit `#restore=` fragment, which it removes immediately.

`GET/PUT /api/profile/state` reads or fully replaces favourites and allowed
colour fields. PUT creates an anonymous profile only when needed, accepts at
most 200 validated stable product IDs, and replaces favourites with a D1
batch. `POST /api/profile/restore` accepts a permanent code and switches the
HttpOnly cookie only when valid. A restore URL uses
`#restore=<SYNC_CODE>`; the frontend removes the fragment immediately, then
replaces local durable state only after successful restore. All personal API
responses use `Cache-Control: no-store`.

Only the one profile manually marked `history_enabled=1` contributes to weekly
history. At the start of the scheduled Wednesday run, before scraping, GitHub
captures that profile's complete favourites for the Australia/Perth date. An
existing date reuses its original snapshot. After full source completeness has
passed and products are normalized, snapshot favourites are permanently added
to `tracked_products`, then every tracked product receives one idempotent
weekly point before image sync. Current specials use the same conservative
price sanitization and discount calculation as catalogue generation. A tracked
product absent from the complete specials receives an explicit 0%; an
unavailable checkpoint is never converted to 0. Removing a favourite does not
stop permanent tracking.

`GET /api/history/<product_id>` requires the valid history-enabled owner
profile and returns that product's points only. The product dialog fetches this
data only when the owner selects “Show discount history” and draws a small
vanilla SVG graph. No-special observations sit at 0%; failed/unavailable or
uncomputable observations are gaps.

The existing Direct Upload workflow runs Wrangler from `web/` and deploys
`../output/site` to the existing `CLOUDFLARE_PAGES_PROJECT`. The `functions/`
directory therefore remains in the Pages project root.

The weekly schedule is `0 22 * * 2` (Wednesday at 6:00 AM Perth time) and
`workflow_dispatch` remains available. No push trigger is added. Any
image-incomplete run must skip the site build and Cloudflare deployment, leaving
the current site untouched.

## Required configuration

GitHub secrets:

- `B2_KEY_ID`
- `B2_APPLICATION_KEY`
- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_D1_API_TOKEN` (separate scoped D1 Read/Write token)

GitHub variables:

- `B2_ENDPOINT`
- `B2_BUCKET`
- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_PAGES_PROJECT`
- `CLOUDFLARE_D1_DATABASE_ID`

Cloudflare Pages encrypted secrets:

- `B2_READ_KEY_ID`
- `B2_READ_APPLICATION_KEY`

Cloudflare plaintext runtime variables are versioned in `web/wrangler.jsonc`.
No credentials may appear in generated JSON, browser JavaScript, source, or
logs.

The Wrangler file declares `PERSONAL_DB` by binding and database name. Its real
Cloudflare database UUID must be added as `database_id` by the administrator
after provisioning; the repository must never invent a production UUID.

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

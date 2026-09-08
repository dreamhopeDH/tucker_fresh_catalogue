# Tucker Fresh weekly catalogue

This repository builds a mobile-first static catalogue from the complete current
Tucker Fresh Broadway specials listing. Python performs a deliberately slow,
sequential bidirectional-alphabetical scrape, exact completeness validation,
normalization, conservative family and promotion grouping, four-way discount
grouping, deterministic random display ordering, private image synchronization,
and paged JSON generation. Vite builds a framework-free TypeScript frontend for
the existing Cloudflare Pages project.

The browser never reads Backblaze B2 directly. Product images stay in a private
B2 bucket and are served through the authenticated same-origin `/images/*`
Cloudflare Pages Function.

The active architecture and acceptance criteria are in
[`docs/PRODUCTION_SPEC.md`](docs/PRODUCTION_SPEC.md). The old
`docs/TEST_MVP_SPEC.md` is historical only.

The catalogue itself remains static. One narrow Cloudflare D1/Pages Functions
exception stores anonymous personal favourites/colours and permanent owner
price history. There is still no account system, server-side catalogue, public
history ingest API, separate Worker, admin dashboard, PWA, Service Worker,
frontend framework, external queue, or automatic B2 garbage collection.

## Local fixture build

Python 3.12 and Node.js 22 are recommended.

Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd web && npm install && cd ..
python -m src.main --fixture tests/fixtures/raw-products.json
cd web && npm run typecheck && npm run build
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Set-Location web; npm install; Set-Location ..
python -m src.main --fixture tests/fixtures/raw-products.json
Set-Location web; npm run typecheck; npm run build
```

Fixture runs contact neither Tucker Fresh nor B2 and use the bundled placeholder
image. Preview with `cd web && npm run dev`, or serve `output/site` after a build.

For a local live run, copy `.env.example` to `.env`, export its values into the
shell, and run `python -m src.main`. The application does not load `.env`
automatically. The unspecified Python default remains `MAX_PRODUCTS=100` so an
accidental developer run cannot start the complete scrape. Use
`--skip-images` only for local layout debugging.

## Configuration

All application configuration is read by `src/config.py`.

| Variable | Default / purpose |
|---|---|
| `SOURCE_SPECIALS_URL` | Tucker Fresh Broadway specials page |
| `MAX_PRODUCTS` | `100` locally; production workflow explicitly sets `none` |
| `PAGE_SIZE` | `9` display items per 3×3 page |
| `LIST_PAGE_DELAY_MIN_SECONDS`, `LIST_PAGE_DELAY_MAX_SECONDS` | `3`, `6`; sequential page requests |
| `IMAGE_DELAY_MIN_SECONDS`, `IMAGE_DELAY_MAX_SECONDS` | `5`, `8`; sequential image requests |
| `IMAGE_TIMEOUT_SECONDS`, `IMAGE_MAX_ATTEMPTS` | `30`, `3` |
| `IMAGE_SYNC_BUDGET_SECONDS` | Empty locally; production uses `18000` seconds |
| `B2_ENDPOINT`, `B2_KEY_ID`, `B2_APPLICATION_KEY`, `B2_BUCKET` | Authenticated S3-compatible B2 upload connection |
| `B2_PREFIX` | `test` locally; production workflow explicitly sets `prod` |
| `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_PAGES_PROJECT` | CI deployment configuration |
| `HISTORY_CHECKPOINT_ENABLED` | `false`; the workflow sets true only for scheduled runs |
| `CLOUDFLARE_D1_DATABASE_ID`, `CLOUDFLARE_D1_API_TOKEN` | Scheduled history only; D1 database ID and separate scoped Read/Write token |

Do not reduce the request delays or add concurrency for the production
catalogue. To change the safe local product cap, edit `MAX_PRODUCTS`; production
must remain `none`, not a guessed numeric catalogue size.

## Production pagination safety

Myfoodlink exposes only 50 pages of 48 products from one large sorted query,
even when it advertises a larger result set. Production therefore retrieves the
public `Name A-Z` (`sort_by=name`) and `Name Z-A`
(`sort_by=name_descending`) windows sequentially. It follows each sort's real
`rel="next"` links but stops at page 50 without requesting the unusable page 51.
If Name A-Z already contains the advertised total, Name Z-A is skipped.

The windows are deduplicated by stable source product ID, falling back to
normalized product URL only when an ID is unavailable. Overlapping copies must
agree on material product and promotion fields. The advertised count must stay
constant, and the final unique union must equal it exactly. Any conflict,
changing count, malformed page, or incomplete union fails before image work and
deployment.

Retrieval order is not display order. After canonical internal ordering, items
are randomized deterministically inside each of the four discount groups. The
seed is exactly the source-advertised specials count, and generated metadata
records the ordering mode and seed. The same complete input and count produce
the same pages across image warm-up reruns.

## Backblaze B2 production setup

The existing bucket remains **private**. Do not create a public bucket and do not
reuse the GitHub write key inside Cloudflare.

Production state is separate from the historical test namespace:

```text
prod/products/{product_id}/{image_url_hash}.webp
prod/state/image-manifest.json
```

Existing `test/` objects are left untouched. Old production image objects may
also remain; this project does not delete or garbage-collect B2 data.

Create or verify two separate bucket-scoped Backblaze Application Keys:

1. **GitHub Actions upload key:** read/write access to `prod/`, including
   `prod/products/` and `prod/state/image-manifest.json`.
2. **Cloudflare Pages runtime key:** Read Only access to `prod/products/`.

If either current key is name-prefix restricted to `test/` or `test/products/`,
create a replacement with the production access above and update the
corresponding existing secrets before the first production run. Never paste key
values into source files, Wrangler configuration, generated JSON, or logs.

The image manifest is uploaded every five processed images and again whenever
the stage exits. Unchanged downloaded URLs are skipped immediately without a
request or sleep. Images remain 256×256 WebP at quality 78 with contained,
uncropped packaging.

## Cloudflare Pages setup

Continue using the existing Direct Upload Pages project; do not create a new
project or separate Worker.

`web/wrangler.jsonc` is the Wrangler-managed Pages configuration. It contains
the plaintext runtime variables:

- `B2_ENDPOINT`
- `B2_BUCKET`
- `B2_IMAGE_PREFIX=prod`

It also declares the `PERSONAL_DB` D1 binding for database
`tucker-fresh-personal`. After creating the real database, add its real UUID as
`database_id` in that binding before deploying. No placeholder production UUID
is committed.

The user does not create those plaintext variables manually in the Dashboard.
In **Settings → Variables and Secrets**, keep only these encrypted runtime
secrets, for Production and Preview as required:

- `B2_READ_KEY_ID`
- `B2_READ_APPLICATION_KEY`

The read key must be able to access `prod/products/`. The Vite output and Pages
deployment directory are `../output/site` from `web/`. CI runs Wrangler from
`web/`, so `web/functions/images/[[path]].ts` is definitely included in the
Direct Upload deployment.

The Function accepts GET only and permits only
`prod/products/<product>/<16-hex-hash>.webp`. It rejects the test prefix,
manifest/state objects, traversal, malformed paths, and other file types. It
signs the private B2 GET with `aws4fetch`, streams the response, and uses
Cloudflare's Cache API with immutable HTTP cache headers.

### D1 provisioning and owner setup

From `web/`, authenticate Wrangler to the same Cloudflare account, then:

```bash
npx wrangler d1 create tucker-fresh-personal
# Add the returned database_id to web/wrangler.jsonc under PERSONAL_DB.
npx wrangler d1 migrations apply tucker-fresh-personal --remote
```

Deploy the Pages project once after adding the binding. Visit the deployed site
from the owner's existing browser; saved favourites or non-default colours will
silently create a profile. Then use the D1 console to identify and enable only
that owner profile:

```sql
SELECT p.id, p.updated_at, COUNT(f.product_id) AS favourite_count
FROM profiles p
LEFT JOIN profile_favourites f ON f.profile_id = p.id
GROUP BY p.id, p.updated_at
ORDER BY p.updated_at DESC;

UPDATE profiles SET history_enabled = 1 WHERE id = <OWNER_PROFILE_ID>;
SELECT sync_code FROM profiles WHERE id = <OWNER_PROFILE_ID>;
```

The partial unique index prevents enabling a second owner. For recovery,
construct `https://<site>/#restore=<sync_code>` from the console value and send
it privately to the user. The fragment is removed from browser history as soon
as it is captured. Do not paste Sync Codes into issues, logs, source, or static
JSON.

## GitHub Actions configuration

Under **Repository → Settings → Secrets and variables → Actions**, keep these
GitHub secrets:

- `B2_KEY_ID`
- `B2_APPLICATION_KEY`
- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_D1_API_TOKEN` (a separate token scoped to D1 Read/Write)

Keep these GitHub variables:

- `B2_ENDPOINT`
- `B2_BUCKET`
- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_PAGES_PROJECT`
- `CLOUDFLARE_D1_DATABASE_ID`

The endpoint and bucket are needed separately by GitHub's uploader and by the
Cloudflare runtime configuration. The Cloudflare `B2_READ_*` secrets are not
frontend build variables and do not belong in GitHub Actions.

The production workflow explicitly uses:

```text
MAX_PRODUCTS=none
B2_PREFIX=prod
IMAGE_SYNC_BUDGET_SECONDS=18000
PAGE_SIZE=9
timeout-minutes=350
```

It supports manual `workflow_dispatch` and runs weekly at `0 22 * * 2`, which
is Wednesday 06:00 in Australia/Perth. There is no push trigger. Only the
scheduled event enables a history checkpoint; manual runs do not create one.

## First production run and resumable image warm-up

1. Push the production changes to `main`.
2. Confirm the GitHub read/write B2 key can access `prod/`.
3. Confirm the Cloudflare read-only B2 key can access `prod/products/`.
4. Open **GitHub → Actions → Update production catalogue**.
5. Select **Run workflow**, choose `main`, and run it.
6. The Action runs tests, recovers the source through Name A-Z and, when
   required, Name Z-A, validates the exact union count, deterministically orders
   the catalogue, and begins the sequential image warm-up.
7. If the five-hour image budget or 10-consecutive-failure guard stops traversal,
   the Action saves
   `prod/state/image-manifest.json`, reports the approximate remaining count,
   skips build/deployment, and leaves the currently deployed site untouched.
8. Manually run the workflow again. It re-scrapes current specials, quickly
   skips unchanged completed images, and continues the remaining work.
9. Repeat only when the summary instructs you to. Once image traversal is
   complete, the Action writes all page JSON, builds Vite, and deploys to the
   existing Cloudflare Pages project.

Equivalent authenticated GitHub CLI commands are:

```bash
gh workflow run update-catalogue.yml --ref main
gh run watch
```

The run summary reports alphabetical retrieval counts and overlap, source and
actual counts, ordering seed, grouping totals, four discount-group counts,
scheduled checkpoint/tracking metrics, pages, image traversal status, and
deployment result. The
`catalogue-debug-<run number>` artifact includes:

- `output/raw-products.json`
- `output/normalized-products.json`
- `output/grouping-result.json`
- `output/catalogue-manifest.json` when catalogue generation completed
- `output/run-summary.json`

Only a successful real Action verifies the production B2 and Cloudflare
integration. Local mocks do not.

## Catalogue behavior

The frontend remains a yellow mobile-first 3×3 catalogue with horizontal swipe,
previous/next buttons, page selector, current-page restoration, active discount
group label, nearby JSON lazy loading, distant DOM unloading, product-detail
dialog, and placeholder fallback. It does not fetch all page JSON or render all
product cards at startup. The lightweight `data/search-index.json` is fetched
when the user opens search or has saved favourites; choosing a result loads that
item's existing page and opens the existing product-detail dialog.

The detail dialog's star stores favourites immediately in that browser's
existing `localStorage` format and asynchronously synchronizes favourites and
colour settings to an anonymous D1 profile. The permanent Sync Code remains in
an HttpOnly cookie, and location/page position is never synchronized.
Current favourites appear in 9-item Favourite pages before the discount groups
and are removed from their original pages. Saved IDs are reconciled with each
new catalogue, so products not present in current specials remain hidden.
If D1 is unavailable, local behaviour continues and the pending full-state
write is retried. A valid `#restore=` link replaces durable favourites/colours
rather than merging profiles.

For the manually enabled owner profile, the detail dialog exposes a lazy
“Discount history” control. Grouped variants remain separately selectable. The
vanilla SVG line uses 0% for a successful no-special week and a gap for an
unavailable or safely uncomputable observation.

The four exact discount boundaries remain:

1. greater than 50%;
2. exactly 50%;
3. 40% inclusive to less than 50%;
4. less than 40%.

Each group starts on a new page. Promotion groups in the same family remain
separate when their prices or offer text differ. Current prices and group
membership are rebuilt from the live source each week; D1 persists explicitly
tracked owner product history while B2 remains image-only. Items are deterministically randomized within
each group, while normal items remain ahead of uncertain items and invalid-price
fallback boundaries remain intact. Randomization occurs in Python, never in the
browser.

Price units from the storefront are retained. Approximate-each offers use a
compact `EACH APX` label beneath the numeric price. Deal stickers are not treated
as saving amounts, and incompatible approximate regular/special/saving values
are displayed conservatively without a misleading was price or saving.

## Grouping overrides

Edit `config/manual_overrides.yml`. `merge` accepts product-ID lists to force
into a family; `exclude` accepts two-ID pairs that must not be grouped:

```yaml
merge:
  - ["product-101", "product-102"]
exclude:
  - ["product-201", "product-202"]
```

Flavor tokens live in `config/grouping_rules.yml`. Similarity alone only marks
products uncertain; it never confirms a merge.

## Tests

```bash
pytest
cd web
npm run typecheck
npm run test:functions
npm run typecheck:functions
npm run build
```

Tests use local fixtures, synthetic product sets, and fake HTTP/S3 clients. They
do not perform a full live scrape, real B2 write, or Cloudflare deployment.

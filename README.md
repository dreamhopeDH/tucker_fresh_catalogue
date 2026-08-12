# Tucker Fresh weekly catalogue

This repository builds a mobile-first static catalogue from the complete current
Tucker Fresh Broadway specials listing. Python performs a deliberately slow,
sequential scrape, normalization, conservative family and promotion grouping,
four-way discount grouping, private image synchronization, and paged JSON
generation. Vite builds a framework-free TypeScript frontend for the existing
Cloudflare Pages project.

The browser never reads Backblaze B2 directly. Product images stay in a private
B2 bucket and are served through the authenticated same-origin `/images/*`
Cloudflare Pages Function.

The active architecture and acceptance criteria are in
[`docs/PRODUCTION_SPEC.md`](docs/PRODUCTION_SPEC.md). The old
`docs/TEST_MVP_SPEC.md` is historical only.

The project intentionally has no database, API server, admin dashboard, PWA,
Service Worker, search, accounts, categories, frontend framework, external
queue, or automatic B2 garbage collection.

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

Do not reduce the request delays or add concurrency for the production
catalogue. To change the safe local product cap, edit `MAX_PRODUCTS`; production
must remain `none`, not a guessed numeric catalogue size.

## Production pagination safety

The scraper follows the exact server-rendered `rel="next"` URL and records the
source-advertised result count. An unlimited run deploys only after the actual
unique product count matches that advertised total. Unexpected empty markup,
pagination loops, changing result counts, and truncated final results fail
loudly before deployment.

During the production promotion audit on 12 August 2026, the live source
advertised 3,754 results, rendered valid pages through page 50, linked to page
51, and returned a zero-result page at page 51. If that upstream deep-pagination
cap remains, the production Action will intentionally fail its completeness
check rather than publish a truncated catalogue. Do not bypass this protection
by weakening the count check or changing the sort order, because the latter
would lose Tucker Fresh's required source ordering.

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

## GitHub Actions configuration

Under **Repository → Settings → Secrets and variables → Actions**, keep these
GitHub secrets:

- `B2_KEY_ID`
- `B2_APPLICATION_KEY`
- `CLOUDFLARE_API_TOKEN`

Keep these GitHub variables:

- `B2_ENDPOINT`
- `B2_BUCKET`
- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_PAGES_PROJECT`

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

It supports manual `workflow_dispatch` and runs weekly at `17 20 * * 0`, which
is Monday 04:17 in Perth. There is no push trigger.

## First production run and resumable image warm-up

1. Push the production changes to `main`.
2. Confirm the GitHub read/write B2 key can access `prod/`.
3. Confirm the Cloudflare read-only B2 key can access `prod/products/`.
4. Open **GitHub → Actions → Update production catalogue**.
5. Select **Run workflow**, choose `main`, and run it.
6. The Action runs tests, scrapes the full current source, validates
   completeness, groups products, and begins the sequential image warm-up.
7. If the five-hour image budget is reached, the Action saves
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

The run summary reports source and actual counts, grouping totals, four discount
group counts, pages, image progress, budget status, and deployment result. The
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
product cards at startup.

The four exact discount boundaries remain:

1. greater than 50%;
2. exactly 50%;
3. 40% inclusive to less than 50%;
4. less than 40%.

Each group starts on a new page. Promotion groups in the same family remain
separate when their prices or offer text differ. Current prices and group
membership are rebuilt from the live source each week; B2 persists image reuse
state only, not price history.

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

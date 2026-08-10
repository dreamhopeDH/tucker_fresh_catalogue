# Tucker Fresh 100-product test catalogue

This repository builds a mobile-first static weekly-specials catalogue from the first 100 unique products returned by the Tucker Fresh Broadway specials pages. It is deliberately a test MVP: Python scrapes and normalizes data, conservatively groups product families, synchronizes resized images to Backblaze B2, writes paged JSON, and Vite builds a framework-free TypeScript site for Cloudflare Pages.

It does not contain an API, database, admin dashboard, PWA, Service Worker, category system, search, accounts, or a frontend framework.

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

The fixture path never contacts the source site or B2 and uses the bundled placeholder image. Preview the production output with `cd web && npm run dev`, or use any static server rooted at `output/site` after the production build.

For a real pipeline run, copy `.env.example` to `.env`, export those values into the shell (`set -a; source .env; set +a` on Bash; set them with `$env:NAME="value"` in PowerShell), then run `python -m src.main`. The application intentionally does not load `.env` itself. A live run is intentionally slow: list requests wait 3–6 seconds and each image request waits 5–8 seconds. `--skip-images` is available only for local layout debugging.

## Configuration

All runtime configuration is read in `src/config.py`:

| Variable | Default / purpose |
|---|---|
| `SOURCE_SPECIALS_URL` | Tucker Fresh Broadway specials URL |
| `MAX_PRODUCTS` | `100`; set empty or `None` only for a future full run |
| `PAGE_SIZE` | `9` display items per 3×3 page |
| `LIST_PAGE_DELAY_MIN_SECONDS`, `LIST_PAGE_DELAY_MAX_SECONDS` | `3`, `6` |
| `IMAGE_DELAY_MIN_SECONDS`, `IMAGE_DELAY_MAX_SECONDS` | `5`, `8` |
| `IMAGE_TIMEOUT_SECONDS`, `IMAGE_MAX_ATTEMPTS` | `30`, `3` |
| `B2_ENDPOINT`, `B2_KEY_ID`, `B2_APPLICATION_KEY`, `B2_BUCKET` | B2 S3-compatible connection |
| `B2_PREFIX` | `test` |
| `IMAGE_BASE_URL` | Public/CDN base URL for B2 image keys |
| `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_PAGES_PROJECT` | Deployment configuration used by CI |

The test workflow pins `MAX_PRODUCTS=100` and `B2_PREFIX=test`. Adjust the delay variables rather than editing downloader code. The limited future full-catalogue extension is `MAX_PRODUCTS=`; no alternate scraper is needed.

## Backblaze B2 setup

1. Create or choose a B2 bucket. Images must be reachable through a public bucket URL or a separately configured public CDN; use that URL as `B2_PUBLIC_BASE_URL`/`IMAGE_BASE_URL`.
2. Create a bucket-scoped application key with read/write access needed for objects under `test/`. Do not commit or paste the key into source files.
3. Use the bucket's S3 endpoint for `B2_ENDPOINT`, not the native B2 API URL.
4. The pipeline stores images at `test/products/{product_id}/{url_hash}.webp` and its resumable manifest at `test/state/image-manifest.json`. The manifest is uploaded every five completed images and once at stage end.

To clear test data, first inspect the exact `test/` prefix in the B2 console or with a dry-run-capable tool, then delete only that prefix after confirming the target. Removing it is destructive and forces all images to download again.

## Cloudflare Pages setup

1. In Cloudflare, create a Direct Upload Pages project named (recommended) `tucker-catalogue-test`.
2. Create an API token with Account → Cloudflare Pages → Edit for the relevant account.
3. The Vite production command is `npm run build`; its output directory is `output/site`. `web/wrangler.jsonc` records the same build output.
4. CI deploys the prebuilt directory with Wrangler. There are no Pages Functions or Workers.

## Required GitHub Actions secrets

Add these under **Repository → Settings → Secrets and variables → Actions → New repository secret**:

- `B2_ENDPOINT`
- `B2_KEY_ID`
- `B2_APPLICATION_KEY`
- `B2_BUCKET`
- `B2_PUBLIC_BASE_URL`
- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_PAGES_PROJECT`

## First 100-product Action

1. Push this repository, including `.github/workflows/update-catalogue.yml`, to the default branch.
2. Complete the B2 and Cloudflare setup above and add all eight repository secrets.
3. Open **GitHub → Actions → Update test catalogue**.
4. Select **Run workflow**, choose the default branch, and select **Run workflow** again.
5. Wait for the `update` job. It will test, scrape exactly the first 100 unique products when available, slowly process images, build, and deploy.
6. Open the run summary and verify the product/image/page counts and Cloudflare deployment result. Download `catalogue-debug-<run number>` from the run's **Artifacts** section for the four JSON diagnostics.
7. Open the Pages deployment URL on Android and verify swipe, buttons, jump navigation, page restoration, the complete 3×3 grid, and image fallbacks.

Equivalent GitHub CLI trigger after authentication:

```bash
gh workflow run update-catalogue.yml --ref main
gh run watch
```

The schedule is `17 20 * * 0` (Monday 04:17 in Perth). Only a successful real Action verifies B2 and Cloudflare integration; mocked tests do not.

## Grouping overrides

Edit `config/manual_overrides.yml`. `merge` accepts lists of product IDs to force into a family; `exclude` accepts two-ID pairs that must not be grouped:

```yaml
merge:
  - ["product-101", "product-102"]
exclude:
  - ["product-201", "product-202"]
```

Flavor tokens used to form conservative exact family stems live in `config/grouping_rules.yml`. Similarity alone only marks products uncertain; it never confirms a merge.

## Tests

```bash
pytest
cd web
npm run typecheck
npm run build
```

Tests use local HTML/JSON/image fixtures and fake HTTP/S3 clients. They never depend on the live retailer, B2, or Cloudflare. Generated runtime output is ignored by Git.

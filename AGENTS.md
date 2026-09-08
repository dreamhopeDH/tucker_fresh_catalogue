# Project instructions

Before making any code changes, read:

- `docs/PRODUCTION_SPEC.md`
- `docs/reference/catalogue-layout.png`

`docs/PRODUCTION_SPEC.md` is the active source of truth for scope, architecture,
acceptance criteria, and explicitly excluded features. `docs/TEST_MVP_SPEC.md`
is retained only as the historical test-phase specification.

## Development rules

- Preserve the existing full-current-specials production architecture.
- Keep the unspecified local live-run default at `MAX_PRODUCTS=100`; the
  production GitHub Action explicitly uses `MAX_PRODUCTS=none`.
- The one approved persistence exception is the existing Pages project's
  `PERSONAL_DB` D1 binding and narrowly scoped `/api/profile/*` and
  `/api/history/*` Pages Functions for durable personal state and permanent
  favourite price history. Do not expand this into an account system, public
  history-ingest API, separate Worker, backend framework, or server-side
  catalogue.
- Do not add another database, database server, admin dashboard, PWA, Service
  Worker, React, Vue, Svelte, or other unrequested systems.
- Keep source and image requests sequential and retain their configured delays.
- Keep the B2 bucket private and never place credentials in source code or logs.
- Prefer simple functions and modules over generic frameworks.
- Do not claim external deployment succeeded unless it was actually executed
  successfully.
- Use the reference image as the visual direction, without copying retailer
  logos or brand identity.

## Required validation

Before finishing:

- Run `pytest`.
- From `web/`, run `npm run typecheck`, `npm run test:functions`,
  `npm run typecheck:functions`, and `npm run build`.
- Run fixture and synthetic full-scale catalogue generation where relevant.
- Review the final diff for accidental scope expansion.

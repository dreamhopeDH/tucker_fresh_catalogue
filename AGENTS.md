# Project instructions

Before making any code changes, read:

- `docs/TEST_MVP_SPEC.md`
- `docs/reference/catalogue-layout.png`

`docs/TEST_MVP_SPEC.md` is the source of truth for scope,
architecture, acceptance criteria, and explicitly excluded features.

## Development rules

- Implement only the 100-product test MVP.
- Do not add a backend API, database server, admin dashboard,
  PWA, Service Worker, React, Vue, or other unrequested systems.
- Prefer simple functions and modules over generic frameworks.
- Preserve the documented extension points without implementing
  future features.
- Do not place credentials in source code or logs.
- Do not claim external deployment succeeded unless it was
  actually executed successfully.
- Use the reference image as the visual direction for the catalogue,
  but do not copy retailer logos or brand identity.

## Required validation

Before finishing:

- Run `pytest`.
- Run the frontend type check and production build.
- Report the commands run and their results.
- Review the final diff for accidental scope expansion.
# incoming-update/ — the files we ported FROM (2026-07-04)

These are the **updated** copies of the three tool files that we received, plus the
author's porting notes. They are a **reference only** — the app does not import them.

- `amazon_listing_generator.py`, `dashboard.py`, `miles_import.py` — the "new" version
  of each file. Useful for seeing the full source of any adopted function.
- `CHANGES_AND_PORTING_GUIDE.md` — the author's write-up of the 6 feature changes.

**Important:** we did **not** adopt these files wholesale. They contained regressions
(fragile relative paths, a hard-coded `"AltaboltaVoo"` brand, a dropped Sheets-link
guard) and lacked our login/auth + hosting code. See `../README.md` for exactly what
was adopted vs. rejected.

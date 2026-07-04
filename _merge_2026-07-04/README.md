# Merge archive — 2026-07-04

**What this folder is:** a reference + safety-net archive from the day the Amazon
listing tool was updated. It is **not live code** — nothing here is imported or run
by the app. It exists so anyone can see *what changed, why, and how to undo it*.

The three live files it relates to (in the project root) are:

- `amazon_listing_generator.py` — SP-API + listing-shaping engine
- `dashboard.py` — Flask UI
- `miles_import.py` — Miles supplier (Google Drive) harvester

---

## Why these files are here

We received an **updated copy** of the three files (plus a porting guide) and wanted
to bring its new features into our running local copy. The two copies had **diverged
in both directions**, so this was **not** a straight overwrite:

- the **incoming update** had new features **but also several regressions**
  (fragile relative paths, a hard-coded brand, a dropped input-validation guard, and
  it was missing our login/auth + hosting code);
- our **local copy** had infrastructure the update lacked (login gate, dynamic port,
  env-aware config paths).

So we did a **selective, function-level merge**: adopt the genuine new features,
keep our local-only infrastructure, and **reject the update's regressions**. The
result is in the project root and has been compiled, imported, route-registered, and
smoke-tested (the `shape_by_schema` fix, the new routes, and the auth gate all work).

## The two subfolders

| Folder | What it is | Use it to… |
|---|---|---|
| `incoming-update/` | The updated files we ported **from**, plus `CHANGES_AND_PORTING_GUIDE.md` (the author's notes on the 6 feature changes). | See the "new" version of any function; read the feature rationale. |
| `original-local-backup/` | Our local files **exactly as they were before** the merge (pre-2026-07-04). | Restore point — revert the merge if needed. |

> There is **no git** on this machine, so these two folders are the only way to diff
> or roll back. Do not delete them until the merged app has been proven against live
> data (a real harvest + a real submit).

---

## What was adopted vs. rejected (per file)

### `amazon_listing_generator.py`
**Added (new functions):** `shape_by_schema`, `_skus_across_all_tabs`, `_verify_live_status`
**Adopted the update's version of:** `build_api_attributes`, `run_api`, `_shape_simple`,
`main`, `run_miles` — i.e. the composite-field shaping fix (drone/hose/massager),
account-authoritative brand, real post-submit status via `getListingsItem`, and the
Miles cross-tab de-dup / Drive back-fill.
**Rejected the update's regressions (kept our local version):**
- `select_rows` — the update **dropped** the "that's a Google Sheet link, not a product" guard
- `_load_attr_defaults`, `run_brand`, `run_export_unified` — the update used **fragile relative paths**
- `run_export_unified` — the update **hard-coded `"AltaboltaVoo"`** as the brand fallback (the exact "leaked brand" its own guide §3 warns against)
- module level — kept our **env-aware `CONFIG_PATH`** and `import os`

### `miles_import.py`
**Added (new functions):** `list_all_item_folders`, `find_item_folder_id`,
`download_drive_file_bytes`, `bundle_from_drive`. Clean superset — nothing rejected.

### `dashboard.py`
**Added (12 new routes/helpers):** `_ebay_creds`, `ui_preview`, `settings_ebay`,
`_parse_sheet_url`, `settings_dropshipping_sheets`, and the Miles sheet-preference
suite (`_miles_prefs_file`, `_miles_load_prefs`, `_miles_prefs_key`, `_miles_get_pref`,
`_miles_set_pref`, `miles_sheet_pref_get`, `miles_sheet_pref_set`).
**Adopted the update's version of:** `accounts_list`, `accounts_select`, `accounts_save`,
`suggest`, `miles_generate`, `miles_run`, `run` — plus HTML/JS template features
(upload-main-image button, dropshipping-sheets settings, per-account eBay creds,
`runMode(skus)` selection scoping, submit-only-selected-rows, saved Miles sheet pref).
**Kept our local-only systems (the update lacked these — a full copy would have deleted them):**
- **Login/auth**: `_login`, `_logout`, `_require_login`, `_healthz`, `_APP_PASSWORD`, `_LOGIN_HTML`, and the `session/redirect/url_for` imports
- **Hosting/port**: `_pick_port`, `IS_HOSTED`, `HOST`, the `.app_port` write, `app.run(host=HOST…)`
- **Paths**: env-aware `CONFIG_PATH`, absolute `_COGS_FILE` and `save_default` paths
- **UI theme**: kept our **blue** theme (skipped the update's purely-cosmetic purple recolor of the Auto-fix buttons)

---

## How to diff or revert

Compare a merged (live) file against either reference with any diff tool, e.g.:

```powershell
# what the update changed vs. our original, for one function or the whole file
python -c "import difflib,sys; print(''.join(difflib.unified_diff(open(r'original-local-backup\dashboard.py',encoding='utf-8').readlines(), open(r'incoming-update\dashboard.py',encoding='utf-8').readlines())))"
```

**To revert the whole merge**, copy the three files from `original-local-backup/`
back over the project-root copies.

---

*Archived 2026-07-04. The merge was verified: all three files compile and import,
99 dashboard routes register, the new routes respond, the auth gate holds, and the
`shape_by_schema` composite-field fix produces the correct array payload.*

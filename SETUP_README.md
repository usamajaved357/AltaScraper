# Listing Generator Suite — Setup Guide

This tool runs locally on your own Mac (Windows also supported). It opens a dashboard in your
browser at `http://127.0.0.1:5000`. Nothing is shared online — all your data stays on your machine.

## What's included (all features)

The full app ships here — not just the listing generator. Inside the dashboard you get:

- **Listing Generator** — eBay/Amazon URL -> compliant Amazon listing (SP-API, with scraper +
  eBay Browse API fallback), plus the auto-fix loop for schema errors.
- **Listings management** — review, approve, retry, and export listings; flat-file export.
- **Brand mode / Brand Registry** — per-brand profiles, voice/tone control, pricing rules,
  competitor ASINs. An `example-brand` profile is included so you can see the setup.
- **PPC module** — keyword bucketing, campaign builder, harvest engine ("Send to PPC agent").
- **Inventory module** — replenishment calculations and exports.
- **Miles import** — Miles bundle import and blank-template generation.
- **Shopify import** — pull catalog data from Shopify.
- **Image generation** — main/secondary/template product images.
- **Multi-account** — add as many selling accounts as you want, each with its own credentials.

Empty data folders (`media/`, `inventory_out/`, `ppc_out/`, `uploads/`, `brands/`) fill
themselves as you use the app. Only the previous owner's generated content was removed —
every feature that produces that content is intact.

All credentials have been removed from this copy. You must add **your own** before it will run.
Work through the steps below in order.

---

## 1. Install Python 3.11 (macOS)

Option A — installer:
- Download Python **3.11** from https://www.python.org/downloads/macos/ and run the `.pkg`.

Option B — Homebrew (if you have it):
```
brew install python@3.11
```

Verify in **Terminal** (open it from Applications → Utilities → Terminal):
```
python3.11 --version
```
If `python3.11` isn't found, `python3 --version` (3.10+) also works — the app and launcher
fall back to plain `python3` automatically.

> **On Windows instead?** Install Python 3.11 from python.org (tick "Add Python to PATH"),
> and use `py -3.11` wherever this guide says `python3.11`.

## 2. Install the required packages

In **Terminal**, go to this folder and install. Tip: type `cd ` (with a space), then drag the
app folder from Finder onto the Terminal window to paste its path, then press Enter:
```
cd "/path/to/new app for brands shopify to amazon"
python3.11 -m pip install -r requirements.txt
```
If pip complains about permissions, add `--user` to that command.

**One extra step (needed for the web-scraper fallback):** the app uses `crawl4ai`, which drives
a headless browser. On a fresh Mac that browser must be downloaded once:
```
python3.11 -m playwright install chromium
```
If you skip this, listing generation still works when SP-API/eBay data is available, but the
scraper fallback (used when a product isn't found via the APIs) will error out.

## 3. Google service account (for reading/writing your Google Sheets & Drive)

1. Go to https://console.cloud.google.com and create (or pick) a project.
2. Enable **Google Sheets API** and **Google Drive API** for that project.
3. Go to **IAM & Admin → Service Accounts → Create Service Account**.
4. Open the new service account → **Keys → Add Key → Create new key → JSON**.
5. A `.json` file downloads. **Rename it to `service_account.json`** and drop it in this
   folder, replacing the placeholder that's here now.
6. Open that JSON, copy the `client_email` value, and **share every Google Sheet and Drive
   folder you'll use with that email as an Editor** (just like sharing with a person).

## 4. Fill in `config.json`

Open `config.json` in **TextEdit** (right-click the file → Open With → TextEdit) or any code
editor. Every empty `""` must be filled with **your own** value.
Here's where each comes from:

| Field | Where to get it |
|---|---|
| `anthropic_api_key` | https://console.anthropic.com → API Keys (starts with `sk-ant-...`) |
| `openrouter_api_key` | (optional) https://openrouter.ai → Keys. Leave `""` if unused. |
| `google_service_account_json` | Leave as `service_account.json` (the filename from step 3) |
| `google_spreadsheet_id` | The long ID in your output Google Sheet URL between `/d/` and `/edit` |
| `input_spreadsheet_id` | Same, for your input sheet |
| `template1_spreadsheet_id` / `template2_spreadsheet_id` | The flat-file template sheet IDs (copy the provided templates into your own Drive and use those IDs) |
| **SP-API (Amazon)** — `sp_api_client_id`, `sp_api_client_secret`, `sp_api_refresh_token`, `seller_id` | From your **Amazon Seller Central → Develop Apps** (LWA credentials + refresh token). See step 5. |
| `us_spapi/*` | Same as above, for a US account. Leave blank if UK-only. |
| `ebay_app_id` / `ebay_cert_id` | https://developer.ebay.com → your app keyset (Production). Optional — only for the eBay supplement. |
| `accounts[]` | One entry per selling account. Fill each account's `lwa_client_id`, `lwa_client_secret`, `refresh_token`, `seller_id`, and its sheet IDs / tab GIDs. `marketplace_id` values are already filled (they're public constants). |

**Tab GIDs**: the `gid=` number in a Google Sheet tab's URL identifies which tab to read/write.

## 5. Amazon SP-API credentials (the main one)

1. In **Seller Central → Apps & Services → Develop Apps**, create (or open) your app.
2. Copy the **LWA client ID** and **client secret** → these are `sp_api_client_id` /
   `sp_api_client_secret` (or `lwa_client_id` / `lwa_client_secret` inside `accounts[]`).
3. Authorize the app for your seller account and generate a **refresh token** →
   `sp_api_refresh_token`.
4. Your **Seller ID** (a string like `A1XXXXXXXXXX`) → `seller_id`.

Note: fresh Amazon apps often need **production access approval** before some calls work.
Until then the built-in scraper + eBay fallback carry the load.

## 6. Run it (macOS)

Double-click **`START_APP.command`**. A Terminal window opens (keep it open) and your browser
opens the dashboard at `http://127.0.0.1:5000` automatically. To stop the app, press **Ctrl+C**

> **Note on the port:** macOS reserves port 5000 for AirPlay Receiver. If 5000 is busy, the app
> automatically uses the next free port (5001, 5002, …) and the launcher opens that one for you —
> so the address bar may read `:5001` instead of `:5000`. That's expected, nothing is wrong. If you
> prefer to keep 5000, turn off **System Settings → General → AirDrop & Handoff → AirPlay Receiver**.
in that window or just close it.

**First-launch security prompt:** because this file was downloaded, macOS may say it "cannot be
opened because it is from an unidentified developer." To allow it once:
- **Right-click** (or Control-click) `START_APP.command` → **Open** → **Open** in the dialog. After
  the first time, double-click works normally.
- If double-clicking still does nothing, open Terminal in this folder and run:
  `chmod +x START_APP.command` then `./START_APP.command`.

The launcher auto-detects `python3.11`, falling back to `python3`.

> **On Windows?** Double-click `START_APP.bat` instead.

---

## Notes

- The `media/`, `uploads/`, `inventory_out/`, `ppc_out/`, `brands/` folders start empty —
  the app fills them as you use it.
- `miles_fonts/` and the `.xlsm` templates are needed; don't delete them.
- Keep your filled-in `config.json` and `service_account.json` **private** — they hold your
  live keys. Don't commit them anywhere public or re-share this folder once filled.

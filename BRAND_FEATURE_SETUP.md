# Brand-Listing Feature — New Folder Setup Checklist

This adds **brand-mode** listing (Shopify → Amazon, in the brand's voice, claims
gated to docs) to your existing app, without changing the arbitrage path.

---

## 1. Files for the new folder

**Copy from your current working folder (the engine — unchanged):**
- amazon_listing_generator.py
- dashboard.py
- unified_export.py
- template_schema.py
- compliance_rules.json   (regulatory layer — also used by brand mode)
- ip_rules.json           (generic IP layer — also used by brand mode)
- valid_values.json       ← don't forget (385 KB; without it attributes degrade)
- config.json             (edit per §3 below)
- service_account.json    (also powers the Drive claim-doc fetch)
- model_number_counter.json
- requirements.txt
- KITCHEN_…xlsm           ← your UK unified template (export needs it)

**New brand-feature files (from this delivery):**
- shopify_import.py
- brand_profile.py
- brand_listing.py
- dashboard_brand_patch.py
- PATCH_brand_mode.py      (instructions — not imported at runtime)

A `brands/` folder is created automatically on first save.

---

## 2. Wire the patches (5 small edits, all additive)

In **amazon_listing_generator.py** (see PATCH_brand_mode.py for exact text):
1. Add imports: `import shopify_import, brand_profile, brand_listing`
2. Paste the `run_brand(...)` function + `ws_out_global()` helper.
3. Add the `brand` branch to `main()`'s mode dispatch.

In **dashboard.py** (see dashboard_brand_patch.py header for exact text):
4. After `app = Flask(__name__)`, add:
   `import dashboard_brand_patch` and the one `dashboard_brand_patch.register(...)` call.
5. Add the **Brand** pill + `#brandpanel` div + the small `loadBrandPanel()` script.
   (Optional: add the `iBtn(...)` helper + CSS for the per-field provenance "i".)

Nothing in the arbitrage path changes. Old modes (generate/retry/export/api) work as before.

---

## 3. config.json additions

Keep your existing keys. Add:
```json
"shopify_export_path": "products_export_all_products.csv",
"active_brand": "Leech",
"connection": {
  "auth_method": "service_account",
  "service_account_json": "service_account.json",
  "claims_docs_drive_url": ""
}
```
(These can also be set from the dashboard Connections + Brand tabs instead of by hand.)

---

## 4. Google Drive (for claim-support docs)

1. In Google Cloud Console → the `ebay-to-amz-ds-link-automation` project →
   **APIs & Services → Enable APIs** → enable **Google Drive API**.
2. Put the brand's claim docs (PDF/image; PPTX/DOCX must be converted to PDF) in
   a Drive folder.
3. **Share that folder** with the service-account email
   (`ebay-to-amz-...@...iam.gserviceaccount.com`), Viewer.
4. Paste the folder link into the brand's **Claims-docs Drive folder** field.

No docs? Brand mode still runs — it just limits claims to generic
category-standard benefits + facts in the export (stricter gate).

---

## 5. Security (do this before going live)

Every key in the configs shared during development is **burned**. Rotate:
- Anthropic API key (it was also failing on a billing balance — top up too)
- SP-API client secret + refresh token (UK; and US when you add it)
- eBay app/cert IDs
- the Google service-account key (and the OAuth client secret if you keep that file)

---

## 6. USA marketplace (when ready)

- US listings publish via the **API path** (`run_api`) → **no US template needed**.
- Add US SP-API credentials to config and select **US** in the brand profile.
- A US flat-file template is only needed if you choose flat-file export for US
  (not recommended — API is cleaner, especially for client-connected accounts).

---

## 7. Run it

From the dashboard: open **Brand** → fill the profile → **Preview export** →
**Save brand** → **Generate listings for this brand**. Rows land in the same
`Listings v7.0 UK` sheet/review cards. Approve → export or api, exactly as today.

CLI equivalent:
```
py -3.11 amazon_listing_generator.py brand "Leech" "products_export_all_products.csv"
```

---

## What each new field does (quick reference)

| Field | Effect |
|---|---|
| Vendor mode | single_brand vs reseller (multi-vendor store) |
| Voice mode | regenerate (fresh) vs preserve (keep phrasing) |
| Tone/output language | English default; brand's source language offered if non-English |
| Marketplace | UK / US (drives spelling, marketplace ID, language tag) |
| Country of origin | brand-stated; never hardcoded |
| Lead title with brand | brand listings usually lead with brand name |
| SKU prefix | off → P2601B; on → LEECH-P2601B |
| Shopify export path | the products CSV |
| Claims-docs Drive folder | substantiation evidence; claims gate keys off this |
| Competitor ASINs | OPTIONAL enrichment; brand mode runs fine without |
| Forbidden brands | brand-specific IP block (folds into the IP scan) |

Identity (SKU / MPN / model / GTIN) always comes from the export verbatim, blank
if absent — never auto-generated for brands.

# Changes & Porting Guide

Purpose: a complete, self-contained record of the bug fixes and upgrades made to
this **local** copy, written so you can re-apply them to your **GitHub / live**
copy of the app. Changes are described by **file + function + anchor** (not line
numbers), so they port even if the other repo's line numbers differ.

Three source files are touched:
- `amazon_listing_generator.py` (the SP-API + shaping engine)
- `dashboard.py` (the Flask UI)
- `miles_import.py` (Google Drive helper for the Miles supplier flow)

### For the receiving Claude session (how to apply this to the old code)
You have the **old code** and this guide. Two ways to port, best first:
1. **Diff-based (most reliable):** if you were also handed the three *updated* files,
   diff each changed function against the old code and copy the new version in.
   Match by **function name**, not line number.
2. **Guide-based:** follow §1–§3 below. Each new function's **full source** is
   embedded here; each edit says which function/anchor to change. Skip §7 entirely.
After editing each file: `python -m py_compile <file>`, then an AST check that no
functions were accidentally dropped (parse before/after, compare the set of
`FunctionDef` names). If the old code's function names/structure differ, adapt the
anchors — the *logic* is what matters. Status verified working in production
(listings submitted successfully).

## Summary

| # | Change | Files | Status |
|---|---|---|---|
| 1 | Composite-field shaping — fixes drone / foot-massager / garden-hose submits | `amazon_listing_generator.py` | **PORT** |
| 2 | Miles: one-click Harvest→Generate + cross-tab de-dup | `dashboard.py`, `miles_import.py`, `amazon_listing_generator.py` | **PORT** |
| 3 | Brand = the account's own trademark (never a leaked/global brand) | `amazon_listing_generator.py` | **PORT** |
| 4 | "Submit · go live" publishes only the SELECTED rows (not all approved) | `dashboard.py` | **PORT** |
| 5 | Accurate post-submit status — verify real listing state (`getListingsItem`) | `amazon_listing_generator.py` | **PORT** |
| 6 | Upload a clean local main image from the product card | `dashboard.py` | **PORT** |
| — | Offer-on-existing-ASIN experiment (`merchant_suggested_asin` + `LISTING_OFFER_ONLY`) | — | **DO NOT PORT** (reverted — see §7) |

> Verify after each port: `python -m py_compile <file>` and an AST check that no
> functions were dropped. Nothing here changes the "create my OWN listing" model.

---

## 1. Composite-field shaping — drone / foot massager / garden hose

### Symptom
`VALIDATION_PREVIEW` rejected these product types with "The provided value for 'X'
is invalid," and the bulk auto-fix stalled at "IDENTICAL, no progress." The AI gave
the right *fact* (50 ft, has a battery), but the code folded it into the wrong
*shape*.

| Product | Product type | Field |
|---|---|---|
| Drone | `UNMANNED_AERIAL_VEHICLE` | `contains_battery_or_cell` |
| Garden hose (50 ft) | `HARDWARE_TUBING` | `leg` → its `length` axis |
| Foot massager | `MASSAGER` | `cable` → its `length` axis |

### Root cause (the code *assumed* the shape instead of *reading* it)
1. **Numeric leaf key** varies per field: most use `value`, but `leg`/`cable` use
   `decimal_value`.
2. **Array vs object**: for `leg`/`cable`, `length` is itself a `type: array` whose
   *items* carry the leaf key — one level deeper than the old shaper looked.
3. **Enum vs boolean**: `contains_battery_or_cell` is an **enum** (`"Yes"/"No"`) on
   the drone, but the code sent boolean `true` → "select an approved value."

Correct hose payload:
```json
"leg": [{ "marketplace_id": "..", "length": [{ "decimal_value": 50.0, "unit": "feet" }] }]
```
Old (wrong) payload: `"leg": { "length": { "value": 50.0, "unit": "feet" } }`
(object instead of array; `value` instead of `decimal_value`).

### The fix — `shape_by_schema` (read the schema at every level)
Add this top-level function to `amazon_listing_generator.py`:

```python
def shape_by_schema(schema, raw, mid, lang="en_GB"):
    t = schema.get("type")
    if t == "array":
        shaped = shape_by_schema(schema.get("items", {}) or {}, raw, mid, lang)
        return [shaped] if shaped is not None else []
    if t == "object":
        props = schema.get("properties", {}) or {}
        obj = {}
        if "marketplace_id" in props: obj["marketplace_id"] = mid
        if "language_tag" in props:   obj["language_tag"]   = lang
        num_key = "decimal_value" if "decimal_value" in props else ("value" if "value" in props else None)
        num = unit = None
        if isinstance(raw, str):
            p = raw.split()
            if p:
                try: num = float(p[0]); unit = " ".join(p[1:]) or None
                except ValueError: pass
        elif isinstance(raw, dict):
            num = raw.get("decimal_value", raw.get("value")); unit = raw.get("unit")
        if num_key and num not in (None, ""):
            try: obj[num_key] = float(str(num))
            except (ValueError, TypeError): obj[num_key] = num
        if "unit" in props and unit not in (None, ""):
            uen = props["unit"].get("enum")
            obj["unit"] = (next((e for e in uen if str(e).lower() == str(unit).strip().lower()), unit)
                           if uen else unit)
        for pk, pv in props.items():
            if pk in ("marketplace_id", "language_tag", "unit", num_key): continue
            if isinstance(pv, dict) and pv.get("type") in ("array", "object"):
                sub = raw.get(pk) if isinstance(raw, dict) and pk in raw else raw
                s = shape_by_schema(pv, sub, mid, lang)
                if s not in (None, [], {}): obj[pk] = s
        return obj
    return raw.get("decimal_value", raw.get("value")) if isinstance(raw, dict) else raw
```

In `build_api_attributes`, route any composite dimension field (its item props
contain axis sub-fields `length`/`width`/`height`/`depth`) through
`shape_by_schema(props[fname], {axis: "NUM UNIT"}, mid)` instead of the old
`_shape_axes`. Also make the axis reader accept `decimal_value` as well as `value`
(in `_from_user_composite` / `_shape_axes`): read `av.get("decimal_value", av.get("value"))`.

For the drone battery fields, add a schema-driven net inside `build_api_attributes`
(independent of keyword detection): if the product type declares/requires
`contains_battery_or_cell` / `number_of_lithium_ion_cells`, fill safe defaults, and
read the field's schema to send the enum's "Yes" via `_cbc_value` rather than boolean
`true`. Full source of the block (`required`, `props`, `A`, `mid` are locals already
in `build_api_attributes`):
```python
def _schema_wants(_f):
    return (_f in required) or isinstance(props.get(_f), dict)
def _cbc_value(_prop):
    # contains_battery_or_cell is an ENUM ("Yes"/"No") for some product types and a
    # BOOLEAN for others. Sending JSON `true` to an enum field fails. Read the schema.
    _enum = []
    if isinstance(_prop, dict):
        _it  = _prop.get("items", {}) if isinstance(_prop.get("items"), dict) else {}
        _itp = _it.get("properties", {}) if isinstance(_it, dict) else {}
        _vpp = _itp.get("value", {}) if isinstance(_itp, dict) else {}
        _enum = [str(x) for x in (_vpp.get("enum") or _itp.get("enum")
                                  or _it.get("enum") or _prop.get("enum") or [])]
    if _enum:
        for _e in _enum:
            if str(_e).strip().lower() in ("yes", "true", "1"):
                return _e
        return _enum[0]
    return True
if _schema_wants("contains_battery_or_cell") and "contains_battery_or_cell" not in A:
    A["contains_battery_or_cell"] = [{"value": _cbc_value(props.get("contains_battery_or_cell", {})),
                                      "marketplace_id": mid}]
if _schema_wants("number_of_lithium_ion_cells") and "number_of_lithium_ion_cells" not in A:
    A["number_of_lithium_ion_cells"] = [{"value": 1, "marketplace_id": mid}]
```

### Verify
`api preview` a `HARDWARE_TUBING` (`leg`) SKU and a `MASSAGER` (`cable`) SKU — the
`length` axis must serialise as an **array** of `{decimal_value, unit}` and pass.

---

## 2. Miles supplier flow — one-click Harvest→Generate + cross-tab de-dup

### What it does now
Hitting **Harvest** in the Supplier Import panel now also **generates listing
copies for every item folder in Drive that isn't already in the output sheet** —
and it de-dupes across **all tabs** of the sheet, so re-running never duplicates a
listing that lives on a different tab. The uploaded Excel is **harvest-only**; the
generation set comes from Drive.

### 2a. `miles_import.py` — enumerate all Drive item folders
Add this function (full source):
```python
def list_all_item_folders(drive_service, master_id: str = MASTER_FOLDER_ID,
                          with_files_only: bool = False, log=None) -> list:
    """Return the item-number NAMES of every folder directly under the master
    Drive folder -- i.e. every item that has EVER been harvested to Drive."""
    def _log(m):
        if log:
            try: log(m)
            except Exception: pass
    if not drive_service:
        _log("    [drive-scan] no drive service -> 0 folders")
        return []
    names, page_token = [], None
    try:
        while True:
            q = (f"'{master_id}' in parents and trashed = false "
                 f"and mimeType = 'application/vnd.google-apps.folder'")
            res = drive_service.files().list(
                q=q, fields="nextPageToken, files(id,name)", pageSize=1000,
                supportsAllDrives=True, includeItemsFromAllDrives=True,
                pageToken=page_token).execute()
            for f in res.get("files", []):
                nm = (f.get("name") or "").strip()
                if not nm:
                    continue
                if with_files_only:
                    q2 = (f"'{f['id']}' in parents and trashed = false "
                          f"and mimeType != 'application/vnd.google-apps.folder'")
                    r2 = drive_service.files().list(
                        q=q2, fields="files(id)", pageSize=1,
                        supportsAllDrives=True,
                        includeItemsFromAllDrives=True).execute()
                    if not r2.get("files"):
                        continue
                names.append(nm)
            page_token = res.get("nextPageToken")
            if not page_token:
                break
    except Exception as e:
        _log(f"    [drive-scan] list failed: {type(e).__name__}: {str(e)[:120]}")
    seen, out = set(), []          # de-dup, preserve order
    for n in names:
        if n not in seen:
            seen.add(n); out.append(n)
    return out
```
(`MASTER_FOLDER_ID` is the module's existing constant for the Drive parent folder.)

### 2b. `amazon_listing_generator.py` — de-dupe SKUs across ALL tabs
Add this function (full source; `_safe_records` is the module's existing
records-reader):
```python
def _skus_across_all_tabs(ws_out) -> set:
    """Union of the SKU column across EVERY worksheet in ws_out's spreadsheet.
    Robust to a malformed tab (duplicate/blank headers) via a raw-grid fallback."""
    out = set()
    try:
        worksheets = ws_out.spreadsheet.worksheets()
    except Exception as e:
        console.print(f"  [yellow]Cross-tab SKU scan unavailable: {str(e)[:80]}[/yellow]")
        return out
    _itempat = re.compile(r"^[A-Za-z]{2,4}\d{4,}$")
    for ws in worksheets:
        try:
            for r in _safe_records(ws):
                v = str(r.get("SKU", "") or "").strip()
                if v:
                    out.add(v)
            continue
        except Exception:
            pass
        try:
            vals = ws.get_all_values()
        except Exception:
            continue
        if not vals:
            continue
        hdr = [str(c).strip().lower() for c in vals[0]]
        if "sku" in hdr:
            ci = hdr.index("sku")
            for row in vals[1:]:
                if ci < len(row) and str(row[ci]).strip():
                    out.add(str(row[ci]).strip())
        else:
            for row in vals:
                for c in row:
                    if _itempat.match(str(c).strip()):
                        out.add(str(c).strip())
    return out
```
Then in `run_miles`, right after `taken_skus, _ = load_existing_skus_and_asins(ws_out)`:
```python
try:
    _cross = _skus_across_all_tabs(ws_out)
    taken_skus |= _cross          # skip an item if its SKU exists on ANY tab
    console.print(f"  Cross-tab dedup: {len(_cross)} SKU(s) already exist across all tabs")
except Exception as _e:
    console.print(f"  Cross-tab SKU scan failed: {str(_e)[:80]}")
```
(This works because Miles SKU == item number, and `process_brand_row` already skips
`if sku in taken_skus and not profile.get("replace_existing")`.)

### 2c. `dashboard.py` — chain generation after harvest, from Drive
- Capture `_acc = _active_account()` and `_pref = _miles_get_pref()` in **request
  context** at the top of `miles_run()` (the SSE generator can't call them).
- Inside the harvest stream, define a nested generator `_generate_missing()` that:
  builds a Drive service, calls `list_all_item_folders`, writes the full list to
  `miles_items.json`, then spawns `python amazon_listing_generator.py miles
  --account-id … --marketplace … --sheet <ID> --tab <tab>` and streams its output.
  **Extract the bare spreadsheet ID from the saved pref** (it may be a full URL):
  `re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", raw)`.
- Call `yield from _generate_missing()` at BOTH exit points of `/miles/run` — the
  normal completion *and* the "nothing new to harvest" branch — so Generate runs
  even when nothing new was harvested.
- Make `/miles/generate` ALSO scan Drive (via `list_all_item_folders`) and write the
  full list to `miles_items.json`, instead of using the uploaded list. (This is what
  makes "the Excel is harvest-only" true, and stops a stale `miles_items.json` from
  scoping generation to the wrong items.)
- In the `except GeneratorExit` / `except Exception` handlers of `/miles/run`,
  terminate `_running["proc"]` (the chained generation subprocess) so browser
  disconnect / Stop kills it.

### Verify
Upload item numbers → Harvest → it harvests, then logs `[items] N item folder(s) in
Drive … existing rows on ANY tab are skipped`, then `[N/…]` writes only the missing
listings. Re-running never duplicates.

---

## 3. Brand = the account's own trademark (never a leaked/global brand)

### Symptom / cause
Listings went to Amazon under the wrong brand. Two failure modes:
- One account's brand **leaked onto another**: the global `config["brand_name"]`
  held `"AltaboltaVoo"` (which is actually the **Jack Reacherd** account's real
  trademark), and any account whose own `brands` list was empty (e.g. Selvora) fell
  back to it — so Selvora listings were built under Jack's brand.
- Worse, in a gated category (`LIGHT_FIXTURE`) the brand was sometimes a **garbage
  value (the product title)**, which Amazon rejects: *"The brand name you have
  entered has not been approved by Amazon."*

> IMPORTANT: `"AltaboltaVoo"` is a **real brand**, not a placeholder. An earlier
> attempt to blocklist it (`_PLACEHOLDER_BRANDS` / `_is_placeholder_brand`) was
> **wrong and was removed**. Do not port any placeholder-blocklist. The authority
> is the **account's `brands` list**, full stop.

### The data
Each account carries its own trademark(s) in its `brands` list in `config.json`
under `accounts`, e.g. `jack_uk → ["AltaboltaVoo"]`, `selvora_limited → ["Selvora"]`,
`miles_lubricants → ["Miles Lubricants"]`, `sheelady_us → ["Shee'lady"]`. Set every
account you list from. (In the app, `accounts.save_account` persists these.)

### The fix — `amazon_listing_generator.py`
1. **Expose the account's brands to the run.** In `main()`, right where the account
   is resolved (`_acc_brand` from `_acc_obj.get("brands")`), publish BOTH to config:
   ```python
   config["_account_brand"]  = _acc_brand   # primary (may be "")
   config["_account_brands"] = [str(x).strip() for x in (_abr or []) if str(x).strip()]
   ```
2. **Payload builder** — in `build_api_attributes`, replace the old
   `brand = g("Brand") or config.get("brand_name","")` with account-authoritative
   resolution (trust the column only if it's one of THIS account's brands, so
   multi-brand accounts still work; otherwise use the account's primary; NEVER the
   global default):
   ```python
   brand = g("Brand").strip()
   _acct_brands = [str(x).strip() for x in (config.get("_account_brands") or []) if str(x).strip()]
   if _acct_brands:
       if brand not in _acct_brands:
           brand = _acct_brands[0]                 # stale/leaked column -> account trademark
   elif config.get("_account_brand") is not None:
       brand = ""                                  # account resolved but NO trademark -> blank
   else:
       brand = brand or config.get("brand_name", "")   # legacy / no-account fallback only
   if has("brand") and brand:
       put("brand", _shape_simple(props["brand"], brand, mid))
   ```
3. **Submit guard** — in `run_api`, inside the per-row loop (after the SKU/Product-Type
   check), block publishing when the account has no trademark, with an actionable
   message. Preview is left alone.
   ```python
   if submit:
       _rb = str(row.get("Brand","") or "").strip()
       _acct_brands = [str(x).strip() for x in (config.get("_account_brands") or []) if str(x).strip()]
       if _acct_brands:
           if _rb not in _acct_brands:
               _rb = _acct_brands[0]
       elif config.get("_account_brand") is not None:
           _rb = ""
       if not _rb:
           err += 1
           queue(i, status_col, "API_ERROR")
           queue(i, notes_col, "[E] brand -- no trademark set for this account. Add your "
                               "brand/trademark in account Settings, or in the product card on the "
                               "Listings page, then submit.")
           console.print(f"  row {i} {sku}: SUBMIT BLOCKED -- no trademark set for this account")
           continue
   ```

### Why this also fixes the "brand not approved" error
Sending the account's **real, consistent** trademark (instead of the product title)
means Amazon evaluates *your* brand. If that brand is recognised/approved, it
passes; verified live — two `LIGHT_FIXTURE` rows that failed with "brand not
approved" went to `ok: 2 errors: 0 API_READY` once the brand resolved to the
account's `AltaboltaVoo`. (If a brand is genuinely new in a gated category, Amazon
may still ask you to request approval via the URL in its error — that's an Amazon
step, not code.)

### Verify
With `jack_uk` active, a row whose Brand column is `AltaboltaVoo` (its own brand)
keeps it; a Selvora row whose column still says `AltaboltaVoo` resolves to `Selvora`;
an account with empty `brands` blocks submit with the "add trademark" note.

---

## 4. "Submit · go live" publishes only the SELECTED rows — `dashboard.py`

### Symptom
The bulk **Submit · go live** button published **every** `APPROVED`/`API_READY` row
in the tab — ignoring the user's selection — so rows left `API_READY` from earlier
previews got swept up (8 submitted when the user approved 4).

### Fix
The backend `/run/api_submit` route **already** honours a `?skus=` filter (it passes
`--skus` to the generator). It just wasn't being sent. Two JS edits:

1. `runMode(mode, skus)` — accept an optional SKU list and append it for the
   preview/submit modes:
   ```javascript
   if((mode==="api"||mode==="api_submit") && skus && skus.length){
     url += (url.indexOf("?")>=0?"&":"?")+"skus="+encodeURIComponent(skus.join(","));
   }
   ```
2. `submitLive()` — pass the current selection (`selectedSkus()`, the ticked rows)
   and reflect it in the confirm dialog:
   ```javascript
   var _sel2 = selectedSkus();
   if(_sel2.length) runMode('api_submit', _sel2);
   else runMode('api_submit');   // nothing selected -> all approved (server default)
   ```
Already-live/submitted rows are skipped automatically (the submit eligibility set is
`{APPROVED, API_READY}`, so `LIVE`/`SUBMITTED` never re-publish).

---

## 5. Accurate post-submit status — `amazon_listing_generator.py`

### Symptom
The submit log said `LIVE` for rows Amazon later **rejected** (e.g. main-image
compliance), and said `errors` for rows that were actually **live**. Cause: the code
set status from the **submit response** (`putListingsItem` returns "accepted"), but
Amazon processes the listing **asynchronously** — "accepted" ≠ "published."

### Fix
Add a verifier that reads the REAL state via `getListingsItem`:
```python
def _verify_live_status(li, seller_id, sku, mid, locale="en_GB"):
    """'Accepted' != 'published'. Query the real listing state so a row is LIVE only
    when Amazon shows it BUYABLE/DISCOVERABLE. Returns (status_list, error_issues);
    (None, None) if the check itself failed."""
    import time as _t
    for _attempt in range(2):
        try:
            _t.sleep(4)
            resp = li.get_listings_item(seller_id, sku, marketplaceIds=[mid],
                                        issueLocale=locale,
                                        includedData=["summaries", "issues"])
            p = resp.payload if hasattr(resp, "payload") else (resp or {})
            summaries = (p or {}).get("summaries", []) or []
            status = summaries[0].get("status", []) if summaries else []
            issues = (p or {}).get("issues", []) or []
            errs = [x for x in issues if str(x.get("severity", "")).upper() == "ERROR"]
            return status, errs
        except Exception:
            continue
    return None, None
```
Then in `run_api`, for **submit only**, replace the "mark LIVE if no submit-time
errors" branch with status set from `_verify_live_status`:
- `BUYABLE`/`DISCOVERABLE` in the real status → **`LIVE`** (if there are image/other
  issues, keep it LIVE but note them — the seller fixes images later).
- real ERROR issues, not buyable → **`API_ERROR`** ("accepted but rejected in
  processing").
- couldn't verify → fall back to the submit-time verdict, flagged unverified.
- else → **`SUBMITTED`** (accepted, pending Amazon processing).
Preview mode is unchanged (submit-time validation IS the answer there).

---

## 6. Upload a clean local main image from the product card — `dashboard.py`

### Why
Source/competitor images often carry text/logo/watermark, which Amazon blocks on the
**main image** (listing won't go live). The seller needs to drop in their own clean
image.

### Fix (reuses existing routes — no new backend)
- `/media/upload` with `kind:"main"` already saves the file **and auto-pushes it to
  the account's Drive**, returning a public `drive_direct_url` Amazon can fetch.
- `/edit` (`target:"attr"`) writes a value onto the row's `Attributes JSON`.
Add a card button + a JS function that chains them:
```javascript
function uploadMainImage(sku, inp){
  const f = inp && inp.files && inp.files[0];
  if(!f || !/^image\//.test(f.type||"")){ if(inp) inp.value=""; return; }
  const rd = new FileReader();
  rd.onload = async () => {
    const up = await (await fetch("/media/upload",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({sku, data:rd.result, name:f.name, kind:"main"})})).json();
    const pub = up && up.ok ? (up.drive_direct_url||"") : "";
    if(!pub){ toast("no public URL — set the account's Drive folder"); return; }
    const sv = await (await fetch("/edit",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({sku, target:"attr", key:"main_product_image_locator", value:pub})})).json();
    if(sv && sv.ok){ toast("Main image set ✓"); loadRows(); }
    inp.value="";
  };
  rd.readAsDataURL(f);
}
```
Card button (in the per-listing action row):
```html
<label class="pushimg" style="cursor:pointer"><i class="ti ti-photo-up"></i> Upload main image<input type="file" accept="image/*" style="display:none" onchange="uploadMainImage('${esc(r.sku)}',this)"></label>
```
**Requires:** the account must have a Drive folder configured (`drive_folder_url`),
or there's no public URL to give Amazon. `build_api_attributes` already sends
`main_product_image_locator` only when it's a public http(s) URL.

---

## 7. Explored and REVERTED — DO NOT PORT

While debugging a dropship SKU that failed on its product identifier, an approach
was tried that made the tool attach the listing as an **offer on the competitor's
existing ASIN** (`merchant_suggested_asin` + `requirements: "LISTING_OFFER_ONLY"`,
dropping brand/identifier). **This is the wrong model** for this business (which
creates its OWN listings under its OWN brand) and was fully reverted. Do **not**
port it. If you see any of these in a codebase, they belong to that reverted
experiment:
- `merchant_suggested_asin` being *set* in `build_api_attributes` (it's fine in the
  `_keep_unknown` keep-lists — that's original).
- `requirements` ever being `"LISTING_OFFER_ONLY"` (must always be `"LISTING"`).
- an `_issue_blocks` function / any relabelling of `[E]`→`[i]` issues.

### The real lesson from that episode (worth knowing, not code)
The dropship SKU's true blocker was **the barcode**: the EAN in the input sheet
(e.g. `4435346455430`) is checksum-valid but **not GS1-registered**, so Amazon
rejects it for new-ASIN creation ("invalid `standard_product_id`"). The tool builds
the correct own-listing payload; the fix is valid product identity — real GS1
barcodes, or a GTIN exemption via Brand Registry (needs a trademark). No code change
solves an unregistered barcode.

---

## Porting checklist

1. `amazon_listing_generator.py`: add `shape_by_schema` (+ `_cbc_value` net) and route
   composite dims through it (§1); add `_skus_across_all_tabs` + run_miles union (§2b);
   publish `config["_account_brand"]`/`["_account_brands"]` in `main()` and make
   `build_api_attributes` + the `run_api` submit-guard resolve brand from the account's
   `brands` (§3). Do NOT add any placeholder blocklist.
   Also add `_verify_live_status` and make `run_api`'s **submit** branch set status
   from the real `getListingsItem` state (§5).
2. `miles_import.py`: add `list_all_item_folders` (§2a).
3. `dashboard.py`: wire `_generate_missing` into `/miles/run` + Drive scan in
   `/miles/generate` + subprocess kill on disconnect (§2c); make `runMode` accept a
   `skus` arg and `submitLive` pass `selectedSkus()` (§4); add the `uploadMainImage`
   JS + the "Upload main image" card button (§6).
4. Do **not** port anything from §7 (the reverted offer-on-ASIN experiment).
5. After each file: `python -m py_compile <file>` + AST "no functions dropped" check;
   for `dashboard.py` JS, extract the changed functions and `node --check`.

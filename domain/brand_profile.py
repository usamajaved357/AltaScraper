"""
brand_profile.py  --  Brand profile + connections data layer for the
                      brand-listing feature of amazon_listing_generator.py.

WHAT THIS MODULE OWNS
---------------------
1. CONNECTIONS  : how the app reaches Google Drive to pull claim-support docs.
                  Defaults to the app owner's existing service_account.json (the
                  same file the main app already uses for Sheets). OAuth is
                  offered as a selectable method for the future client phase but
                  is stubbed until per-client onboarding is built.

2. BRAND PROFILE: per-brand settings that drive generation --
                  voice mode, claims-docs Drive folder, competitor-ASIN pool,
                  marketplace, tone/output language, vendor mode (single vs
                  reseller). Stored as brands/<slug>/profile.json. The dashboard
                  Connections + Brand tabs read/write these; you never hand-edit.

3. CLAIM DOCS   : list + download the brand's substantiation files (PDF/image
                  fetched as base64 for Claude; PPTX/DOCX flagged, not silently
                  dropped) from the Drive master folder. This is what powers the
                  claims gate: Claude may only state a claim it can tie to one of
                  these documents.

DESIGN NOTES
------------
* No competitor required. A brand profile holds an OPTIONAL competitor-ASIN pool;
  generation runs with or without it.
* One config.json stays the source of truth for owner-level secrets. This module
  reads connection defaults from it and stores per-brand settings under brands/.
* Reuses the exact Drive-fetch approach proven in the Miles script
  (list_files_in_folder + download_file_as_base64).
"""

import base64
import io
import json
import re
from pathlib import Path


# --- Anthropic-readable document types ---------------------------------------
# Claude can ingest PDFs and images directly. Office formats must be converted to
# PDF first (we do NOT silently skip them -- we surface them as a warning so a
# .pptx claim sheet never disappears unnoticed).
PDF_MIMES   = ("application/pdf",)
IMAGE_MIMES = ("image/jpeg", "image/png", "image/gif", "image/webp")
OFFICE_MIMES = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # pptx
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",     # docx
    "application/vnd.ms-powerpoint", "application/msword",
    "application/vnd.google-apps.presentation", "application/vnd.google-apps.document",
)

MAX_DOC_BYTES = 30_000_000   # Anthropic per-request doc ceiling guard


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    return s or "brand"


def _extract_drive_folder_id(url_or_id: str) -> str:
    """Accept a full Drive folder URL or a bare folder ID."""
    if not url_or_id:
        return ""
    s = url_or_id.strip()
    m = re.search(r"/folders/([A-Za-z0-9_-]{10,})", s)
    if m:
        return m.group(1)
    m = re.search(r"[?&]id=([A-Za-z0-9_-]{10,})", s)
    if m:
        return m.group(1)
    # bare id
    if re.fullmatch(r"[A-Za-z0-9_-]{10,}", s):
        return s
    return ""


# =============================================================================
# CONNECTIONS  (Drive auth -- service account default, OAuth stubbed)
# =============================================================================

DEFAULT_CONNECTION = {
    "auth_method":        "service_account",       # "service_account" | "oauth"
    "service_account_json": "service_account.json", # owner default (existing file)
    "oauth_credentials_json": "oauth_credentials.json",
    "oauth_token_pickle":   "token.pickle",
    "claims_docs_drive_url": "",                    # master folder of claim docs
    "label":              "Owner (default)",
}

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def load_connection(config: dict) -> dict:
    """Resolve the active Drive connection. Falls back to the owner's existing
    service account so the app works today with zero new setup."""
    conn = dict(DEFAULT_CONNECTION)
    saved = (config or {}).get("connection") or {}
    conn.update({k: v for k, v in saved.items() if v not in (None, "")})
    # inherit the main app's service account path if not separately set
    if not saved.get("service_account_json") and config.get("google_service_account_json"):
        conn["service_account_json"] = config["google_service_account_json"]
    return conn


def build_drive_service(conn: dict, base_dir: Path):
    """Return an authenticated Drive v3 service, or (None, reason).

    service_account : headless, uses the owner's JSON. WORKS TODAY.
                      Requires (a) Drive API enabled on the GCP project and
                      (b) the claim-docs folder shared with the service-account
                      email.
    oauth           : interactive browser login (Miles-style). STUBBED for the
                      client-onboarding phase -- returns a clear not-yet message
                      rather than pretending to work.
    """
    method = conn.get("auth_method", "service_account")

    if method == "oauth":
        return None, ("OAuth is reserved for the client-onboarding phase and is "
                      "not active yet. Use the service-account method (default).")

    # ---- service account ----
    try:
        from google.oauth2 import service_account as _sa
        from googleapiclient.discovery import build as _build
    except Exception as e:
        return None, (f"Google API libraries missing ({e}). "
                      f"pip install google-api-python-client google-auth")

    sa_path = Path(conn.get("service_account_json", "service_account.json"))
    if not sa_path.is_absolute():
        sa_path = base_dir / sa_path
    if not sa_path.exists():
        return None, f"Service account file not found: {sa_path}"

    try:
        creds = _sa.Credentials.from_service_account_file(str(sa_path), scopes=DRIVE_SCOPES)
        service = _build("drive", "v3", credentials=creds, cache_discovery=False)
        return service, None
    except Exception as e:
        return None, f"Drive auth failed: {type(e).__name__}: {str(e)[:160]}"


# =============================================================================
# CLAIM DOCS  (list + download as base64 -- powers the claims gate)
# =============================================================================

def list_claim_docs(drive_service, folder_id: str) -> dict:
    """List everything in the claim-docs master folder, sorted into readable
    (pdf/image) vs needs-conversion (office) vs other. Recurses one level into
    subfolders so a per-product subfolder layout also works."""
    out = {"readable": [], "office": [], "other": [], "errors": []}
    if not drive_service or not folder_id:
        out["errors"].append("No Drive service or folder id.")
        return out

    def _list(fid):
        try:
            resp = drive_service.files().list(
                q=f"'{fid}' in parents and trashed=false",
                fields="files(id, name, mimeType)", pageSize=200,
            ).execute()
            return resp.get("files", [])
        except Exception as e:
            out["errors"].append(f"list failed: {str(e)[:120]}")
            return []

    for f in _list(folder_id):
        mt = f.get("mimeType", "")
        if mt == "application/vnd.google-apps.folder":
            for sub in _list(f["id"]):          # one level deep
                _sort_doc(sub, out)
        else:
            _sort_doc(f, out)
    return out


def _sort_doc(f: dict, out: dict):
    mt = f.get("mimeType", "")
    if mt in PDF_MIMES or mt in IMAGE_MIMES:
        out["readable"].append(f)
    elif mt in OFFICE_MIMES:
        out["office"].append(f)
    else:
        out["other"].append(f)


def download_doc_base64(drive_service, file_id: str):
    """Download a Drive file as base64 (Miles-proven path)."""
    try:
        from googleapiclient.http import MediaIoBaseDownload
    except Exception:
        return None
    try:
        req = drive_service.files().get_media(fileId=file_id)
        buf = io.BytesIO()
        dl = MediaIoBaseDownload(buf, req)
        done = False
        while not done:
            _status, done = dl.next_chunk()
        buf.seek(0)
        data = buf.read()
        if len(data) > MAX_DOC_BYTES:
            return None
        return base64.b64encode(data).decode("utf-8")
    except Exception:
        return None


def fetch_claim_documents(config: dict, profile: dict, base_dir: Path) -> dict:
    """High-level: resolve connection -> list -> download readable docs as
    base64, ready to attach to a Claude message. Returns a structured result the
    generator and the dashboard can both use.

    Returns:
      {
        "docs":   [{"name", "media_type", "data"(b64)}, ...],   # ready for Claude
        "office_skipped": [name, ...],   # need PDF conversion -- surfaced, not hidden
        "count":  int,
        "warnings": [str, ...],
        "ok": bool,
      }
    """
    result = {"docs": [], "office_skipped": [], "count": 0, "warnings": [], "ok": False}

    drive_url = (profile.get("claims_docs_drive_url")
                 or load_connection(config).get("claims_docs_drive_url", ""))
    folder_id = _extract_drive_folder_id(drive_url)
    if not folder_id:
        result["warnings"].append("No claims-docs Drive folder set for this brand. "
                                   "Claims will be limited to product-stated facts only.")
        result["ok"] = True   # not an error -- just no docs => stricter gate
        return result

    conn = load_connection(config)
    service, reason = build_drive_service(conn, base_dir)
    if not service:
        result["warnings"].append(f"Drive not reachable: {reason}")
        return result

    listing = list_claim_docs(service, folder_id)
    result["warnings"].extend(listing.get("errors", []))
    for f in listing.get("office", []):
        result["office_skipped"].append(f["name"])
    if listing.get("office"):
        result["warnings"].append(
            f"{len(listing['office'])} Office file(s) (PPTX/DOCX) found but not "
            f"machine-readable as-is -- convert to PDF to include them as claim "
            f"evidence: " + ", ".join(d["name"] for d in listing["office"][:5]))

    for f in listing.get("readable", []):
        b64 = download_doc_base64(service, f["id"])
        if not b64:
            result["warnings"].append(f"Could not download: {f['name']}")
            continue
        mt = f["mimeType"]
        media_type = "application/pdf" if mt in PDF_MIMES else mt
        result["docs"].append({"name": f["name"], "media_type": media_type, "data": b64})

    result["count"] = len(result["docs"])
    result["ok"] = True
    return result


# =============================================================================
# BRAND PROFILE  (per-brand settings; stored brands/<slug>/profile.json)
# =============================================================================

DEFAULT_PROFILE = {
    "brand_name":            "",
    "vendor_mode":           "single_brand",   # "single_brand" | "reseller"
    "voice_mode":            "regenerate",      # "preserve" | "regenerate"
    "tone_language":         "en",              # output/tone language code; en default
    "source_language":       "en",              # auto-detected from the catalogue
    "marketplace":           "UK",              # "UK" | "US"
    "country_of_origin":     "",                # brand-stated; NOT hardcoded CN
    "lead_with_brand":       True,              # brand listings usually lead with brand
    "claims_docs_drive_url": "",                # per-brand override of the docs folder
    "competitor_asins":      [],                # OPTIONAL enrichment pool
    "forbidden_brands":      [],                # brand-specific IP (Miles-style)
    "safe_alternatives":     "",
    "voice_notes":           "",                # free-text brand voice/positioning
    "source_currency":       "",                # e.g. SEK (label)
    "fx_rate":               "",                # source->target multiplier
    "price_markup":          "",                # extra multiplier (1.0 = none)
    "price_round_99":        False,             # round to .99
    "price_fixed":           "",                # exact override price
    "replace_existing":      False,             # re-generate SKUs already in sheet
    "main_image_reference":  "",                # brand's template/reference image URL for AI main-image gen
    # --- per-brand routing (so a US brand writes to its OWN US sheet) ---------
    "output_spreadsheet_id": "",                # brand's output Google Sheet ID
    "output_tab":            "",                # tab name in that sheet
    "input_spreadsheet_id":  "",                # optional brand-specific input sheet
    "claims_docs_drive_url_override": "",       # (alias kept for clarity)
}


def brands_dir(config: dict, base_dir: Path) -> Path:
    d = config.get("brands_dir", "brands")
    p = Path(d)
    if not p.is_absolute():
        p = base_dir / p
    p.mkdir(parents=True, exist_ok=True)
    return p


def list_brands(config: dict, base_dir: Path) -> list:
    bdir = brands_dir(config, base_dir)
    out = []
    for sub in sorted(bdir.iterdir()):
        pf = sub / "profile.json"
        if pf.exists():
            try:
                out.append(json.loads(pf.read_text(encoding="utf-8")))
            except Exception:
                continue
    return out


def load_profile(config: dict, base_dir: Path, brand_name: str) -> dict:
    bdir = brands_dir(config, base_dir)
    pf = bdir / _slug(brand_name) / "profile.json"
    prof = dict(DEFAULT_PROFILE)
    if pf.exists():
        try:
            prof.update(json.loads(pf.read_text(encoding="utf-8")))
        except Exception:
            pass
    if not prof.get("brand_name"):
        prof["brand_name"] = brand_name
    return prof


def save_profile(config: dict, base_dir: Path, profile: dict) -> str:
    bdir = brands_dir(config, base_dir)
    slug = _slug(profile.get("brand_name", "brand"))
    folder = bdir / slug
    folder.mkdir(parents=True, exist_ok=True)
    pf = folder / "profile.json"
    merged = dict(DEFAULT_PROFILE)
    merged.update(profile)
    pf.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(pf)


def tone_dropdown_options(source_lang_code: str) -> list:
    """Build the dashboard tone dropdown per the agreed rule: English always
    first and pre-selected; if the brand's source copy is non-English, add that
    language as a second option."""
    from_names = {
        "en": "English", "sv": "Swedish", "pt": "Portuguese", "es": "Spanish",
        "de": "German", "fr": "French", "it": "Italian", "nl": "Dutch",
    }
    opts = [{"code": "en", "label": "English", "default": True}]
    if source_lang_code and source_lang_code != "en":
        opts.append({"code": source_lang_code,
                     "label": from_names.get(source_lang_code, source_lang_code),
                     "default": False})
    return opts


if __name__ == "__main__":
    # Smoke test (no network): profile round-trip + dropdown + id parsing.
    here = Path(__file__).parent
    cfg = {"google_service_account_json": "service_account.json", "brands_dir": "brands"}
    p = dict(DEFAULT_PROFILE, brand_name="Leech Eyewear", vendor_mode="reseller",
             source_language="sv", claims_docs_drive_url="")
    path = save_profile(cfg, here, p)
    print("saved:", path)
    back = load_profile(cfg, here, "Leech Eyewear")
    print("loaded brand:", back["brand_name"], "| vendor_mode:", back["vendor_mode"])
    print("tone options:", tone_dropdown_options(back["source_language"]))
    print("folder id from url:",
          _extract_drive_folder_id("https://drive.google.com/drive/folders/1AbCdEfGh1234567890_xy?usp=sharing"))

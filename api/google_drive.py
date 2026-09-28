"""api/google_drive.py -- Google Drive helpers that need no config: folder ids, sub-folders, direct links, sharing.

Moved word for word out of dashboard.py (Milestone 4, owner-approved 28 Sep 2026).
dashboard.py still imports every name below, so dashboard.<name> and every
route that is handed one keep working exactly as before. Nothing here may
import dashboard (it would load a second copy of the app).
"""

import re


# ---- Google Drive image storage -------------------------------------------
# Each account can set a master Drive FOLDER (its URL). Generated images for that
# account are uploaded into per-product subfolders named "{SKU}_{ProductName}".
# IMPORTANT: the Google service account email must be granted access (Editor) to
# that Drive folder, exactly like sharing a Google Sheet with it.
_DRIVE_FOLDER_CACHE = {}   # {"<parent>::<name>": folder_id}


def _drive_folder_id_from_url(url):
    """Pull the Drive folder ID out of a folder URL or accept a raw ID."""
    s = str(url or "").strip()
    if not s:
        return ""
    m = re.search(r"/folders/([A-Za-z0-9_-]+)", s)
    if m:
        return m.group(1)
    m = re.search(r"[?&]id=([A-Za-z0-9_-]+)", s)
    if m:
        return m.group(1)
    # raw id (no slashes/spaces)
    if re.fullmatch(r"[A-Za-z0-9_-]{20,}", s):
        return s
    return ""


def _drive_get_or_create_subfolder(svc, parent_id, name):
    """Return the ID of subfolder `name` under `parent_id`, creating it if needed."""
    name = str(name or "").strip()[:200] or "_misc"
    ck = f"{parent_id}::{name}"
    if ck in _DRIVE_FOLDER_CACHE:
        return _DRIVE_FOLDER_CACHE[ck]
    # look for an existing folder with this name under the parent
    safe_name = name.replace("'", "\\'")
    q = (f"name = '{safe_name}' and mimeType = 'application/vnd.google-apps.folder' "
         f"and '{parent_id}' in parents and trashed = false")
    try:
        res = svc.files().list(q=q, fields="files(id,name)", pageSize=1,
                               supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
        files = res.get("files", [])
        if files:
            _DRIVE_FOLDER_CACHE[ck] = files[0]["id"]
            return files[0]["id"]
    except Exception:
        pass
    # create it
    meta = {"name": name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]}
    created = svc.files().create(body=meta, fields="id", supportsAllDrives=True).execute()
    fid = created["id"]
    _DRIVE_FOLDER_CACHE[ck] = fid
    return fid


def _drive_direct_url(file_id):
    """Convert a Drive file id into a DIRECT image URL that external platforms
    (Amazon, eBay) can fetch. The reliable format is lh3.googleusercontent.com/d/<id>
    (the older drive.google.com/uc?export=view redirect is flaky). The file must
    also be shared 'anyone with link: reader' for this to load -- see _drive_make_public."""
    fid = str(file_id or "").strip()
    return f"https://lh3.googleusercontent.com/d/{fid}" if fid else ""


def _drive_make_public(svc, file_id):
    """Grant 'anyone with the link: reader' on a Drive file so external platforms
    can fetch the image. Idempotent -- ignores 'already exists' style errors."""
    try:
        svc.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
            supportsAllDrives=True,
        ).execute()
    except Exception:
        pass  # already public, or permission already present -> fine

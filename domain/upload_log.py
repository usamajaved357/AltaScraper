"""domain/upload_log.py -- every uploaded file that changed data, kept.

    "i want to track which files were uploaded recently for creating listings
     like amazon has it, it stores files which were used to create or make any
     changes in the listings using the files or templates"
    "all 7, keep forever, new sidebar item"

Seller Central keeps every inventory file you upload, with its processing
report. Here, until now, all seven uploads read the file, did the work and threw
the bytes away -- so "what did that sheet on Tuesday actually set?" had no
answer beyond memory.

ONE PLACE RECORDS AN UPLOAD (Rule 12). Each upload route calls record() once,
after it has done its work, with the bytes it received and the result it is
about to return. This module:

  * writes the ORIGINAL FILE, byte for byte, under <data dir>/uploads/<account>/
    <year>/<month>/ -- beside config.json, which is the persistent disk in
    production -- and never deletes it (kept for ever, by the owner's choice);
  * stores one upload_log row: kind, file name, size, checksum, who, when, the
    counts, the summary sentence and the per-row report;
  * builds the downloadable processing report from that per-row report.

NEVER FATAL. Recording happens after the upload did its work; a full disk or a
database hiccup must not turn a successful upload into an error. record()
returns None when it could not record, and the upload's own answer stands.

NOT A PREVIEW. A dry run changes nothing, so it is not recorded -- the upload
that follows it, with the same file, is.
"""
import base64
import csv
import hashlib
import io
import json
import os
import re
import time

# What each upload is, in words for the page. The key is what is stored.
KINDS = {
    "product_template": "Product template (new drafts)",
    "cost_sheet":       "Product cost sheet",
    "order_costs":      "Order cost sheet",
    "tracking":         "Tracking numbers",
    "supplier_links":   "Supplier links (repricer)",
    "min_prices":       "Min prices (repricer)",
    "miles_items":      "Miles item list",
}

DONE = "done"
DONE_WITH_ERRORS = "done_with_errors"
FAILED = "failed"

# A report row count this large is a sheet of ~100k products; past it the rows
# are cut, and the report says so. The FILE is always kept whole.
MAX_REPORT_ROWS = 50000


def _data_dir(config_path):
    return os.path.dirname(os.path.abspath(str(config_path or "config.json")))


def _safe(part, limit=100):
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", str(part or "")).strip("._")
    return (s or "file")[:limit]


def uploader(config_path):
    """Who is uploading: the signed-in user's email or name, "" for the owner."""
    try:
        from domain import job_owner as _jo
        uid = _jo.current()
        if not uid:
            return ""
        from auth import users as _users
        u = _users.get_user(config_path, uid)
        return str((u or {}).get("email") or (u or {}).get("name") or uid)
    except Exception:
        return ""


def decode_data_url(value):
    """A browser FileReader data URL (or bare base64) -> bytes. b"" if unreadable."""
    s = str(value or "")
    if not s:
        return b""
    if s.startswith("data:") and "," in s:
        s = s.split(",", 1)[1]
    try:
        return base64.b64decode(s, validate=False)
    except Exception:
        return b""


def record(config_path, workspace_id, marketplace, kind, filename, data, *,
           ok=0, skipped=0, errors=0, total=None, summary="", rows=None,
           skus=None, error="", uploaded_by=None):
    """Keep one upload: its file and what it did. -> the upload id, or None.

    `rows` is the per-row report the upload already builds -- a list of dicts
    (or plain strings for an error list) -- and becomes the processing report.
    `error` set means the file was received and refused as a whole.
    """
    try:
        from data import db as _db
        data = data if isinstance(data, (bytes, bytearray)) else bytes(str(data or ""), "utf-8")
        ws = str(workspace_id or "")
        mkt = str(marketplace or "").upper()
        kind = str(kind or "")
        name = os.path.basename(str(filename or "")) or "upload"
        rows = list(rows or [])
        if total is None:
            total = int(ok or 0) + int(skipped or 0) + int(errors or 0)
        if error:
            status = FAILED
        elif errors:
            status = DONE_WITH_ERRORS
        else:
            status = DONE
        report = [r if isinstance(r, dict) else {"note": str(r)}
                  for r in rows[:MAX_REPORT_ROWS]]
        who = uploaded_by if uploaded_by is not None else uploader(config_path)

        conn = _db.get_db(config_path)
        cur = conn.execute(
            "INSERT INTO upload_log (workspace_id, marketplace, kind, filename, bytes, "
            "sha256, uploaded_by, status, rows_total, rows_ok, rows_skipped, rows_error, "
            "summary, error, report_json, skus_json, uploaded_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (ws, mkt, kind, name, len(data), hashlib.sha256(data).hexdigest(), who,
             status, int(total or 0), int(ok or 0), int(skipped or 0), int(errors or 0),
             str(summary or "")[:2000], str(error or "")[:2000],
             json.dumps(report, ensure_ascii=False, default=str),
             json.dumps(sorted({str(s) for s in (skus or []) if str(s or "").strip()}),
                        ensure_ascii=False),
             time.strftime("%Y-%m-%d %H:%M:%S")))
        uid = cur.lastrowid
        conn.commit()

        # THE FILE ITSELF, named by the upload's id so two files with one name
        # never overwrite each other.
        rel = os.path.join("uploads", _safe(ws or "_no_account"),
                           time.strftime("%Y"), time.strftime("%m"),
                           "%d_%s" % (uid, _safe(name, 150)))
        full = os.path.join(_data_dir(config_path), rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as fh:
            fh.write(data)
        conn.execute("UPDATE upload_log SET stored_path=? WHERE id=?",
                     (rel.replace("\\", "/"), uid))
        conn.commit()
        return uid
    except Exception as e:
        try:
            print("[upload_log] not recorded: %s" % str(e)[:200], flush=True)
        except Exception:
            pass
        return None


_LIST_COLS = ("id, workspace_id, marketplace, kind, filename, bytes, uploaded_by, "
              "status, rows_total, rows_ok, rows_skipped, rows_error, summary, error, "
              "uploaded_at, stored_path, skus_json")


def _public(row):
    d = dict(row)
    d["kind_label"] = KINDS.get(d.get("kind"), d.get("kind") or "")
    try:
        skus = json.loads(d.pop("skus_json", None) or "[]")
    except Exception:
        skus = []
    d["sku_count"] = len(skus)
    d["skus"] = skus[:200]
    # An upload whose browser did not send the file (an old tab) keeps an empty
    # one; there is nothing to download, so no download is offered.
    d["has_file"] = bool(d.get("stored_path")) and bool(d.get("bytes"))
    d.pop("stored_path", None)
    return d


def recent(config_path, workspace_id, kind=None, limit=200):
    """This account's uploads, newest first. The file and report stay out of it."""
    from data import db as _db
    conn = _db.get_db(config_path)
    q = "SELECT %s FROM upload_log WHERE workspace_id=?" % _LIST_COLS
    args = [str(workspace_id or "")]
    if kind:
        q += " AND kind=?"
        args.append(str(kind))
    q += " ORDER BY id DESC LIMIT ?"
    args.append(max(1, min(int(limit or 200), 1000)))
    return [_public(r) for r in conn.execute(q, args)]


def get(config_path, upload_id, workspace_id):
    """One upload of THIS account, with its report. None if it is another's."""
    from data import db as _db
    conn = _db.get_db(config_path)
    r = conn.execute("SELECT * FROM upload_log WHERE id=? AND workspace_id=?",
                     (int(upload_id), str(workspace_id or ""))).fetchone()
    if not r:
        return None
    d = dict(r)
    try:
        d["report"] = json.loads(d.pop("report_json", None) or "[]")
    except Exception:
        d["report"] = []
    try:
        d["skus"] = json.loads(d.pop("skus_json", None) or "[]")
    except Exception:
        d["skus"] = []
    d["kind_label"] = KINDS.get(d.get("kind"), d.get("kind") or "")
    return d


def file_path(config_path, rec):
    """Where the original file is on disk, or "" if it is not there.

    Resolved inside the data directory only: a stored path that points anywhere
    else is refused rather than served.
    """
    rel = str((rec or {}).get("stored_path") or "")
    if not rel:
        return ""
    base = os.path.realpath(_data_dir(config_path))
    full = os.path.realpath(os.path.join(base, rel))
    if not full.startswith(base + os.sep) or not os.path.isfile(full):
        return ""
    return full


def _cell(v):
    if isinstance(v, (list, tuple)):
        return "; ".join(_cell(x) for x in v)
    if isinstance(v, dict):
        return json.dumps(v, ensure_ascii=False, default=str)
    return "" if v is None else str(v)


def report_csv(rec):
    """The processing report: one line per row the upload reported on. -> bytes.

    Columns are whatever that upload reports -- a cost sheet says sku/cost/
    status, a template says row/sku/status/note -- in the order they first
    appear, so nothing an upload chose to say is dropped.
    """
    report = (rec or {}).get("report") or []
    cols = []
    for r in report:
        for k in (r or {}).keys():
            if k not in cols:
                cols.append(k)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["upload", "file", "kind", "uploaded_at", "status", "summary"])
    w.writerow([rec.get("id"), rec.get("filename"), rec.get("kind_label"),
                rec.get("uploaded_at"), rec.get("status"),
                rec.get("error") or rec.get("summary") or ""])
    w.writerow([])
    if cols:
        w.writerow(cols)
        for r in report:
            w.writerow([_cell((r or {}).get(c)) for c in cols])
    else:
        w.writerow(["This upload reported no per-row detail."])
    if len(report) >= MAX_REPORT_ROWS:
        w.writerow([])
        w.writerow(["Report cut at %d rows; the original file is kept whole." % MAX_REPORT_ROWS])
    # utf-8-sig so Excel reads pound signs and accented names correctly.
    return buf.getvalue().encode("utf-8-sig")

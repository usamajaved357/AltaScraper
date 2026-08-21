"""monitor/known_sellers.py — classify a SellerId as ME / AMAZON / AUTHORISED / UNKNOWN.

Config-driven via config.json's "known_sellers" block, with a built-in seed so it works out of
the box. Only UNKNOWN third-party sellers get flagged (amber) and a one-time storefront-name
lookup; me / Amazon / authorised are labelled straight from config with NO fetch.

config.json shape (editable — add authorised resellers or missing Amazon IDs anytime):
  "known_sellers": {
    "me":         { "<sellerId>": "My Brand (you)" },
    "amazon":     { "UK": ["<amazonId>"], "DE": ["..."], ... },
    "authorised": { "<sellerId>": "Reseller Name" }
  }
"""

# Built-in seed. config.json's "known_sellers" is deep-merged OVER this at runtime.
# NOTE: Amazon retail IDs below marked (verify) are the widely-documented per-marketplace IDs;
# UK is confirmed live. Edit/extend in config.json. A wrong/missing Amazon ID only means that
# offer shows as UNKNOWN until you add it -- a harmless extra amber, never a missed threat.
_SEED = {
    # MY OWN seller IDs -- multiple owned entities supported (id -> business label).
    "me": {"A1VE7Q65PZSDVZ": "Promixx Inc (you)",
           "A2UGPOQGIOZGY1": "Promixx Ltd (you)"},
    "amazon": {
        "UK": ["A3P5ROKL5A1OLE"],   # confirmed live
        "DE": ["A3JWKAKR8XB7XF"],   # verify
        "FR": ["A1X6FK5RDHNB96"],   # verify
        "IT": ["A11IL2PNWYJU7H"],   # verify
        "ES": ["A1AT7YVPFBWXBL"],   # verify
    },
    "authorised": {},
}


import re
import json
import datetime
import threading

# Amazon's OWN retail storefront names -- DOMESTIC and CROSS-BORDER:
#   "Amazon", "Amazon.de", "Amazon.co.uk", "Amazon.com.be", "Amazon.nl",
#   "Amazon US", "Amazon EU", "Amazon UK", ...
# Strict on purpose -- "Amazon Warehouse", "Amazon Deals reseller" etc. must NOT match. Feedback
# count can't be the signal (several Amazon cross-border accounts have 0 feedback) -- the NAME is.
_AMAZON_NAME = re.compile(r"^\s*amazon(?:[.\s](?:co\.[a-z]{2}|com\.[a-z]{2}|[a-z]{2,3}))?\s*$", re.I)
_CFG_LOCK = threading.Lock()


def _norm(s):
    return str(s or "").strip()


def _amz_id(entry):
    """An amazon[mkt] entry may be a bare id string OR a tagged object {id, source, name, at}."""
    return _norm(entry.get("id")) if isinstance(entry, dict) else _norm(entry)


def load(cfg):
    """Merge config.json's known_sellers OVER the built-in seed."""
    block = (cfg or {}).get("known_sellers") or {}
    me = dict(_SEED["me"]); me.update({_norm(k): v for k, v in (block.get("me") or {}).items()})
    auth = dict(_SEED["authorised"]); auth.update({_norm(k): v for k, v in (block.get("authorised") or {}).items()})
    # names: an EDITABLE {sellerId: "Business Name"} map for KNOWN unknown third parties -- lets you
    # label a flagged seller (it stays type=unknown) without a code change. Add to it anytime.
    names = dict(_SEED.get("names", {})); names.update({_norm(k): v for k, v in (block.get("names") or {}).items()})
    amazon = {mk: list(ids) for mk, ids in _SEED["amazon"].items()}
    for mk, ids in (block.get("amazon") or {}).items():
        MK = str(mk).upper()
        amazon.setdefault(MK, [])
        for i in (ids if isinstance(ids, (list, tuple)) else [ids]):
            iid = _amz_id(i)                          # tolerate bare-id OR tagged-object entries
            if iid and iid not in amazon[MK]:
                amazon[MK].append(iid)
    return {"me": me, "amazon": amazon, "authorised": auth, "names": names}


def name_for(seller_id, cfg):
    """A manually-stored display name for a seller id (from known_sellers.names), or ""."""
    return load(cfg).get("names", {}).get(_norm(seller_id), "")


def set_seller(config_path, seller_id, name="", kind="name", marketplace=""):
    """Label/classify a seller GLOBALLY BY SELLER ID from the UI -> writes config.json known_sellers.
    The mapping is keyed only by seller id, so it applies to EVERY ASIN and marketplace (past
    snapshots + future checks). kind: 'name' (named third party, STAYS flagged) | 'authorised'
    (trusted, neutral) | 'me' (yours, teal) | 'amazon' (Amazon retail, neutral) | 'unknown' (REVERT
    -- remove all labels, flag it again). Removes the id from every block first so re-classifying is
    clean. Returns {ok, kind, previous:{kind,label}} so the caller can audit the change."""
    import json
    sid = _norm(seller_id)
    if not sid:
        return {"ok": False, "error": "no seller id"}
    kind = (kind or "name").lower()
    name = str(name or "").strip()
    with _CFG_LOCK:
        try:
            with open(config_path, encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as e:
            return {"ok": False, "error": f"could not read config: {str(e)[:120]}"}
        previous = classify(sid, "", cfg)              # what it was, BEFORE we change anything
        ks = cfg.setdefault("known_sellers", {})
        # Through the same helper the CSV import uses, so the rules about which
        # block a kind belongs in live in exactly one place.
        _apply_one(ks, sid, name, kind, marketplace)
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
        except Exception as e:
            return {"ok": False, "error": f"could not write config: {str(e)[:120]}"}
    return {"ok": True, "kind": kind, "previous": previous}


def _apply_one(ks, sid, name, kind, marketplace=""):
    """Put ONE seller into the right block of an already-loaded known_sellers.

    Lifted out of set_seller so the single-seller path and the CSV import share
    it -- the rules for which block a kind goes in, and for clearing the id out
    of the others first, are the sort of thing that quietly diverges when it
    exists twice (CLAUDE.md rule 12).
    """
    for blk in ("names", "me", "authorised"):      # id is GLOBAL -> clear it everywhere first
        if isinstance(ks.get(blk), dict):
            ks[blk].pop(sid, None)
    for mk in list((ks.get("amazon") or {}).keys()):
        ks["amazon"][mk] = [e for e in ks["amazon"][mk] if _amz_id(e) != sid]
    if kind == "me":
        ks.setdefault("me", {})[sid] = name or "My account (you)"
    elif kind == "authorised":
        ks.setdefault("authorised", {})[sid] = name or sid
    elif kind == "amazon":
        mk = str(marketplace or "").upper() or "UK"
        ks.setdefault("amazon", {}).setdefault(mk, []).append(
            {"id": sid, "source": "manual", "name": name})
    elif kind == "unknown":
        pass                                       # REVERT: in no block -> flagged again
    else:                                          # 'name' -> named third party, stays flagged
        ks.setdefault("names", {})[sid] = name or sid


def set_sellers_bulk(config_path, rows):
    """Label MANY sellers in ONE read-modify-write of config.json.

        "i have the names of the sellers which i can put in a csv file to tell
         the asin monitor that this seller id's person name is this. whether it
         is amazon, myself, or a third party. right now i have the ability to do
         it manually one by one"

    `rows` is [{seller_id, name, kind, marketplace}]. Returns
    {ok, applied, skipped, changes:[{seller_id, name, kind, previous}]}.

    ONE WRITE, NOT ONE PER SELLER. set_seller reloads, edits and rewrites the
    whole config for each seller; a hundred-row CSV would be a hundred
    read-modify-writes of a file the running app is also reading, with a hundred
    chances to interleave badly. This takes the lock once.

    THE MAPPING IS BY SELLER ID AND NOTHING ELSE, which is the point of doing it
    in bulk at all. The auto-scraped cache in asin_monitor_history.json is keyed
    "sellerId::marketplace", so the same seller in eight countries is eight
    entries and naming them by hand is eight jobs. A seller's name is the same
    everywhere, so one CSV row settles it for every marketplace and every ASIN,
    past snapshots included.
    """
    import json
    out = {"ok": True, "applied": 0, "skipped": [], "changes": []}
    rows = list(rows or [])
    if not rows:
        return {"ok": False, "error": "nothing to apply"}
    with _CFG_LOCK:
        try:
            with open(config_path, encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as e:
            return {"ok": False, "error": "could not read config: %s" % str(e)[:120]}
        ks = cfg.setdefault("known_sellers", {})
        seen = set()
        for r in rows:
            sid = _norm((r or {}).get("seller_id"))
            if not sid:
                out["skipped"].append({"row": r, "why": "no seller id"})
                continue
            if sid in seen:
                # LAST ONE WINS would be silent. A CSV listing the same seller
                # twice with two different names is a mistake worth naming.
                out["skipped"].append({"row": r, "why": "seller id repeated in the file"})
                continue
            seen.add(sid)
            kind = str((r or {}).get("kind") or "name").lower()
            if kind not in ("name", "authorised", "me", "amazon", "unknown"):
                out["skipped"].append({"row": r, "why": "unknown kind %r" % kind})
                continue
            name = str((r or {}).get("name") or "").strip()
            prev = classify(sid, "", cfg)
            _apply_one(ks, sid, name, kind, (r or {}).get("marketplace") or "")
            out["applied"] += 1
            out["changes"].append({"seller_id": sid, "name": name, "kind": kind,
                                   "previous": prev})
        if not out["applied"]:
            return {"ok": False, "error": "no usable rows",
                    "skipped": out["skipped"]}
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
        except Exception as e:
            return {"ok": False, "error": "could not write config: %s" % str(e)[:120]}
    return out


def current(cfg, seller_id):
    """The seller's CURRENT global classification {kind,label} (marketplace-agnostic) from config."""
    return classify(seller_id, "", cfg)


def looks_like_amazon(name, marketplace=""):
    """True if a resolved storefront name is Amazon's OWN retail account for a marketplace."""
    return bool(_AMAZON_NAME.match(str(name or "")))


def auto_add_amazon(config_path, seller_id, marketplace, name):
    """AUTO-CLASSIFICATION: persist an auto-detected Amazon retail SellerId into config.json
    known_sellers.amazon[<mkt>], tagged source='auto' with the resolved name + timestamp, so the
    user never maintains Amazon IDs by hand. Only Amazon is ever auto-added -- never 'me' or
    'authorised' (those stay manual; unknown is the safe default). Returns True if newly added."""
    sid = _norm(seller_id); mkt = str(marketplace or "").upper()
    if not sid or not mkt:
        return False
    with _CFG_LOCK:
        try:
            with open(config_path, encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            return False
        ks = cfg.setdefault("known_sellers", {})
        amz = ks.setdefault("amazon", {})
        lst = amz.setdefault(mkt, [])
        if any(_amz_id(e) == sid for e in lst):
            return False                              # already known for this marketplace
        lst.append({"id": sid, "source": "auto", "name": _norm(name),
                    "at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")})
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
        except Exception:
            return False
        return True


def classify(seller_id, marketplace, cfg, name=""):
    """Return {"kind": me|amazon|authorised|unknown, "label": str}. Only 'unknown' is a threat."""
    sid = _norm(seller_id)
    mkt = str(marketplace or "").upper()
    k = load(cfg)
    if sid and sid in k["me"]:
        return {"kind": "me", "label": k["me"][sid]}
    amz = k["amazon"].get(mkt, []) + sum((v for kk, v in k["amazon"].items() if kk != mkt), [])
    if sid and sid in amz:
        return {"kind": "amazon", "label": "Amazon"}
    if sid and sid in k["authorised"]:
        return {"kind": "authorised", "label": k["authorised"][sid]}
    # unknown third party -- but show a stored/resolved NAME if we have one (stays flagged)
    return {"kind": "unknown", "label": (name or k.get("names", {}).get(sid) or sid or "unknown seller")}



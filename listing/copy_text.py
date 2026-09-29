"""listing/copy_text.py -- listing copy text: the Claude call, message content, search terms, length caps, brand prompt, autocomplete keywords.

Moved word for word out of amazon_listing_generator.py (Milestone 4, owner-approved 28 Sep 2026).
amazon_listing_generator.py still imports every name below, so dashboard.<name> and every
route that is handed one keep working exactly as before. Nothing here may
import dashboard (it would load a second copy of the app).
"""
from api.anthropic_client import client as _ai_client   # arch A7: one constructor

import base64
import urllib.parse
import json
import re


def _claude(config):
    """The Claude client. ONE place, so the library loads only when it is used.

    Written out identically at four call sites (generate, retry, optimise,
    Miles). Beyond the duplication, each of those copies is reached only on the
    run it belongs to, while the import at the top of the file was paid on all
    of them -- 2.1 seconds, on runs like export that never call Claude at all.
    """
    import anthropic
    return _ai_client(config["anthropic_api_key"])


INFORMATIONAL = ["what is", "how does", "why is", "history of",
                  "difference between", "meaning of"]


def get_autocomplete_keywords(core_term: str) -> list:
    variations = [core_term, f"best {core_term}", f"{core_term} set",
                  f"{core_term} for", f"buy {core_term}"]
    headers    = {
        "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "en-GB,en;q=0.9",
        "Accept":          "application/json, text/javascript, */*",
    }
    seen, all_kws = set(), []
    for v in variations:
        enc = urllib.parse.quote(v)
        url = (f"https://completion.amazon.co.uk/search/complete"
               f"?method=completion&q={enc}&search-alias=aps&mkt=3&x=String")
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as r:
                data = json.loads(r.read().decode("utf-8"))
            if isinstance(data, list) and len(data) > 1:
                for pos, s in enumerate(data[1]):
                    if isinstance(s, str) and 3 < len(s) < 100:
                        kl = s.lower().strip()
                        if kl not in seen and not any(inf in kl for inf in INFORMATIONAL):
                            seen.add(kl)
                            all_kws.append({"keyword":   kl,
                                            "vol_score": round(max(0, 1 - pos / 15), 2)})
        except Exception:
            continue
    all_kws.sort(key=lambda x: x["vol_score"], reverse=True)
    return all_kws[:30]


def extract_core_search_term(item_name: str) -> str:
    noise   = r"\b(\d+|pcs|pc|pack|piece|inch|lbs|lot|uk|usa|new|best|buy|get|the|and|with|for)\b"
    cleaned = re.sub(noise, "", item_name.lower(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    words   = [w for w in cleaned.split() if len(w) > 2][:5]
    return " ".join(words) if words else item_name[:30]


def _build_message_content(prompt: str, images: list) -> list:
    """Build Claude message content. Images are validated by magic bytes and
    size before being attached; bad images are skipped silently."""
    # Anthropic-supported formats
    MAGIC = {
        b"\xff\xd8\xff":           "image/jpeg",
        b"\x89PNG\r\n\x1a\n":      "image/png",
        b"GIF87a":                 "image/gif",
        b"GIF89a":                 "image/gif",
        b"RIFF":                   "image/webp",   # checked further below
    }
    MAX_IMG_BYTES = 4_500_000   # ~4.5 MB (Anthropic limit is 5 MB)
    MIN_IMG_BYTES = 1_000       # reject tiny 1x1 trackers / 0-byte responses

    content = []
    for img_url in images[:2]:
        if not img_url or not img_url.startswith("http"):
            continue
        try:
            req = urllib.request.Request(img_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                img_bytes = r.read()
        except Exception:
            continue
        if not img_bytes or len(img_bytes) < MIN_IMG_BYTES:
            continue
        if len(img_bytes) > MAX_IMG_BYTES:
            continue
        # Detect actual media type by magic bytes (ignore URL extension - it lies)
        media_type = None
        for sig, mt in MAGIC.items():
            if img_bytes.startswith(sig):
                if sig == b"RIFF":
                    # WebP files: 'RIFF' + 4-byte size + 'WEBP'
                    if len(img_bytes) >= 12 and img_bytes[8:12] == b"WEBP":
                        media_type = "image/webp"
                else:
                    media_type = mt
                break
        if not media_type:
            continue
        img_b64 = base64.b64encode(img_bytes).decode("utf-8")
        content.append({"type": "image",
                         "source": {"type": "base64",
                                    "media_type": media_type,
                                    "data": img_b64}})
    if content:
        content.append({"type": "text",
                         "text": ("Above: product images of the competitor item. "
                                  "Use them to visually confirm: material, colour, "
                                  "handle material, finish type.\n\n" + prompt)})
    else:
        content.append({"type": "text", "text": prompt})
    return content


SEARCH_TERMS_MAX_BYTES = 249


def clean_search_terms(st: str) -> str:
    """Backend search terms: strip ALL punctuation, collapse to single spaces,
    lowercase, then byte-cap at 249 (Amazon ignores the whole field if over).
    Spaces are kept (Amazon tokenises on them); only punctuation is removed."""
    if not st:
        return ""
    import re as _re
    # replace any punctuation/separators with a space, then collapse spaces
    st = _re.sub(r"[^\w\s]", " ", st, flags=_re.UNICODE)
    st = _re.sub(r"\s+", " ", st).strip().lower()
    b = st.encode("utf-8")
    if len(b) > SEARCH_TERMS_MAX_BYTES:
        st = b[:SEARCH_TERMS_MAX_BYTES].decode("utf-8", "ignore")
        # don't end mid-word
        if " " in st:
            st = st[:st.rfind(" ")].strip()
    return st


def cap_chars(s: str, n: int) -> str:
    """Trim to n characters and STILL READ AS A FINISHED SENTENCE.

    Cutting on a word boundary keeps words whole, which is necessary and not
    sufficient. On a real listing this produced a bullet ending

        ...suitable for users of all experience levels who wish to practise
        aerial yoga, stretching, or simply

    -- every word intact and the sentence abandoned mid-thought, published to
    Amazon exactly like that. A customer reads that as a broken listing, which
    is the one thing the copy is there to avoid.

    So: end at the last full stop when there is one reasonably near the limit,
    and otherwise fall back to the word boundary with any dangling conjunction
    or comma removed. Losing a clause is better than printing half of one.
    """
    s = (s or "").rstrip()
    if len(s) <= n:
        return s
    cut = s[:n]

    # A sentence end, if one sits in the last third of what we are allowed to
    # keep. Nearer the start than that and we would throw away too much.
    floor = int(n * 0.6)
    best = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    if best < 0 and cut.rstrip().endswith((".", "!", "?")):
        best = len(cut.rstrip()) - 1
    if best >= floor:
        return cut[:best + 1].rstrip()

    # No usable sentence end: whole words, and nothing left hanging.
    if " " in cut:
        cut = cut[:cut.rfind(" ")].rstrip()
    cut = cut.rstrip(" ,;:-–—")
    _tail = cut.rsplit(" ", 1)[-1].lower() if " " in cut else ""
    while _tail in ("and", "or", "but", "with", "for", "to", "the", "a", "an",
                    "of", "in", "on", "as", "that", "which", "while", "from"):
        cut = cut[:cut.rfind(" ")].rstrip().rstrip(" ,;:-–—")
        _tail = cut.rsplit(" ", 1)[-1].lower() if " " in cut else ""
    return cut


def prompt_for_brand() -> str:
    """Ask user once for the brand to use across this run.
    Empty string = auto-pick per category from schema."""
    try:
        entered = input("Enter brand name (or press Enter to auto-pick per category): ").strip()
    except EOFError:
        entered = ""
    return entered

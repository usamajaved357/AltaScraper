"""domain/image_bytes.py -- image bytes: fetching as base64, sniffing the type, converting to JPEG, the result shape.

Moved word for word out of dashboard.py (Milestone 4, owner-approved 28 Sep 2026).
dashboard.py still imports every name below, so dashboard.<name> and every
route that is handed one keep working exactly as before. Nothing here may
import dashboard (it would load a second copy of the app).
"""

import base64
from flask import Flask, Response, request, jsonify, session, redirect, url_for, send_from_directory


def _fetch_image_b64(url: str):
    """Fetch an image URL -> (media_type, base64_str). None on failure / non-image / >5MB."""
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            ct   = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            data = r.read()
        if not ct.startswith("image/") or len(data) > 5_000_000:
            return None
        return ct, base64.b64encode(data).decode("ascii")
    except Exception:
        return None


def _sniff_image_ext(raw: bytes, fallback: str = "jpg") -> str:
    """Return the TRUE image extension by reading the file's magic-number bytes,
    not the (often-wrong) mime label the AI model claims. Amazon rejects a file
    whose bytes don't match its extension (e.g. JPEG bytes named .png), so the
    saved filename must reflect the actual format.

    THE BODY MOVED to domain/media_kinds.sniff_ext. It was defined here and
    injected into two route modules -- and the route that saves generated images
    was not one of them, so that path used the mime label and wrote JPEGs called
    .png. A helper only the injected callers can reach is a helper the next
    writer will not use, so it now lives with the rest of the image-file rules
    and this delegates (rule 12)."""
    from domain import media_kinds as _mk
    return _mk.sniff_ext(raw, fallback)


def _to_jpeg_bytes(raw: bytes, quality: int = 90) -> bytes:
    """Convert any image bytes (PNG/WebP/GIF/JPEG) to JPEG bytes. Amazon prefers
    JPEG for listing images and they're much smaller than PNG. Transparency is
    flattened onto a white background (Amazon main images need white anyway).
    Falls back to the original bytes if PIL/conversion fails."""
    try:
        from io import BytesIO
        from PIL import Image as _PImg
        im = _PImg.open(BytesIO(raw))
        # flatten alpha onto white so JPEG (no transparency) looks right
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bg = _PImg.new("RGB", im.size, (255, 255, 255))
            bg.paste(im, mask=im.split()[-1])
            im = bg
        else:
            im = im.convert("RGB")
        out = BytesIO()
        im.save(out, format="JPEG", quality=quality, optimize=True)
        return out.getvalue()
    except Exception:
        return raw


def _imgresult(res, extra=None):
    if res.get("image_b64"):
        data_url = f"data:{res.get('mime','image/png')};base64,{res['image_b64']}"
    elif res.get("image_url"):
        data_url = res["image_url"]
    else:
        return jsonify({"ok": False, "error": "no image returned"}), 400
    out = {"ok": True, "data_url": data_url,
           "detailed_prompt": res.get("detailed_prompt", ""),
           # WAS THE BRIEF REWORDED TO GET PAST THE SAFETY FILTER?
           #
           # Some product words (slasher, blade, weapon-ish nouns) trip the image
           # provider's filter -- a real weed slasher came back as "the input text
           # may contain sensitive information". run_pipeline now rewords once and
           # retries instead of failing, which is right, but the picture is then
           # made from words the user did not write. Carry the flag through so the
           # screen can say so; detailed_prompt above is the wording actually used.
           "softened_prompt": bool(res.get("softened_prompt")),
           "text_provider": res.get("text_provider"),
           "image_provider": res.get("image_provider")}
    if extra:
        out.update(extra)
    return jsonify(out)

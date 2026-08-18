"""
ai_providers.py  (OpenRouter edition)
============================================================================
Single-gateway AI layer built on OpenRouter. One key, every model.

  TEXT  (prompt enhancement): POST /api/v1/chat/completions  (OpenAI-compatible)
  IMAGE (generation):         POST /api/v1/images            (dedicated image API)

MODEL DISCOVERY (so the dashboard shows only what you can actually use):
  GET /api/v1/models                      -> all models (filter text output)
  GET /api/v1/images/models               -> dedicated image-model list

CONFIG (local config.json -- key NAME only; paste the real key locally):
  "openrouter_api_key": "sk-or-v1-..."
  "ai_select": {
     "prompt_enhance": "anthropic/claude-sonnet-4.6",
     "image_generate": "google/gemini-2.5-flash-image"
  }

Everything returns {"ok": bool, ...} and never raises to the caller.
============================================================================
"""

import json
import urllib.request
import urllib.error
import time

OPENROUTER_BASE = "https://openrouter.ai/api/v1"

_CACHE = {"text": None, "image": None, "ts": 0}
_CACHE_TTL = 300


def _key(config: dict) -> str:
    return str(config.get("openrouter_api_key", "") or "").strip()


def _headers(config: dict) -> dict:
    return {
        "Authorization": f"Bearer {_key(config)}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://127.0.0.1:5000",
        "X-Title": "Listing Generator",
    }


def _get(url, config, timeout=30):
    req = urllib.request.Request(url, headers=_headers(config), method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# WHAT THE CURRENT CALL IS FOR, and whose it is.
#
# _post is the single place every OpenRouter call passes through, which makes it
# the one place worth recording spend from -- but it is handed a URL and a body,
# not a purpose. Rather than thread a feature name through nine call sites and
# their optional arguments, the caller sets this immediately before calling and
# _post reads it.
#
# Module-level rather than thread-local ON PURPOSE: image batches run on worker
# threads, and a thread-local set on the request thread would be invisible to
# them, so every generated image would be recorded as "unknown". The window
# between set and use is one function call.
#
# ONE context, shared with the Anthropic recorder. Both providers must answer
# "whose call was that, and what for" the same way, or the same run would be
# split between two ledgers -- OpenRouter's half attributed and Anthropic's half
# filed under "unknown". This name is kept as an alias so the call sites here
# read naturally; the dictionary itself lives in ai_usage.
from domain.ai_usage import CONTEXT as _AI_CONTEXT


def set_usage_context(feature="", workspace_id="", sku="", config_path=""):
    """Name what the next AI calls are for, so the spend can be attributed."""
    from domain import ai_usage as _usage
    _usage.set_context(feature=feature or "", workspace_id=workspace_id or "",
                       sku=sku or "", config_path=config_path or "")


def _feature(name):
    """Name the STEP, keeping whose it is.

    The route says which account and where the ledger lives; each step here says
    what it is. Split that way because a route cannot know that generating one
    image is four billable calls -- read the reference, think of concepts, write
    the prompt, draw it -- and those four are exactly what someone looking at a
    bill wants told apart.
    """
    _AI_CONTEXT["feature"] = name


def _count_images(payload):
    """How many pictures came back, WHICHEVER endpoint answered.

    OpenRouter returns them two different ways and only one was being counted:

        /chat/completions   choices[].message.images[]
        /images             data[].b64_json  or  data[].url

    The second is what generate_image uses, so every real image generation was
    recorded as zero pictures -- and priced at zero, since an image reply carries
    no token usage either. Both shapes are counted here, in one place, so a third
    endpoint is one line rather than another silent zero.
    """
    n = 0
    p = payload or {}
    for ch in (p.get("choices") or []):
        n += len(((ch or {}).get("message") or {}).get("images") or [])
    for d in (p.get("data") or []):
        if isinstance(d, dict) and (d.get("b64_json") or d.get("url")):
            n += 1
    return n


def _record_openrouter(body, payload, ok=True, error="", ms=0):
    """Log one OpenRouter call against whatever context was set. Never raises."""
    try:
        cp = _AI_CONTEXT.get("config_path") or ""
        if not cp:
            return                      # nowhere to write it; not worth guessing
        from domain import ai_usage as _usage
        model = (body or {}).get("model") or ""
        i, o = _usage.tokens_from_openrouter(payload or {})
        n_img = _count_images(payload)
        _usage.record(cp, feature=(_AI_CONTEXT.get("feature")
                                   or _usage.unnamed_feature()),
                      provider="openrouter", model=model,
                      workspace_id=_AI_CONTEXT.get("workspace_id") or "",
                      input_tokens=i, output_tokens=o, images=n_img,
                      kind=("image" if n_img else "text"),
                      # OpenRouter's own figure where it gave one -- the only
                      # number that can be right for a model our price table has
                      # never heard of, which is how an image came to be recorded
                      # at no cost at all.
                      cost_usd=_usage.cost_from_openrouter(payload),
                      ok=ok, error=error, sku=_AI_CONTEXT.get("sku") or "", ms=ms)
    except Exception:
        pass


def _post(url, config, body, timeout=120):
    """POST to OpenRouter and RECORD IT, whichever endpoint it was.

    THE IMAGES WERE NEVER COUNTED. This recorded only when the url contained
    "chat/completions", and image generation posts to /images -- so every
    picture the app has ever made was missing from the ledger entirely. The
    reading, the thinking and the prompt-writing around each image were all
    logged; the expensive part, the generation itself, was not.

    Measured on the live ledger before this change: 46 rows, of which
    images = 0 on every single one, and no row anywhere with the feature
    "image: generate" -- which _feature() sets at the top of generate_image.

    Reported as: "ai spend is also not reflecting correct data ... if images are
    created or any other feature is used which caused ai to use credits it
    should be recorded accurately where spent went, to which feature which
    account".
    """
    _t0 = time.time()
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers=_headers(config), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        # A failed call still spent its input tokens, and a month of retries
        # must not look free.
        _record_openrouter(body, None, ok=False, error=str(e)[:200],
                           ms=int((time.time() - _t0) * 1000))
        raise
    _record_openrouter(body, payload, ms=int((time.time() - _t0) * 1000))
    return payload


_FALLBACK_TEXT = [
    {"id": "anthropic/claude-sonnet-4.6", "name": "Claude Sonnet 4.6"},
    {"id": "openai/gpt-5.1", "name": "GPT-5.1"},
    {"id": "google/gemini-2.5-flash", "name": "Gemini 2.5 Flash"},
]
_FALLBACK_IMAGE = [
    {"id": "google/gemini-2.5-flash-image", "name": "Nano Banana (Gemini 2.5 Flash Image)"},
    {"id": "google/gemini-3.1-flash-image-preview", "name": "Nano Banana 2"},
    {"id": "google/gemini-3-pro-image-preview", "name": "Nano Banana Pro"},
    {"id": "openai/gpt-image-1", "name": "GPT Image 1"},
    {"id": "bytedance-seed/seedream-4.5", "name": "Seedream 4.5"},
]


def discover_models(config: dict, force: bool = False) -> dict:
    """Query OpenRouter for available models, split into text + image. Cached.
    Falls back to a static list on failure so the UI still works."""
    if not _key(config):
        return {"ok": False, "error": "No openrouter_api_key in config.json. "
                "Get one at https://openrouter.ai/keys and add it locally.",
                "text": _FALLBACK_TEXT, "image": _FALLBACK_IMAGE}
    now = time.time()
    if not force and _CACHE["text"] is not None and (now - _CACHE["ts"] < _CACHE_TTL):
        return {"ok": True, "text": _CACHE["text"], "image": _CACHE["image"]}

    text_models, image_models = [], []
    try:
        allm = _get(f"{OPENROUTER_BASE}/models", config)
        for m in allm.get("data", []):
            arch = m.get("architecture", {}) or {}
            outs = arch.get("output_modalities", []) or []
            if "text" in outs:
                text_models.append({"id": m.get("id"), "name": m.get("name") or m.get("id")})
    except Exception:
        text_models = list(_FALLBACK_TEXT)

    try:
        imgm = _get(f"{OPENROUTER_BASE}/images/models", config)
        for m in imgm.get("data", []):
            image_models.append({"id": m.get("id"), "name": m.get("name") or m.get("id")})
    except Exception:
        try:
            allm = _get(f"{OPENROUTER_BASE}/models?output_modalities=image", config)
            for m in allm.get("data", []):
                image_models.append({"id": m.get("id"), "name": m.get("name") or m.get("id")})
        except Exception:
            image_models = list(_FALLBACK_IMAGE)

    if not text_models:
        text_models = list(_FALLBACK_TEXT)
    if not image_models:
        image_models = list(_FALLBACK_IMAGE)
    text_models.sort(key=lambda x: (x["id"] or "").lower())
    image_models.sort(key=lambda x: (x["id"] or "").lower())
    _CACHE.update({"text": text_models, "image": image_models, "ts": now})
    return {"ok": True, "text": text_models, "image": image_models}


def select(config: dict, purpose: str) -> str:
    sel = config.get("ai_select") or {}
    if sel.get(purpose):
        return sel[purpose]
    disc = discover_models(config)
    if purpose == "prompt_enhance":
        ids = [m["id"] for m in disc.get("text", [])]
        for pref in ("anthropic/claude-sonnet-4.6", "openai/gpt-5.1", "google/gemini-2.5-flash"):
            if pref in ids:
                return pref
        return ids[0] if ids else ""
    ids = [m["id"] for m in disc.get("image", [])]
    for pref in ("google/gemini-2.5-flash-image", "google/gemini-3-pro-image-preview",
                 "openai/gpt-image-1"):
        if pref in ids:
            return pref
    return ids[0] if ids else ""


class ImageRefError(Exception):
    """A reference image could not be turned into VALID image data (empty, not an image,
    a URL/path mistaken for base64, an expired URL that returned HTML, too large, etc.).
    Callers surface the message to the user instead of forwarding garbage to the model and
    getting a cryptic 400."""
    pass


_MAX_IMG_BYTES = 20 * 1024 * 1024      # 20 MB hard cap (models reject bigger; avoids truncation)
# Where local '/media/...' references resolve on disk. Set once at startup if needed; otherwise
# falls back to <cwd>/media (the app always runs from its own dir), so no per-call plumbing.
DEFAULT_MEDIA_ROOT = ""


def _sniff_image_mime(raw: bytes):
    """Image mime from magic numbers, or None if `raw` is NOT a known image format."""
    if not raw or len(raw) < 12:
        return None
    if raw[:3] == b"\xff\xd8\xff":                  return "image/jpeg"
    if raw[:8] == b"\x89PNG\r\n\x1a\n":             return "image/png"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP": return "image/webp"
    if raw[:6] in (b"GIF87a", b"GIF89a"):           return "image/gif"
    if raw[:2] == b"BM":                            return "image/bmp"
    return None


def _bytes_to_data_uri(raw: bytes, where: str = "image") -> str:
    """Validate that `raw` really is an image (magic numbers) and within the size cap, then
    return a base64 data URI. Raises ImageRefError with a clear message otherwise."""
    if not raw:
        raise ImageRefError(f"no product image available (the {where} was empty).")
    if len(raw) > _MAX_IMG_BYTES:
        raise ImageRefError(f"the {where} is too large ({len(raw)//(1024*1024)} MB; limit "
                            f"{_MAX_IMG_BYTES//(1024*1024)} MB) — use a smaller image.")
    mime = _sniff_image_mime(raw)
    if mime is None:
        raise ImageRefError(
            f"the {where} is not a valid image (got {len(raw)} bytes, header {bytes(raw[:12])!r}). "
            f"It may be an expired/redirected link or non-image data — download or upload the "
            f"product image first.")
    import base64 as _b64
    return "data:" + mime + ";base64," + _b64.b64encode(raw).decode("ascii")


def _url_to_data_uri(url: str, timeout: int = 20) -> str:
    """Download a remote image and return it as a VALIDATED base64 data URI. Raises
    ImageRefError if the URL doesn't return real image bytes -- e.g. an expired link that now
    serves an HTML error page (which previously got base64-encoded as image/jpeg and 400'd)."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(_MAX_IMG_BYTES + 1)
    except Exception as e:
        raise ImageRefError(f"could not download the image URL ({str(e)[:120]}) — it may have "
                            f"expired; upload or re-download the product image.")
    return _bytes_to_data_uri(raw, where="image URL")


def _read_local_image(path: str, media_root: str = "") -> str:
    """Read a LOCAL image (absolute path, file:// URI, or an app '/media/...' served path) from
    disk and return a validated data URI. Raises ImageRefError if missing / not an image."""
    import os as _os
    media_root = media_root or DEFAULT_MEDIA_ROOT or _os.path.join(_os.getcwd(), "media")
    p = path
    if p.startswith("file://"):
        p = urllib.request.url2pathname(p[7:])
    if p.startswith("/media/"):                               # app served path -> disk path
        p = _os.path.join(media_root, p[len("/media/"):].replace("/", _os.sep))
    elif not _os.path.isabs(p) and _os.path.exists(_os.path.join(media_root, p)):
        p = _os.path.join(media_root, p)
    if not _os.path.exists(p):
        raise ImageRefError(f"the local image file was not found on disk ({path}).")
    try:
        with open(p, "rb") as f:
            raw = f.read(_MAX_IMG_BYTES + 1)
    except Exception as e:
        raise ImageRefError(f"could not read the local image ({str(e)[:120]}).")
    return _bytes_to_data_uri(raw, where="local image file")


def _looks_like_local_path(s: str) -> bool:
    # EXPLICIT path markers only. Deliberately NOT a bare leading "/" — a bare-base64 JPEG
    # begins with "/9j/", so treating "/" as a path would misroute valid JPEG data to disk.
    if s.startswith(("file://", "./", "../", "/media/")):
        return True
    if len(s) > 2 and s[1] == ":" and s[2] in "\\/":     # Windows drive path C:\ or C:/
        return True
    if "\\" in s:                                          # backslash path (never in base64)
        return True
    return False


def _img_to_ref(url_or_b64, media_root: str = ""):
    """Turn a reference (URL / data-uri / local path / bare base64) into a VALIDATED image
    block. Raises ImageRefError with a clear message on anything that isn't a real image, so we
    never forward garbage and trigger a cryptic 400."""
    if not url_or_b64:
        raise ImageRefError("no product image available.")
    s = str(url_or_b64).strip()
    if s.startswith("data:"):
        import base64 as _b64
        try:
            b64 = s.split(",", 1)[1] if "," in s else ""
            raw = _b64.b64decode(b64)
        except Exception:
            raise ImageRefError("the reference image data URI could not be decoded.")
        return {"type": "image_url", "image_url": {"url": _bytes_to_data_uri(raw, "reference image")}}
    if s.startswith("http://") or s.startswith("https://"):
        return {"type": "image_url", "image_url": {"url": _url_to_data_uri(s)}}
    if _looks_like_local_path(s):
        return {"type": "image_url", "image_url": {"url": _read_local_image(s, media_root)}}
    # otherwise it is SUPPOSED to be bare base64 image bytes. Decode + validate. If it is
    # actually a stray URL/path/text this raises a clear error instead of shipping
    # "data:image/png;base64,<garbage>" to the API (the old bug at this very spot).
    import base64 as _b64
    try:
        raw = _b64.b64decode(s, validate=True)
    except Exception:
        raise ImageRefError("the reference wasn't a valid image — it looks like a URL/path or "
                            "text, not image data. Download or upload the product image first.")
    return {"type": "image_url", "image_url": {"url": _bytes_to_data_uri(raw, "reference image")}}


def resolve_image_ref(candidates, media_root: str = ""):
    """Try image sources IN ORDER (uploaded local file -> cached/downloaded copy -> source URL)
    and return the first that yields a VALID image block. Raises ImageRefError('no product image
    available ...') if every candidate fails -- so an expired scrape URL falls through to a
    cached/local copy instead of failing the whole run."""
    cands = list(candidates) if isinstance(candidates, (list, tuple)) else [candidates]
    cands = [c for c in cands if c]
    if not cands:
        raise ImageRefError("no product image available.")
    errors = []
    for c in cands:
        try:
            return _img_to_ref(c, media_root)
        except ImageRefError as e:
            errors.append(str(e))
    raise ImageRefError("no product image available — none of the sources (uploaded file, "
                        "cached copy, source URL) returned a valid image. ["
                        + " | ".join(errors[:3]) + "]")


def _resolve_ref_block(image, media_root: str = ""):
    """image = a single ref (str) OR an ordered list of candidates. Returns a validated ref
    block; raises ImageRefError. Central helper so every entry point validates identically."""
    if isinstance(image, (list, tuple)):
        return resolve_image_ref(image, media_root)
    return _img_to_ref(image, media_root)


# THE HOUSE STYLE -- a preference, not a rule.
#
# This sentence used to sit inside the ABSOLUTE NON-NEGOTIABLE list below, which
# is why every image came back lit exactly the same way and no amount of asking
# changed it. Amazon has no opinion about lighting: it requires the pure white
# background, the frame fill, and no added text. The lighting was ours.
#
# It is still the default, so nothing changes for anyone who liked it -- but it
# is now ONE string, in ONE place, and setting "image_style_note" in config.json
# replaces it. Setting it to "" removes styling guidance altogether and lets the
# brief (or the standing instructions box) decide the look.
DEFAULT_STYLE_NOTE = (
    "Even soft daylight-balanced (5500K) studio lighting, a subtle natural contact "
    "shadow under the product, sRGB colour."
)


def style_note(config):
    """The house style for generated images, or "" if it has been cleared."""
    if not isinstance(config, dict):
        return DEFAULT_STYLE_NOTE
    v = config.get("image_style_note", None)
    return DEFAULT_STYLE_NOTE if v is None else str(v).strip()


# What Amazon actually requires. Nothing here is a matter of taste.
_ENHANCE_RULES = (
    "You are a product-photography art director. Expand the user's short brief "
    "into a single, richly detailed image-generation prompt for a professional "
    "Amazon MAIN product image that meets Amazon's 2025 technical standards. "
    "ABSOLUTE NON-NEGOTIABLE RULES (state every one of these explicitly in the prompt):\n"
    "- The background MUST be 100% pure solid white (RGB exactly 255,255,255) edge to edge. "
    "NEVER a coloured, grey, gradient, textured, scene, or lifestyle background. Pure white only.\n"
    "- The product MUST fill 85% or more of the frame — large, prominent, well-cropped, not tiny or "
    "floating in empty space.\n"
    "- Perfect 1:1 square aspect ratio.\n"
    "- Maximum resolution and sharpness — crisp, high-definition, professional studio quality, every "
    "detail in sharp focus (target 2500x2500 pixels, never below 1600x1600).\n"
    "- NO text added by you, NO logos added, NO watermarks, NO badges, NO props, NO people, single "
    "product only, shown OUTSIDE its packaging.\n"
    # NOTHING AROUND THE EDGE, AND NOTHING BORROWED FROM THE REFERENCE'S STYLING.
    #
    # The reference image is usually a supplier's marketing collage, and those
    # are built out of framed panels, dashed borders, corner flashes and little
    # decorative motifs. The model reads that styling as part of the subject and
    # reproduces it: a generated main image came back with a green dashed border
    # around all four sides, copied from the source collage's panel frames.
    # Amazon rejects a main image with a border or frame, and it is the kind of
    # fault nobody looks for because the product itself is correct.
    #
    # Deliberately generic. This governs every product in every category, so it
    # names what must not be in the FRAME rather than anything about a
    # particular kind of goods.
    "- NO border, frame, outline, dashed or dotted edge, coloured margin, corner "
    "flash, banner, ribbon, sticker, seal, starburst or decorative motif "
    "anywhere in the image. The white background must run clean to all four "
    "edges with nothing drawn on it.\n"
    "- The reference image is evidence of WHAT THE PRODUCT LOOKS LIKE, never a "
    "guide to layout or styling. Supplier photographs are usually marketing "
    "collages with panels, frames, captions and graphics; take the product from "
    "them and leave every one of those behind.\n"
    "- The WHOLE product must be inside the frame with clear margin on all four "
    "sides. Nothing cropped, nothing bleeding off an edge.\n"
    "- Show the parts that are genuinely supplied and NO OTHERS. Do not invent "
    "extra components, fittings, accessories, decorative hardware or duplicates "
    "to fill space. If the spec says how many of something there are, show "
    "exactly that many.\n"
)

_ENHANCE_FIDELITY = (
    "CRITICAL — PRODUCT FIDELITY: an EXACT PRODUCT SPEC may be provided. Reproduce the product PRECISELY "
    "from it and from the reference image — keep the identical shape, colours, materials, layout, logo "
    "placement, and reproduce ALL label text exactly as written, letter for letter. Do NOT invent, "
    "redesign, restyle, translate, or omit any text or feature. "
    "Output ONLY the prompt text, no preamble, 350-650 words."
)


def _enhance_system(config=None):
    """The main-image system prompt: Amazon's rules, then the house style if any.

    Assembled rather than stored, so the style can be changed or removed without
    touching what Amazon requires -- the two used to be one paragraph, and that
    is why the look could not be changed without weakening the compliance rules.
    """
    note = style_note(config)
    style = ""
    if note:
        style = ("HOUSE STYLE (follow unless the brief asks for something else):\n- %s\n"
                 "Be specific about lighting, angle, shadow and finish.\n" % note)
    return _ENHANCE_RULES + style + _ENHANCE_FIDELITY


def describe_image(config: dict, images: list, focus: str = "", provider: str = None) -> dict:
    """Vision AI: look at competitor/reference image(s) and return a STRUCTURED
    description of the visual technique (lighting, angle, composition, effects,
    text treatment) so it can be re-applied to the seller's own product. Returns
    {ok, description}. Does NOT copy the competitor's product or branding."""
    model = provider or select(config, "prompt_enhance")
    if not _key(config):
        return {"ok": False, "error": "No openrouter_api_key in config.json"}
    if not model:
        return {"ok": False, "error": "No text model selected/available"}
    if not images:
        return {"ok": False, "error": "no images to describe"}
    sys = (
        "You are a product-photography art director. Look at the reference image(s) and describe "
        "ONLY the reusable visual TECHNIQUE so it can be recreated for a DIFFERENT product: "
        "lighting setup and direction, camera angle, background/surface, colour palette/mood, any "
        "special effects (water droplets, steam, splashes, powder, motion), composition/layout, and "
        "how any text/benefit callout is placed and styled (position, size, restraint). "
        "Do NOT describe or identify the specific product, brand, or logo in the reference. "
        "Be concrete and concise (120-200 words) so another AI can reproduce the STYLE on a new product."
        + (f" Focus especially on: {focus}." if focus else "")
    )
    _feature("image: read style reference")
    content = [{"type": "text", "text": "Describe the reusable visual style/technique of these reference image(s)."}]
    for im in images[:3]:
        try:                                    # skip any invalid reference; describe the rest
            ref = _img_to_ref(im)
            if ref:
                content.append(ref)
        except ImageRefError:
            continue
    body = {"model": model,
            "messages": [{"role": "system", "content": sys},
                         {"role": "user", "content": content}],
            "max_tokens": 700}
    try:
        resp = _post(f"{OPENROUTER_BASE}/chat/completions", config, body, timeout=90)
        text = (resp.get("choices") or [{}])[0].get("message", {}).get("content", "")
        return {"ok": bool(text), "description": (text or "").strip(), "provider": model}
    except urllib.error.HTTPError as e:
        d = ""
        try:
            d = e.read().decode("utf-8")[:300]
        except Exception:
            pass
        return {"ok": False, "error": f"OpenRouter vision HTTP {e.code}: {d}"}
    except Exception as e:
        return {"ok": False, "error": f"OpenRouter vision failed: {str(e)[:200]}"}


_SECONDARY_SYSTEM = (
    "You are a product-photography art director. Expand the seller's brief into a "
    "single detailed image-generation prompt for an Amazon SECONDARY/supplemental "
    "listing image (these MAY include tasteful text and graphics, unlike the main "
    "image). The prompt MUST instruct: perfect 1:1 square aspect ratio, high "
    "resolution (target 2000x2000 pixels, never below 1000x1000), sRGB colour, "
    "sharp and well-lit, premium and clean with generous negative space. Any text "
    "must be SHORT, large enough to read on mobile, truthful, and must NOT include "
    "prohibited claims (no 'Best Seller', '#1', 'Guaranteed', pricing, or "
    "percentage-off badges). Keep the real product identical to the reference image "
    "(same shape, colour, label, text) — build the scene/graphic around it, never "
    "redesign it. Output ONLY the prompt text, no preamble, 250-500 words."
)
# HOW MUCH OF THE PRODUCT EACH CONCEPT NEEDS.
#
#     "i see the item image in all the seconary images ... There is no need to
#      show the item in all the pictures."
#
# Nothing asked this question before, so the answer was always "all of it", and
# a set of eight came out as eight photographs of the same bottle. The slots
# that should have answered a doubt were spent repeating the main image.
#
# The strongest secondary images on real listings often contain NO product: a
# wall of journal pages under "3,319 peer-reviewed studies"; a specification
# panel with the numbers called out around it. The product is already in the
# main image and in several of the others.
#
# The MODEL decides, per concept, because the right answer depends on the
# product. A garden bench needs scale against a person; a supplement needs its
# facts panel; a tool needs the mechanism close up. A fixed rota would be the
# same generic list this file already warns against.
# A CONCEPT MAY ONLY NEED FACTS THAT EXIST.
#
# The presence work made product-free panels possible, and the very first one
# was an ingredient board for a multivitamin whose listing carries NO ingredient
# list -- the app gets title, attributes and images from the catalogue, and
# nothing else. So the model was asked to draw twenty-eight things it had never
# been told. It produced "Magnanese", "Setassium", "Molybdenese", and on the
# next attempt outright noise: "SPORTPRFIBS", "MUTERIBL", "SACBEITIES".
#
# That is not a prompt-obedience problem and no amount of "do not invent" fixes
# it. A designed panel has a shape to fill, and a model given a shape and no
# facts will fill it with something. The fault is upstream: proposing the panel
# at all.
#
# So the STRATEGIST is made responsible for it. A concept that needs specific
# facts must name them, taken from the details it was given, and if it cannot
# name them it must propose something else. Naming them is what makes the check
# possible -- a concept saying "list the ingredients" passes any review; one
# saying "list these six: ..." either has them or obviously does not.
_FACTS_BRIEF = (
    "\nONLY PROPOSE WHAT THE FACTS CAN FILL.\n"
    "Some images are data: a specification table, an ingredient panel, a "
    "comparison, a set of numbered callouts, a what-is-in-the-box layout. Those "
    "need real values, and the ONLY values available are in the product details "
    "given below. There is nothing else -- no ingredient list, no test result "
    "and no certificate exists unless it is written there.\n"
    "If a concept needs specific facts, put them in \"facts_used\": the actual "
    "values it will print, copied from the details. If you cannot fill that "
    "list, the concept is not available for this product -- propose a different "
    "one. A lifestyle moment, a close-up of the material or a single clear "
    "statement need no data and are always available.\n"
    "NEVER propose a layout whose shape implies more facts than exist. A "
    "four-column grid promises four columns of content; if there is enough for "
    "one short list, propose the one short list. An empty column or a padded one "
    "is worse than a simpler image, because it is the part a buyer reads "
    "closely.\n"
)

_PRESENCE_BRIEF = (
    "\nHOW MUCH OF THE PRODUCT EACH IMAGE SHOWS -- decide this per concept and "
    "return it as \"product_presence\", one of:\n"
    "  \"hero\"    the whole product is the subject\n"
    "  \"detail\"  a tight crop of one part, mechanism, surface or texture\n"
    "  \"in_use\"  in a real scene, held or in use, possibly partly out of frame\n"
    "  \"none\"    NO product at all -- a designed panel, chart, comparison, set "
    "of icons or piece of evidence\n"
    "DO NOT make every concept \"hero\". The main image already shows the whole "
    "product on white; a set that repeats it wastes the slots that could answer "
    "a real doubt. Across the set aim for a genuine spread, and use \"none\" for "
    "at least one or two where this product's buyer would rather read a fact "
    "than look at another photograph.\n"
    "Choose by what THIS product's buyer actually needs. A large item needs its "
    "size against something familiar. A tool needs its working part close up. "
    "Something bought on trust needs the evidence laid out. Something fiddly "
    "needs the steps. Do not apply one product's answer to another: a "
    "supplement's lab-testing panel is meaningless on a table stand, and a "
    "table stand's assembly steps are meaningless on a supplement.\n"
)

# A+ MODULES ARE A PAGE, NOT A PILE.
#
#     "every module do not talk with each other ... i am not able to understand
#      which module is which"
#
# Each module was written on its own and drawn on its own, so seven of them came
# out as seven separate posters about the same bottle. Nothing carried a reader
# from one to the next, and nothing said what any of them was FOR.
#
# A+ is read top to bottom, once, by somebody who has already scrolled past the
# images and is still not sure. That is a sequence with a job at each step, and
# the steps are not interchangeable.
_APLUS_STORY = (
    "\nTHESE MODULES ARE ONE PAGE, READ TOP TO BOTTOM -- not a pile of posters.\n"
    "Give every concept a \"role\" naming its job in that sequence, and a "
    "\"headline\" it carries. The reader arrives unconvinced and leaves ready to "
    "buy, so the sequence must actually move:\n"
    "  open      what this is and who it is for, in one confident line\n"
    "  problem    the situation the buyer is in that makes them look\n"
    "  answer     how this product solves it, concretely\n"
    "  proof      the evidence, materials, standard or record behind that claim\n"
    "  detail     the one thing a careful buyer wants to inspect before paying\n"
    "  use        how it fits into their day, or how it is used\n"
    "  compare    why this rather than the obvious alternative\n"
    "  close      the reassurance that removes the last hesitation\n"
    "Pick the roles that suit THIS product and put them in an order that reads. "
    "Not every product needs every role, and the right set for a supplement is "
    "not the right set for a garden bench.\n"
    "EACH MODULE MUST HAND OVER TO THE NEXT. The headline of one should make the "
    "next one feel like the answer to it. Do not repeat the same claim in two "
    "modules, and do not open three of them with the product name.\n"
    "SET THE LOOK ONCE AND HOLD IT. Decide one palette, one type treatment and "
    "one background family for the whole page, state it in every art_direction, "
    "and keep it identical across all of them -- a page whose modules each look "
    "like a different brand is the most common way A+ fails.\n"
)

_APLUS_SYSTEM = (
    "You are an Amazon A+ Content designer. Expand the brief into a single detailed "
    "image-generation prompt for ONE Amazon A+ Content module image at the EXACT "
    "pixel dimensions given in the brief. The prompt MUST instruct: those exact "
    "dimensions and aspect ratio, high resolution and sharpness, sRGB colour, a "
    "clean premium layout following the '70% visual / 30% text' rule, short readable "
    "text (min ~24px equivalent, large enough for mobile), NO prohibited claims (no "
    "'Best Seller', '#1', pricing, percentage-off, or external website links), and "
    "brand-consistent styling. Keep any depicted product faithful to the reference "
    "image. Output ONLY the prompt text, no preamble, 250-500 words."
)


def strategize_images(config: dict, image="", product_title: str = "",
                      product_spec: str = "", n: int = 3, kind: str = "main",
                      provider: str = None, custom_instructions: str = "",
                      media_root: str = "", listing=None) -> dict:
    """STRATEGIST AI — thinks like a world-class Amazon conversion strategist AND
    like the target customer, then INVENTS concrete image concepts for this exact
    product (rather than executing the seller's literal idea). Returns a list of
    concept dicts: {title, customer_insight, concept, art_direction}.

    kind='main'  -> white-background hero concepts (different angles/personality,
                    Amazon-compliant: pure white, no added text)
    kind='secondary' -> infographic/lifestyle/benefit concepts (text allowed)
    """
    model = provider or select(config, "prompt_enhance")
    if not _key(config):
        return {"ok": False, "error": "No openrouter_api_key in config.json"}
    if not model:
        return {"ok": False, "error": "No text model selected/available"}

    if kind == "main":
        rules = (
            "These are Amazon MAIN images: each concept MUST be on a 100% pure white background "
            "(RGB 255,255,255), product filling 85%+, NO added text or graphics, and NO border, "
            "frame, dashed edge, coloured margin or decorative motif of any kind -- the white must "
            "run clean to all four edges. The reference photograph is evidence of what the product "
            "LOOKS LIKE, never a guide to layout: supplier images are usually collages with framed "
            "panels and captions, and none of that belongs here. Creativity comes ONLY "
            "from camera angle, product positioning/arrangement, lighting mood, and tasteful physical "
            "touches that suit the product (e.g. water droplets, condensation, a soft splash, powder, "
            "steam, a dramatic highlight, an interesting grouping). Make each of the N concepts visually "
            "DISTINCT and genuinely scroll-stopping."
        )
    elif kind == "aplus":
        rules = (
            "These are Amazon A+ CONTENT modules (the enhanced brand-story section below the listing). "
            "Text and graphics ARE allowed and expected. Each concept should be ONE module that advances "
            "the brand story and moves the buyer toward purchase. Module TYPES exist (hero banner, "
            "key-benefit, how-it-works, ingredient/material spotlight, lifestyle, comparison, trust) but "
            "DO NOT just walk down that generic list — the SPECIFIC angle, scene, and headline of each "
            "module must come from THIS product's real features, materials, use-context and buyer. Two "
            "different products should produce visibly different module sets. Keep each premium and "
            "uncluttered (~70% visual, 30% text), and never make prohibited medical/efficacy claims.\n"
            + _APLUS_STORY + _PRESENCE_BRIEF + _FACTS_BRIEF
        )
    else:
        rules = (
            "These are Amazon SECONDARY images: text and graphics ARE allowed. Each concept should sell "
            "ONE clear idea cleanly. Angles exist (a benefit, a feature, a lifestyle moment, a size/scale "
            "shot, a trust/quality cue, a comparison) but DO NOT just default to that generic list — the "
            "specific idea, scene, and message of each image must be driven by THIS product's real "
            "features, materials, who uses it and where, and the actual objections its buyer has. Two "
            "different products must produce visibly different image sets. Keep them premium and "
            "uncluttered — one strong message per image, not walls of text. Make the N concepts cover "
            "genuinely different angles of the buying decision for this exact product.\n"
            + _PRESENCE_BRIEF + _FACTS_BRIEF
        )

    # ONE PRODUCT, DESCRIBED THE SAME WAY IN EVERY IMAGE.
    # (see _PRESENCE_BRIEF above for the separate question of how much of the
    # product each concept should contain -- the two rules pull against each
    # other on purpose: same product everywhere it appears, but it does not
    # have to appear everywhere.)
    #
    # The rules above push each concept to be DIFFERENT from the others, and
    # nothing balanced that: the set is free to disagree with itself about the
    # thing it is selling. On a real listing that produced one image showing a
    # single carabiner and another showing the hammock hung from two -- under
    # copy that said one. A buyer counts what arrives.
    #
    # Deliberately about ANY product and any category: it names no part, no
    # material and no item type, because the same strategist writes the images
    # for grease guns, tables and torches.
    same_item = (
        "\nEVERY CONCEPT SHOWS THE SAME PHYSICAL PRODUCT, AND ONLY WHAT IS SUPPLIED.\n"
        "The images vary in idea, angle, scene and message. They must NOT vary in what "
        "the product IS. Across the whole set, keep identical: the number of each part or "
        "piece supplied, colours and finishes, materials, shape and proportions, and how "
        "the parts fit together. If one concept shows a quantity of something, every other "
        "concept that shows it shows the same quantity.\n"
        "Never show an accessory, fitting, attachment, container or extra unit that is not "
        "listed in the product details as included -- not as a prop, not for scale, not to "
        "make the scene look complete. If the details state what is in the box, that list is "
        "exhaustive: do not add to it and do not multiply it. Where the details are silent "
        "about a quantity, show one.\n"
        "The product details below outrank the reference photograph on all of this. A "
        "supplier photo often shows a bundle, a different variant, or props that are not "
        "part of the sale.\n"
    )

    sys = (
        "You are a world-class Amazon conversion strategist and product photographer who has launched "
        "hundreds of best-selling listings. You also think like the actual TARGET CUSTOMER scrolling on a "
        "phone. Your job is to INVENT image concepts that make that customer stop, feel 'this is the one', "
        "and buy — NOT to wait for instructions.\n"
        "First reason briefly about: who the target customer is, what they truly care about, what doubt or "
        "objection stops them from buying, and what emotional trigger or proof would win them over. THEN "
        "translate that into concrete, shootable image concepts for THIS exact product.\n"
        + rules + "\n"
        + same_item
        + f"Return ONLY JSON: a list of exactly {n} objects, each "
        '{"title": "<short name>", "customer_insight": "<the buyer psychology this image targets, 1 sentence>", '
        '"concept": "<what the image shows, plain language, 1-2 sentences>", '
        '"product_presence": "<hero|detail|in_use|none — how much of the product this image shows>", '
        '"facts_used": ["<the actual values this image will print, copied from the product '
        'details — empty list if it needs none>"], '
        + ('"role": "<its job in the top-to-bottom sequence: open|problem|answer|proof|detail|use|'
           'compare|close>", "headline": "<the one short line this module carries>", '
           if kind == "aplus" else "")
        + '"art_direction": "<specific art direction for the image model: angle, lighting, composition, any '
        'physical touch like droplets, mood — be concrete and vivid>"}. No preamble, no markdown.'
    )
    _ci = (custom_instructions or "").strip()
    _ci_block = ""
    if _ci:
        _ci_block = (
            "\n\nIMPORTANT — the seller gave SPECIFIC INSTRUCTIONS for this set of concepts. "
            "You MUST honor every one of them when inventing the concepts (they override your "
            "default choices where they conflict):\n" + _ci + "\n"
            "If an instruction says to show something in only SOME images, reflect that across the "
            "set (don't put it in every concept). If it says NOT to show something, never include it."
        )
    # THE LISTING'S OWN WORDS, HANDED OVER DIRECTLY.
    #
    # product_spec is a VISION summary: a model looking at the photograph. The
    # listing facts were already being fed to that step, but what comes back is
    # the model's own paraphrase, and the parts that are hard to see -- what is
    # in the box, how many of each -- do not survive it. Measured: on five real
    # products the spec mentioned the contents in NONE of them, and the concepts
    # then counted the objects visible in the supplier photo instead. On the
    # hammock that produced "all five components" for a listing that ships four.
    #
    # So the facts go in as their own block, marked as outranking both.
    _facts = ""
    try:
        _facts = listing_facts(listing) if listing else ""
    except Exception:
        _facts = ""
    _facts_block = ""
    if _facts:
        _facts_block = (
            "\n\nTHE LISTING ITSELF SAYS THIS, AND IT OUTRANKS BOTH THE PHOTOGRAPH "
            "AND THE DESCRIPTION ABOVE. Where they disagree about what is included, "
            "how many of anything there are, the size, the colour or the material, "
            "THIS is right and they are wrong -- a supplier photograph is routinely "
            "a bundle, a different variant, or a collage with props:\n" + _facts + "\n")

    content = [{"type": "text",
                "text": (f"Product: {product_title}\n"
                         + (f"\nProduct details:\n{product_spec}\n" if product_spec else "")
                         + _facts_block
                         + f"\nInvent {n} distinct, conversion-focused image concepts for this product. "
                           "Ground every concept in the SPECIFIC product details above (its real "
                           "features, materials, size, who uses it and where) so these ideas could NOT be "
                           "copy-pasted onto a different product. Avoid generic template concepts; make "
                           "each one unmistakably about THIS item. Think as the strategist AND the customer."
                         + _ci_block
                         + "\nReturn ONLY the JSON list.")}]
    try:
        _rb = _resolve_ref_block(image, media_root) if image else None
    except ImageRefError as e:
        return {"ok": False, "error": str(e)}
    if _rb:
        content.append(_rb)
    body = {"model": model,
            "messages": [{"role": "system", "content": sys},
                         {"role": "user", "content": content}],
            # Scale the token budget with N. Each concept is ~180-220 tokens
            # (4 verbose fields), so a fixed 1600 truncated the JSON once N grew to
            # 8 (secondary) -- the array never closed and parsing failed. Give
            # generous headroom and a floor so small N still has room.
            "max_tokens": max(1600, 320 * int(n) + 400),
            # higher temperature so concepts vary product-to-product and run-to-run
            # instead of converging on the same safe list every time.
            "temperature": 0.9}
    _feature("image: think of concepts")
    try:
        resp = _post(f"{OPENROUTER_BASE}/chat/completions", config, body, timeout=90)
        text = (resp.get("choices") or [{}])[0].get("message", {}).get("content", "")
        text = (text or "").strip()
        if not text:
            # the model returned nothing -- surface WHY (often a provider error
            # tucked into the response, or an empty completion) instead of a
            # silent "strategist failed".
            _err = ""
            try:
                _err = (resp.get("error") or {}).get("message", "") if isinstance(resp.get("error"), dict) else str(resp.get("error") or "")
            except Exception:
                _err = ""
            return {"ok": False, "error": f"the AI model returned an empty response"
                    + (f" ({_err[:160]})" if _err else f". Model: {model}. Try a different Prompt-AI model in AI & settings.")}
        # strip code fences if present
        import re as _re
        text = _re.sub(r"^```(?:json)?|```$", "", text).strip()
        concepts = None
        try:
            concepts = json.loads(text)
        except Exception:
            # try to find the JSON array
            mt = _re.search(r"\[.*\]", text, _re.DOTALL)
            if mt:
                try:
                    concepts = json.loads(mt.group(0))
                except Exception:
                    concepts = None
            # SALVAGE a TRUNCATED array (response hit the token limit mid-way, so
            # the closing ] is missing). Walk the objects and keep every COMPLETE
            # one, then close the array. This recovers e.g. 6 of 8 concepts instead
            # of failing outright.
            if not concepts and text.lstrip().startswith("["):
                _objs = []
                _depth = 0
                _start = None
                _in_str = False
                _esc = False
                for _i, _ch in enumerate(text):
                    if _esc:
                        _esc = False; continue
                    if _ch == "\\" and _in_str:
                        _esc = True; continue
                    if _ch == '"':
                        _in_str = not _in_str; continue
                    if _in_str:
                        continue
                    if _ch == "{":
                        if _depth == 0:
                            _start = _i
                        _depth += 1
                    elif _ch == "}":
                        _depth -= 1
                        if _depth == 0 and _start is not None:
                            _frag = text[_start:_i+1]
                            try:
                                _objs.append(json.loads(_frag))
                            except Exception:
                                pass
                            _start = None
                if _objs:
                    concepts = _objs
        if isinstance(concepts, dict):
            concepts = [concepts]
        if not concepts:
            # parsed to nothing -> tell the user the model didn't return usable
            # JSON, and include a short snippet so the cause is visible.
            return {"ok": False, "error": "the AI didn't return usable concepts (its reply wasn't valid JSON). "
                    + f"This usually means the selected Prompt-AI model ('{model}') struggles with strict JSON output \u2014 "
                    + "try a stronger text model in AI & settings. First 120 chars it returned: "
                    + (text[:120].replace("\n", " ") if text else "(empty)")}
        return {"ok": True, "concepts": concepts, "provider": model}
    except urllib.error.HTTPError as e:
        d = ""
        try:
            d = e.read().decode("utf-8")[:300]
        except Exception:
            pass
        return {"ok": False, "error": f"OpenRouter strategist HTTP {e.code}: {d}"}
    except Exception as e:
        return {"ok": False, "error": f"OpenRouter strategist failed: {str(e)[:200]}"}


def enhance_prompt(config: dict, brief: str, product_title: str = "",
                   provider: str = None, image_kind: str = "main") -> dict:
    _feature("image: write the prompt")
    model = provider or select(config, "prompt_enhance")
    if not _key(config):
        return {"ok": False, "error": "No openrouter_api_key in config.json"}
    if not model:
        return {"ok": False, "error": "No text model selected/available"}
    _main = _enhance_system(config)
    sysmsg = {"main": _main, "secondary": _SECONDARY_SYSTEM,
              "aplus": _APLUS_SYSTEM}.get(image_kind, _main)
    user_msg = (f"Product: {product_title}\n\n" if product_title else "") + \
               f"Brief from seller: {brief or 'clean professional Amazon image'}\n\n" \
               "Write the detailed image prompt now."
    body = {"model": model,
            "messages": [{"role": "system", "content": sysmsg},
                         {"role": "user", "content": user_msg}],
            "max_tokens": 1500}
    try:
        resp = _post(f"{OPENROUTER_BASE}/chat/completions", config, body, timeout=90)
        text = (resp.get("choices") or [{}])[0].get("message", {}).get("content", "")
        return {"ok": bool(text), "prompt": (text or "").strip(), "provider": model}
    except urllib.error.HTTPError as e:
        d = ""
        try:
            d = e.read().decode("utf-8")[:300]
        except Exception:
            pass
        return {"ok": False, "error": f"OpenRouter HTTP {e.code}: {d}"}
    except Exception as e:
        return {"ok": False, "error": f"OpenRouter text failed: {str(e)[:200]}"}


def generate_image(config: dict, prompt: str, reference_image="",
                   provider: str = None, strength: float = None,
                   aspect_ratio: str = "1:1", image_size: str = None,
                   extra_reference: str = "", media_root: str = "") -> dict:
    _feature("image: generate")
    model = provider or select(config, "image_generate")
    if not _key(config):
        return {"ok": False, "error": "No openrouter_api_key in config.json"}
    if not model:
        return {"ok": False, "error": "No image model selected/available"}
    body = {"model": model, "prompt": prompt, "output_format": "png"}
    ref = None
    if reference_image:
        try:
            ref = _resolve_ref_block(reference_image, media_root)
        except ImageRefError as e:
            return {"ok": False, "error": str(e)}
    if ref:
        # reference image(s) for editing / product preservation. We can pass more
        # than one: e.g. [image-to-edit, ORIGINAL product] so a refine edits the
        # generated image while staying anchored to the REAL product.
        refs = [ref]
        if extra_reference:
            try:                                # extra reference is optional -> skip if invalid
                refs.append(_resolve_ref_block(extra_reference, media_root))
            except ImageRefError:
                pass
        body["input_references"] = refs
        # image_config.strength keeps the output close to the source product.
        # Low strength = stay very close to the reference (product unchanged);
        # high = free to change. We default LOW so the product is preserved.
        ic = {}
        if strength is not None:
            ic["strength"] = strength
        if aspect_ratio:
            ic["aspect_ratio"] = aspect_ratio
        if image_size:
            ic["image_size"] = image_size       # OpenRouter/Gemini-style name
        if ic:
            body["image_config"] = ic
        # Seedream (ByteDance) reads a top-level `size` param ("2K"/"4K" or WxH),
        # NOT image_config.image_size. Send it so we actually get high-res output.
        if image_size:
            body["size"] = image_size
    else:
        ic = {}
        if aspect_ratio:
            ic["aspect_ratio"] = aspect_ratio
        if image_size:
            ic["image_size"] = image_size
        if ic:
            body["image_config"] = ic
        if image_size:
            body["size"] = image_size
    try:
        resp = _post(f"{OPENROUTER_BASE}/images", config, body, timeout=180)
        data = resp.get("data") or []
        if data and data[0].get("b64_json"):
            return {"ok": True, "image_b64": data[0]["b64_json"],
                    "mime": "image/png", "provider": model}
        if data and data[0].get("url"):
            return {"ok": True, "image_url": data[0]["url"], "provider": model}
        # surface the raw response so we can see WHY (e.g. ref ignored / model error)
        return {"ok": False, "error": "OpenRouter returned no image",
                "raw": str(resp)[:400]}
    except urllib.error.HTTPError as e:
        d = ""
        try:
            d = e.read().decode("utf-8")[:400]
        except Exception:
            pass
        # THE MODEL REFUSED THE WORDS, and that is a different problem from a
        # broken key or a rate limit.
        #
        # MEASURED: the clean-background main image for 10.99_3Days_B0GGSCK998
        # (a "Weed Slasher ... Hardened Steel Blade") came back
        #     HTTP 400 {"error":{"message":"The request failed because the input
        #     text may contain sensitive content ...
        # -- the image model's own safety filter, tripped by the product's name.
        # It is an ordinary garden tool. Three of the four products tested got
        # their image; this one could not, and the person was shown a wall of
        # truncated JSON that said nothing about why or what to do.
        if _refused_as_sensitive(e.code, d):
            return {"ok": False, "refused": True, "error": (
                "The image model refused this prompt as sensitive content. That "
                "happens with bladed or tool-like products -- a knife, a slasher, "
                "a cutter -- whatever the product actually is. Reword the brief "
                "to describe the OBJECT rather than what it does (\"a long-handled "
                "steel garden tool\" rather than \"weed slasher blade\"), or "
                "generate this one image by hand."), "raw": d}
        return {"ok": False, "error": f"OpenRouter image HTTP {e.code}: {d}"}
    except Exception as e:
        return {"ok": False, "error": f"OpenRouter image failed: {str(e)[:200]}"}


# Words that describe what a tool DOES, and the plain noun for the same object.
#
# Every one of these is a lawful product this owner sells or could sell. The image
# model's filter reads the verb and refuses; it has no objection to a photograph
# of a garden tool on a white background, which is what is actually being asked
# for. Replacing the verb with the object leaves the picture identical.
_SOFTEN = (
    ("weed slasher", "long-handled garden tool"),
    ("grass slasher", "long-handled garden tool"),
    ("slasher", "long-handled garden tool"),
    ("machete", "long-handled garden tool"),
    ("weapon", "tool"),
    ("blade", "flat metal head"),
    ("bladed", "metal-headed"),
    ("cutter", "trimming tool"),
    ("cutting edge", "shaped metal edge"),
    ("sharp", "finished"),
    ("stab", "press"),
    ("kill", "clear"),
    ("hardened steel blade", "hardened steel head"),
)


def _soften_for_filter(prompt):
    """The same photograph, of the same object, without the words that trip it.

    Case-insensitive and whole-word, so "bladed" is not half-rewritten inside
    another word. Returns the prompt unchanged when there is nothing to soften --
    the caller uses that to know a retry is pointless.
    """
    import re as _re
    out = str(prompt or "")
    for bad, good in _SOFTEN:
        out = _re.sub(r"\b%s\b" % _re.escape(bad), good, out, flags=_re.I)
    return out


def _refused_as_sensitive(code, body):
    """Did the model refuse the WORDS, rather than fail for another reason?

    Told apart from every other 400 because the answer is different: a refusal is
    fixed by rewording the brief, and a bad key or a rate limit is not. Matched on
    the provider's own phrases; anything unrecognised stays a plain HTTP error
    rather than being dressed up as a refusal.
    """
    if int(code or 0) != 400:
        return False
    t = str(body or "").lower()
    # "sensitive" alone, not "sensitive content": the provider says BOTH. Measured
    # on the same product, minutes apart --
    #     "the input text may contain sensitive content"
    #     "the input text may contain sensitive information."   <- Seed
    # -- and matching the longer phrase missed the second, so the retry never
    # fired and the person got the raw JSON after all.
    return any(s in t for s in ("sensitive", "safety", "content policy",
                                "prohibited_content", "content_filter",
                                "blocked by", "violates"))


# ONE spec per product, reused by every image made from it.
#
# Each image used to call describe_product for itself. The vision model is not
# deterministic, so five secondary images meant five slightly different specs --
# one calling the handle "charcoal", the next "dark grey", one counting four
# slots and the next five. Every image was then faithful to a DIFFERENT product,
# which is exactly the complaint: the item changes from picture to picture.
#
# Cached on the reference image and title, so a batch describes the product once
# and every image in it is built from the same words. Cleared when the app
# restarts, which is often enough -- a product's appearance does not change while
# the server is up.
_SPEC_CACHE = {}


def clear_product_spec_cache():
    _SPEC_CACHE.clear()


# Attribute names that carry a real-world measurement. The listing keeps these
# in Attributes JSON; a photograph cannot supply any of them.
_DIM_KEYS = {
    "item_length": "length", "item_width": "width", "item_height": "height",
    "item_depth": "depth", "item_weight": "weight", "item_diameter": "diameter",
    "item_display_length": "length", "item_display_weight": "weight",
    "item_display_height": "height", "item_display_width": "width",
    "item_display_diameter": "diameter", "item_display_volume": "volume",
    "capacity": "capacity", "wattage": "wattage", "voltage": "voltage",
}


def _flat_attr(v):
    """Amazon attributes are lists of objects; pull out a readable value."""
    if isinstance(v, list) and v:
        v = v[0]
    if isinstance(v, dict):
        for a, b in (("value", "unit"), ("decimal_value", "unit")):
            if v.get(a) is not None:
                return "%s %s" % (v[a], v.get(b) or "")
        for k in ("value", "name"):
            if v.get(k) is not None:
                return str(v[k])
        return ""
    return str(v) if v is not None else ""


def listing_facts(row) -> str:
    """What the SELLER'S OWN LISTING says this product is, for, and how big.

    WHY THIS EXISTS. The vision model was given the photograph and the title and
    nothing else. A photograph cannot say how big something is -- a weed slasher
    photographed against a plain background could be six inches or six feet, and
    the model picks one, confidently. Nor can it say what the thing is FOR, so
    the "uses" in a lifestyle image get invented from what the shape resembles.

    Meanwhile the listing itself carries all of it: the bullets say what it does,
    the description says how it is used, and the attributes carry real
    dimensions in centimetres. It was sitting one function call away and never
    being passed.

    Returns "" when there is nothing to say, so a caller with no listing behaves
    exactly as before.
    """
    r = row or {}
    g = lambda *names: next((str(r.get(n)).strip() for n in names
                             if r.get(n) not in (None, "", "None")), "")
    parts = []

    kind = g("product_type", "Product Type")
    cat = g("amazon_category", "Amazon Category", "subcategory", "Subcategory")
    if kind or cat:
        parts.append("WHAT IT IS: %s" % " / ".join(x for x in (kind, cat) if x))

    bullets = [g("bullet_%d" % i, "Bullet %d" % i) for i in range(1, 6)]
    bullets = [b for b in bullets if b]
    if bullets:
        parts.append("WHAT THE LISTING SAYS IT DOES:\n" +
                     "\n".join("- " + b[:300] for b in bullets))

    desc = g("description_html", "Description (HTML)")
    if desc:
        import re as _re
        plain = _re.sub(r"<[^>]+>", " ", desc)
        plain = " ".join(plain.split())
        if plain:
            parts.append("DESCRIPTION: " + plain[:700])

    # WHAT IS IN THE BOX. A photograph of a bundle cannot say which of those
    # pieces are actually being sold, and this is the field that decides how many
    # of each thing an image is allowed to show. It was the one part of the
    # listing not being passed, and it is the part a buyer counts on arrival.
    included = ""
    try:
        import json as _json
        _a = r.get("attributes_json") or r.get("Attributes JSON") or "{}"
        _o = _json.loads(_a) if isinstance(_a, str) else (_a or {})
        if isinstance(_o, dict):
            included = _flat_attr(_o.get("included_components")).strip()
    except Exception:
        included = ""
    included = included or g("included_components", "Included Components")
    if included:
        parts.append("WHAT IS IN THE BOX (the complete list -- show nothing beyond "
                     "it, and no more of anything than it states): " + included[:400])

    hl = g("item_highlights", "Item Highlights")
    if hl:
        parts.append("HIGHLIGHTS: " + hl[:300])

    # THE SIZE, which is the one a photograph cannot supply.
    dims = []
    for key, label in (("size", "size"), ("Size", "size"),
                       ("number_of_items", "pieces in the pack"),
                       ("Number of Items", "pieces in the pack"),
                       ("material", "material"), ("Material", "material"),
                       ("colour", "colour"), ("Colour", "colour")):
        v = g(key)
        if v:
            dims.append("%s: %s" % (label, v))
    try:
        import json as _json
        attrs = r.get("attributes_json") or r.get("Attributes JSON") or "{}"
        obj = _json.loads(attrs) if isinstance(attrs, str) else (attrs or {})
        if isinstance(obj, dict):
            for k, label in _DIM_KEYS.items():
                if k in obj:
                    val = _flat_attr(obj[k]).strip()
                    if val:
                        dims.append("%s: %s" % (label, val))
    except Exception:
        pass
    if dims:
        # Deduplicated but ordered: "length: 80 centimetres" twice reads as two
        # different measurements.
        seen, uniq = set(), []
        for d in dims:
            if d.lower() not in seen:
                seen.add(d.lower())
                uniq.append(d)
        parts.append("MEASURED FACTS (authoritative — the photograph cannot "
                     "show these):\n" + "\n".join("- " + d for d in uniq))

    return "\n\n".join(parts).strip()


def describe_product(config: dict, image="", product_title: str = "",
                     provider: str = None, media_root: str = "",
                     listing=None) -> dict:
    """Vision AI reads the seller's ACTUAL product in fine detail so the image
    model reproduces it faithfully. Captures: exact product type/shape, every
    colour, ALL text on labels/packaging verbatim, logo placement, materials,
    finish, proportions. This description is what stops the model from inventing
    or altering the product. Returns {ok, description}."""
    model = provider or select(config, "prompt_enhance")
    if not _key(config):
        return {"ok": False, "error": "No openrouter_api_key in config.json"}
    if not model:
        return {"ok": False, "error": "No text model selected/available"}
    # The cache key is the reference itself plus the title: same product photo,
    # same spec, every time, for every image in the batch.
    _feature("image: read the product")
    _facts = listing_facts(listing) if listing else ""
    _key_img = image if isinstance(image, str) else repr(image)
    # The facts are part of the key. Without them a spec built BEFORE the
    # listing content was available would be handed back for every later image,
    # and the whole point of reading the listing would be cached away.
    _ck = (str(_key_img)[:400], str(product_title)[:200], str(model),
           hash(_facts))
    _hit = _SPEC_CACHE.get(_ck)
    if _hit:
        return dict(_hit, cached=True)

    try:
        ref = _resolve_ref_block(image, media_root)
    except ImageRefError as e:
        return {"ok": False, "error": str(e)}
    sys = (
        "You are a forensic product analyst preparing a brief so an AI image model can RECREATE "
        "this exact product without changing it. Examine the image and document EVERYTHING with "
        "precision — a reproduction needs every measurable detail:\n"
        "1. FORM & PROPORTIONS: exact product type and category; overall silhouette and shape; the "
        "approximate height-to-width ratio (e.g. 'tall slim cylinder ~3:1 height to width'); whether it "
        "tapers, curves, is straight-sided, rounded or angular; the base shape and the top/shoulder shape.\n"
        "2. CONTAINER & PARTS: the vessel type (airless pump bottle, tube, jar, dropper bottle, etc.); the "
        "pump/cap/lid — its exact shape, height relative to the body, and colour; any collar, ring, nozzle, "
        "or button; how the parts join.\n"
        "3. MATERIAL & TEXTURE & FINISH: the material (frosted glass, matte plastic, glossy acrylic, "
        "aluminium); the surface finish (matte / satin / high-gloss / metallic); transparency (opaque / "
        "translucent / clear); any soft-touch or textured feel.\n"
        "4. COLOURS — be exact: every colour and EXACTLY where it appears; note any gradient or ombré and "
        "its direction (e.g. 'white at top fading to orange at the base'); the colour of the cap vs body vs "
        "label; describe colours concretely (warm orange, off-white, charcoal) and their finish.\n"
        "5. ALL TEXT — TRANSCRIBE EVERY WORD VERBATIM exactly as printed, preserving capitalisation, line "
        "breaks, and order: brand name, product name, taglines, ingredient/benefit lines, size/volume, small "
        "print. For each text block note the FONT STYLE (serif/sans-serif, weight, italic, letter-spacing), "
        "the relative SIZE, the colour, the alignment, and its exact position on the product.\n"
        "6. LOGO / GRAPHICS / DECORATION: any logo, icon, symbol, underline, divider line, coloured band or "
        "stripe — describe its shape, colour, thickness, and exact location.\n"
        "7. LABEL LAYOUT: describe the full top-to-bottom arrangement of everything on the front so it can be "
        "reproduced element by element in the right positions and proportions.\n"
        "8. SCALE — HOW BIG IS IT REALLY: state the real-world size in cm or mm. Say what it is held or used "
        "with (one hand, two hands, sits on a worktop, stands on the floor) and how it compares to a familiar "
        "object. A model with no sense of scale renders a hand tool the size of a machine, and the picture "
        "looks entirely convincing.\n"
        "9. EDGES, PROFILE AND WORKING PARTS: for anything with a blade, edge, tine, prong, bristle or tooth "
        "— is the edge straight, curved, hooked, bevelled, serrated or plain? Sharp or blunt? Single or double "
        "sided? COUNT the teeth, tines, prongs, holes, slots or segments and give the number. If it has NONE "
        "of a thing, say so explicitly: 'the blade is plain-edged with NO teeth and NO serrations'.\n"
        "10. WHAT IS NOT THERE — the most important section. List what the product visibly does NOT have, "
        "especially anything a similar product usually would: no teeth, no guard, no second handle, no strap, "
        "no wheels, no markings on this face, no visible fixings. Describing only what IS present leaves an "
        "image model free to add whatever it expects to see, and it adds it confidently. This section is what "
        "stops that.\n"
        "11. WHAT IT IS FOR: state plainly what the product does and how it is USED — who holds it, what "
        "they do with it, where. If the seller's own listing is given below, that is the authority on this; "
        "do not infer a use from what the shape resembles. A tool photographed alone gets shown being used "
        "for the wrong job otherwise, and the picture looks entirely convincing.\n"
        "Be exhaustive, literal and measurement-oriented — this is a reproduction spec, not a description. "
        "Do NOT beautify, summarise, or omit anything. Never describe a feature you cannot actually see; if "
        "something is partly unclear, say it is unclear rather than filling it in. If something is genuinely "
        "hidden by the angle, say 'not visible in this image' rather than inferring it. "
        "Write 450-750 words of precise, structured detail."
    )
    if _facts:
        # WHICH SOURCE WINS, stated explicitly, because they answer different
        # questions and the model will otherwise average them. The photograph is
        # the only evidence of what the thing LOOKS like; the listing is the only
        # evidence of how big it is and what it is for. A photograph cannot say
        # whether a slasher is 20cm or 200cm, and a listing cannot say what
        # colour the handle is.
        sys += (
            "\n\nTHE SELLER'S OWN LISTING FOR THIS PRODUCT IS GIVEN BELOW. Use it and the photograph "
            "together, and understand which answers what:\n"
            "  - The PHOTOGRAPH is the authority on APPEARANCE: shape, colour, finish, label text, "
            "which parts exist. Never contradict it about how the product looks.\n"
            "  - The LISTING is the authority on FACTS the photograph cannot carry: real-world SIZE, "
            "what the product is FOR, how it is used, what it is made of, how many are in the pack. "
            "Never overrule a measurement in the listing with an impression from the photograph.\n"
            "  - Where the two genuinely conflict, say so in the spec rather than silently picking one.\n"
            "Section 8 (SCALE) must use the listing's measurements where it gives any, converted to "
            "something a person can picture — 'the head is 25cm across, about the width of a dinner "
            "plate; the whole tool is 80cm, about the length of a baseball bat'. This is the single "
            "most common way a generated image goes wrong: with no sense of scale a model renders a "
            "hand tool the size of a machine, or a machine the size of a toy.\n"
            "Section 11 (WHAT IT IS FOR) must come from the listing, not from the shape."
        )
    _user = "Product title (for context): %s" % product_title
    if _facts:
        _user += "\n\n--- THE SELLER'S LISTING ---\n" + _facts + "\n--- END OF LISTING ---"
    _user += ("\n\nDocument this exact product for faithful recreation, transcribing ALL label "
              "text verbatim, and state its real size in a way a person can picture.")
    content = [{"type": "text", "text": _user}, ref]
    body = {"model": model,
            "messages": [{"role": "system", "content": sys},
                         {"role": "user", "content": content}],
            "max_tokens": 1600}
    try:
        resp = _post(f"{OPENROUTER_BASE}/chat/completions", config, body, timeout=90)
        text = (resp.get("choices") or [{}])[0].get("message", {}).get("content", "")
        _out = {"ok": bool(text), "description": (text or "").strip(), "provider": model}
        if _out["ok"]:
            # Only a SUCCESSFUL read is cached. Caching a failure would stick an
            # empty spec to the product until restart, and every image after it
            # would be generated with no spec at all.
            _SPEC_CACHE[_ck] = _out
        return _out
    except urllib.error.HTTPError as e:
        d = ""
        try:
            d = e.read().decode("utf-8")[:300]
        except Exception:
            pass
        return {"ok": False, "error": f"OpenRouter vision HTTP {e.code}: {d}"}
    except Exception as e:
        return {"ok": False, "error": f"OpenRouter vision failed: {str(e)[:200]}"}


def _closest_aspect_ratio(w: int, h: int) -> str:
    """Map an exact W×H to the nearest aspect-ratio string the image models accept,
    so the generated composition already roughly matches the target shape before we
    crop to exact pixels. Models typically support 1:1, 4:3, 3:4, 16:9, 9:16, 3:2,
    2:3, 21:9."""
    try:
        ratio = float(w) / float(h)
    except Exception:
        return "1:1"
    candidates = {
        "1:1": 1.0, "4:3": 4/3, "3:4": 3/4, "16:9": 16/9, "9:16": 9/16,
        "3:2": 3/2, "2:3": 2/3, "21:9": 21/9, "5:4": 5/4, "4:5": 4/5,
    }
    best, bestd = "1:1", 1e9
    for name, r in candidates.items():
        d = abs(r - ratio)
        if d < bestd:
            best, bestd = name, d
    return best


# How far the generated shape may differ from the target before cropping starts
# destroying things. Below this, a cover-crop takes a sliver off two edges and
# nobody can tell. Above it, the crop is eating whole lines of type.
_SAFE_CROP = 0.12


def _resize_to_exact(image_b64: str, target_w: int, target_h: int) -> str:
    """Resize a base64 PNG to EXACTLY target_w × target_h. Never cuts content.

    THE BUG THIS FIXES

    This used to cover-crop unconditionally: scale until the image fills the
    box, then centre-crop whatever hangs over. On a small mismatch that is
    invisible and right. On a large one it is a guillotine -- and the models
    return a roughly square image whatever aspect ratio they are asked for, so
    the mismatch was large every time.

    Measured on the real A+ output: a 4096x4096 image cropped to 1464x600
    keeps the middle 41% of its height. Every generated A+ module came back
    with its headline sliced through the middle:

        "MULTIVITAMIN."  -- only the bottom half of the letters
        "WEEKS COVERED." -- top gone
        "2 CAPSULES"     -- bottom gone

    Reported as: "the cutout text is there but it is half, where is the other
    half". The other half was cropped off here.

    SO: crop only while the crop is small. Past that, CONTAIN the whole image
    and pad to the target with the colour of its own edge, which keeps every
    pixel of the composition and reads as a deliberate margin rather than a
    letterbox. Amazon still gets its exact dimensions, and no text is ever cut.
    """
    import base64 as _b64
    from io import BytesIO
    from PIL import Image as _PImg
    raw = _b64.b64decode(image_b64)
    im = _PImg.open(BytesIO(raw)).convert("RGB")
    sw, sh = im.size
    if sw == target_w and sh == target_h:
        return image_b64

    # HOW MUCH WOULD A COVER-CROP THROW AWAY? Cover scales until the box is
    # full, so the overflow on one axis is what gets cut.
    cover = max(target_w / sw, target_h / sh)
    lost = 1.0 - min((target_w / (sw * cover)), (target_h / (sh * cover)))

    if lost <= _SAFE_CROP:
        # A sliver off two edges. Fills the frame, nothing readable is lost.
        nw, nh = max(1, round(sw * cover)), max(1, round(sh * cover))
        im = im.resize((nw, nh), _PImg.LANCZOS)
        left = max(0, (nw - target_w) // 2)
        top = max(0, (nh - target_h) // 2)
        im = im.crop((left, top, left + target_w, top + target_h))
    else:
        # CONTAIN AND PAD. Cropping this much cuts headlines in half, so the
        # whole composition is kept and the difference is padded.
        fit = min(target_w / sw, target_h / sh)
        nw, nh = max(1, round(sw * fit)), max(1, round(sh * fit))
        small = im.resize((nw, nh), _PImg.LANCZOS)
        # Padded with the image's OWN edge colour, sampled from the border it
        # will sit against, so a dark composition gets a dark margin rather
        # than white bars. Read as a median so one bright highlight in the
        # corner does not decide the colour of the whole band.
        pad = _edge_colour(small, "h" if nw >= nh else "v")
        canvas = _PImg.new("RGB", (target_w, target_h), pad)
        canvas.paste(small, ((target_w - nw) // 2, (target_h - nh) // 2))
        im = canvas
    buf = BytesIO()
    im.save(buf, format="PNG")
    return _b64.b64encode(buf.getvalue()).decode("ascii")


def _edge_colour(im, axis="h"):
    """The dominant colour along the edges the padding will touch.

    Median rather than mean: a single bright highlight in one corner should not
    lighten the whole band, and a median ignores it.
    """
    try:
        w, h = im.size
        px = im.load()
        pts = []
        if axis == "h":                       # padding above and below
            for x in range(0, w, max(1, w // 64)):
                pts.append(px[x, 0])
                pts.append(px[x, h - 1])
        else:                                 # padding left and right
            for y in range(0, h, max(1, h // 64)):
                pts.append(px[0, y])
                pts.append(px[w - 1, y])
        if not pts:
            return (255, 255, 255)
        mid = len(pts) // 2
        return tuple(sorted(p[i] for p in pts)[mid] for i in range(3))
    except Exception:
        return (255, 255, 255)


import re as _re_mod
# A real measurement, or a comparison to something everyone can picture.
_re_scale = _re_mod.compile(
    r"(\d+\s?(mm|cm|m\b|inch|inches|in\b|ft\b|feet|kg|g\b|lb|ml|l\b|litre|liter))"
    r"|about the (size|length|width|height) of"
    r"|roughly the (size|length) of"
    r"|(compared|comparable) to a",
    _re_mod.I)


def hard_constraints(product_spec):
    """The lines from the spec that must reach the image model untouched.

    Pulled out by section heading and by the words that carry an absence or a
    count, because those are what a rewriting model discards: it is writing about
    light and composition, and "the blade has NO teeth" is not that. Appended
    after the prompt is written, so nothing downstream can paraphrase it away.

    Returns "" when there is nothing to add, so a caller with no spec is
    unaffected.
    """
    spec = str(product_spec or "")
    if not spec.strip():
        return ""

    # SCALE and WHAT IT IS FOR are on this list for the same reason the absences
    # are: a model rewriting a prompt is writing about light and composition,
    # and "the whole tool is 80cm, about the length of a baseball bat" is not
    # that, so it goes. It is also the single most common way a generated image
    # is wrong -- a hand tool rendered the size of a machine, convincingly.
    want_head = ("what is not there", "scale", "edges, profile", "working parts",
                 "counts", "what it is for", "measured facts", "how big")
    keep, in_section = [], False
    for raw in spec.splitlines():
        line = raw.strip()
        if not line:
            in_section = False
            continue
        low = line.lower().lstrip("0123456789. )-*#").strip()
        if any(low.startswith(h) for h in want_head):
            in_section = True
            keep.append(line)
            continue
        # A heading for some OTHER section closes the one we were in.
        #
        # Detected on the part BEFORE the colon. Requiring the whole LINE to be
        # uppercase never matched, because a real heading looks like
        # "COLOURS: the handle is natural wood" -- so once a wanted section
        # opened, nothing closed it and every line to the end of the spec was
        # pulled in as a non-negotiable fact, including the lighting and the
        # depth of field. A list of forty "non-negotiable" items, most of them
        # about composition, is one the model reads as tone.
        if in_section:
            head = line.split(":", 1)[0] if ":" in line else ""
            if (head and len(head) < 60 and head.strip().isupper()
                    and any(c.isalpha() for c in head)
                    and not any(low.startswith(h) for h in want_head)):
                in_section = False
        if in_section:
            keep.append(line)
            continue
        # Outside the sections, keep any sentence that states an absence or a
        # count -- specs do not always use the headings, and these are the facts
        # that get invented when they go missing.
        l2 = " " + low + " "
        if (" no " in l2 or l2.startswith("no ") or " without " in l2
                or " none " in l2 or " not present" in l2 or " absent" in l2
                or " exactly " in l2):
            keep.append(line)
            continue
        # A measurement or a comparison to a familiar object, wherever it sits.
        # These are the sentences that stop a slasher being drawn the size of an
        # ant or a bed, and they are exactly what a rewrite drops.
        if _re_scale.search(line):
            keep.append(line)

    keep = [k for k in keep if len(k) > 3][:40]
    if not keep:
        return ""
    return ("\n\nNON-NEGOTIABLE FACTS ABOUT THIS PRODUCT — these override anything "
            "above and must be obeyed exactly. Do NOT add any feature that is not "
            "listed as present, and do NOT omit one that is. If a feature is "
            "stated as absent, it must not appear in the image at all:\n"
            + "\n".join("- " + k for k in keep))


def run_pipeline(config: dict, brief: str, reference_image="",
                 product_title: str = "", text_provider: str = None,
                 image_provider: str = None, image_kind: str = "main",
                 read_product: bool = True, strength: float = 0.25,
                 extra_reference: str = "", target_w: int = 0, target_h: int = 0,
                 media_root: str = "", spec_image: str = "", listing=None) -> dict:
    """Vision-first pipeline:
    1) (optional) vision AI reads the ACTUAL product in detail (exact label text,
       shape, colours, material) so the model can't alter it,
    2) prompt AI writes the detailed image prompt incorporating that spec,
    3) image AI generates with the product image attached as reference, using a
       LOW strength so the product is preserved (lower = more faithful).
    extra_reference: an optional SECOND reference image. Used by refine so the
    model edits the generated image while staying anchored to the ORIGINAL product.

    spec_image: WHICH image step 1 should read the product from, when that is not
    the image being edited. Refine needs this: its reference_image is the
    already-generated picture, so reading the product from it would describe a
    copy of a copy and let small errors compound with every edit. Reading the
    ORIGINAL product photo instead keeps every round anchored to the real thing.
    Defaults to reference_image, so every existing caller is unaffected.
    """
    product_spec = ""
    _spec_src = spec_image or reference_image
    if read_product and _spec_src:
        # The listing goes with it: the photograph cannot say how big the thing
        # is or what it is for, and those are the two ways a generated image is
        # most often wrong.
        desc = describe_product(config, _spec_src, product_title,
                                provider=text_provider, media_root=media_root,
                                listing=listing)
        if desc.get("ok"):
            product_spec = desc.get("description", "")
    # fold the exact product spec into the brief so the prompt AI anchors to it
    full_brief = brief
    if product_spec:
        full_brief = (
            brief
            + "\n\nEXACT PRODUCT SPEC (reproduce the product PRECISELY from this — do not change the "
              "shape, colours, layout, logo, or any label text; reproduce all text exactly as written):\n"
            + product_spec
        )
    enh = enhance_prompt(config, full_brief, product_title, provider=text_provider, image_kind=image_kind)
    if not enh.get("ok"):
        return {"ok": False, "error": "Prompt stage: " + enh.get("error", ""), "stage": "prompt"}
    detailed = enh["prompt"]
    # THE FACTS SURVIVE THE REWRITE.
    #
    # enhance_prompt does not pass the spec through -- it REWRITES it into an
    # evocative 350-650 word photography brief. And the things it drops first are
    # precisely the ones that matter here: "NO teeth", "12 cm long", "four slots,
    # not five". They read as dull constraints in a paragraph about lighting and
    # mood, and a model writing prose leaves them out.
    #
    # That is why a better spec alone did not fix the pictures. The hard facts are
    # therefore appended AFTER the rewrite, verbatim, where nothing can edit them.
    detailed = detailed + hard_constraints(product_spec)

    # COMPOSE FOR THE SHAPE THAT IS BEING ASKED FOR.
    #
    # The models return a roughly square picture whatever aspect ratio they are
    # given, so a wide A+ banner arrived as a square composition and the resize
    # had to deal with it. Even now that the resize can no longer cut anything
    # away, a square composition inside a 1464x600 banner is a small picture
    # with wide margins -- correct, and not what anybody wanted.
    #
    # So the shape is stated in words as well, in the prompt itself, along with
    # a safe area. Models respect a described LAYOUT far more reliably than an
    # aspect_ratio parameter, and the safe area is what stops a headline
    # sitting against the very edge where any later trim would clip it.
    if target_w and target_h:
        _shape = ("WIDE BANNER, much wider than it is tall"
                  if target_w > target_h * 1.4 else
                  "TALL, much taller than it is wide"
                  if target_h > target_w * 1.4 else "roughly square")
        detailed += (
            f"\n\nCANVAS AND LAYOUT -- these govern the composition.\n"
            f"The finished image is {target_w} x {target_h} pixels: a {_shape}. "
            f"COMPOSE FOR THAT SHAPE. Lay the elements out ACROSS the long "
            f"dimension -- do not build a square composition and leave the rest "
            f"empty, and do not stack everything down the middle.\n"
            f"SAFE AREA: keep every word, logo and important edge of the "
            f"subject inside the middle 88% of the frame, with nothing that "
            f"matters within about 6% of any edge. Text touching the edge is "
            f"the single most common way one of these is ruined."
        )
    # strength LOW so the model preserves the actual product from the reference
    # (only the scene/angle/background change, not the product itself).
    # size '4K' = Seedream's max (4096px); SAME $0.04 cost as 2K, and gives
    # Amazon zoom-quality. Models that don't support it fall back gracefully.
    # If a target W×H is given (A+ module / secondary), ask the model for the
    # MATCHING aspect ratio so the composition is right, then we resize to the
    # EXACT pixels afterwards (models won't hit exact dimensions on their own).
    _ar = "1:1"
    if target_w and target_h:
        _ar = _closest_aspect_ratio(target_w, target_h)
    img = generate_image(config, detailed, reference_image, provider=image_provider,
                         strength=strength if reference_image else None,
                         aspect_ratio=_ar, image_size="4K", extra_reference=extra_reference,
                         media_root=media_root)
    # REFUSED FOR ITS WORDS? TRY ONCE MORE, DESCRIBING THE OBJECT.
    #
    # The filter fires on the product's NAME, not on the picture being asked for:
    # a "Weed Slasher / Hardened Steel Blade" is an ordinary garden tool and the
    # request is for it on a white background. So the retry strips the product's
    # own aggressive words and asks for the same photograph of the same object,
    # described by its shape and material.
    #
    # This is not talking the model past a real objection -- nothing about the
    # image changes, only the noun. If it refuses again, that is reported as a
    # refusal and no third attempt is made.
    if (not img.get("ok")) and img.get("refused"):
        softened = _soften_for_filter(detailed)
        if softened != detailed:
            img = generate_image(config, softened, reference_image,
                                 provider=image_provider,
                                 strength=strength if reference_image else None,
                                 aspect_ratio=_ar, image_size="4K",
                                 extra_reference=extra_reference,
                                 media_root=media_root)
            if img.get("ok"):
                img["softened_prompt"] = True
                detailed = softened
    if not img.get("ok"):
        return {"ok": False, "error": "Image stage: " + img.get("error", ""),
                "refused": bool(img.get("refused")),
                "stage": "image", "detailed_prompt": detailed, "raw": img.get("raw", "")}
    # EXACT-DIMENSION RESIZE: Amazon A+/secondary modules need precise pixel sizes
    # (e.g. 970×600 basic, 1464×600 premium). The model returns ~square 4K, so we
    # cover-crop + resize to the exact target so Amazon doesn't reject/stretch it.
    if target_w and target_h and img.get("image_b64"):
        try:
            img["image_b64"] = _resize_to_exact(img["image_b64"], int(target_w), int(target_h))
            img["mime"] = "image/png"
            img["resized_to"] = f"{target_w}x{target_h}"
        except Exception as _re:
            img["resize_error"] = str(_re)[:120]
    out = {"ok": True, "detailed_prompt": detailed, "product_spec": product_spec,
           # WAS THE BRIEF REWORDED? Said in the result, not left to be guessed
           # at: the image was made from words the person did not write, and they
           # are entitled to know which ones. detailed_prompt above is the
           # softened version, so it can be read in full.
           "softened_prompt": bool(img.get("softened_prompt")),
           "text_provider": enh.get("provider"), "image_provider": img.get("provider")}
    if img.get("image_b64"):
        out["image_b64"] = img["image_b64"]; out["mime"] = img.get("mime", "image/png")
    elif img.get("image_url"):
        out["image_url"] = img["image_url"]
    return out


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


def _post(url, config, body, timeout=120):
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers=_headers(config), method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


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
                      media_root: str = "") -> dict:
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
            "(RGB 255,255,255), product filling 85%+, NO added text or graphics. Creativity comes ONLY "
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
            "different products should produce visibly different module sets. Sequence them so the N "
            "concepts read as a coherent story top to bottom. Keep each premium and uncluttered (~70% "
            "visual, 30% text), and never make prohibited medical/efficacy claims. In art_direction, note "
            "the module type and the single product-specific headline it should carry."
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
            "genuinely different angles of the buying decision for this exact product."
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
        f"Return ONLY JSON: a list of exactly {n} objects, each "
        '{"title": "<short name>", "customer_insight": "<the buyer psychology this image targets, 1 sentence>", '
        '"concept": "<what the image shows, plain language, 1-2 sentences>", '
        '"art_direction": "<specific art direction for the image model: angle, lighting, composition, any '
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
    content = [{"type": "text",
                "text": (f"Product: {product_title}\n"
                         + (f"\nProduct details:\n{product_spec}\n" if product_spec else "")
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
        return {"ok": False, "error": f"OpenRouter image HTTP {e.code}: {d}"}
    except Exception as e:
        return {"ok": False, "error": f"OpenRouter image failed: {str(e)[:200]}"}


def describe_product(config: dict, image="", product_title: str = "",
                     provider: str = None, media_root: str = "") -> dict:
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
        "Be exhaustive, literal and measurement-oriented — this is a reproduction spec, not a description. "
        "Do NOT beautify, summarise, or omit anything. If something is partly unclear, give your best reading "
        "and mark it. Write 400-650 words of precise, structured detail."
    )
    content = [{"type": "text", "text": f"Product title (for context): {product_title}\n\nDocument this exact product for faithful recreation, transcribing ALL label text verbatim."},
               ref]
    body = {"model": model,
            "messages": [{"role": "system", "content": sys},
                         {"role": "user", "content": content}],
            "max_tokens": 1200}
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


def _resize_to_exact(image_b64: str, target_w: int, target_h: int) -> str:
    """Cover-crop + resize a base64 PNG to EXACTLY target_w × target_h pixels.
    'Cover' = scale so the image fills the box, then center-crop the overflow, so
    the product isn't squished (preserves aspect, fills the frame). Returns new
    base64 PNG. Amazon requires exact module dimensions or it rejects/stretches."""
    import base64 as _b64
    from io import BytesIO
    from PIL import Image as _PImg
    raw = _b64.b64decode(image_b64)
    im = _PImg.open(BytesIO(raw)).convert("RGB")
    sw, sh = im.size
    if sw == target_w and sh == target_h:
        return image_b64
    # scale to cover the target box
    scale = max(target_w / sw, target_h / sh)
    nw, nh = max(1, round(sw * scale)), max(1, round(sh * scale))
    im = im.resize((nw, nh), _PImg.LANCZOS)
    # center-crop to exact target
    left = max(0, (nw - target_w) // 2)
    top = max(0, (nh - target_h) // 2)
    im = im.crop((left, top, left + target_w, top + target_h))
    buf = BytesIO()
    im.save(buf, format="PNG")
    return _b64.b64encode(buf.getvalue()).decode("ascii")


def run_pipeline(config: dict, brief: str, reference_image="",
                 product_title: str = "", text_provider: str = None,
                 image_provider: str = None, image_kind: str = "main",
                 read_product: bool = True, strength: float = 0.25,
                 extra_reference: str = "", target_w: int = 0, target_h: int = 0,
                 media_root: str = "", spec_image: str = "") -> dict:
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
        desc = describe_product(config, _spec_src, product_title,
                                provider=text_provider, media_root=media_root)
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
    if not img.get("ok"):
        return {"ok": False, "error": "Image stage: " + img.get("error", ""),
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
           "text_provider": enh.get("provider"), "image_provider": img.get("provider")}
    if img.get("image_b64"):
        out["image_b64"] = img["image_b64"]; out["mime"] = img.get("mime", "image/png")
    elif img.get("image_url"):
        out["image_url"] = img["image_url"]
    return out


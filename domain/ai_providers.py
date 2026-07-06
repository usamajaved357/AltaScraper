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


def _url_to_data_uri(url: str, timeout: int = 20) -> str:
    """Download a remote image and return it as a base64 data URI. Some providers
    (Anthropic-via-Azure, etc.) reject bare image URLs and require inline base64,
    which caused 'invalid base64 data' 400s when an Amazon image URL was passed
    straight through. Fetching + inlining makes the reference work everywhere."""
    import base64 as _b64
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        ctype = r.headers.get("Content-Type", "") or ""
    # sniff a sane image mime from the bytes if the header is missing/wrong
    mime = "image/jpeg"
    if raw[:3] == b"\xff\xd8\xff": mime = "image/jpeg"
    elif raw[:8] == b"\x89PNG\r\n\x1a\n": mime = "image/png"
    elif raw[:4] == b"RIFF" and raw[8:12] == b"WEBP": mime = "image/webp"
    elif raw[:6] in (b"GIF87a", b"GIF89a"): mime = "image/gif"
    elif ctype.startswith("image/"): mime = ctype.split(";")[0].strip()
    return "data:" + mime + ";base64," + _b64.b64encode(raw).decode("ascii")


def _img_to_ref(url_or_b64: str):
    if not url_or_b64:
        return None
    s = url_or_b64.strip()
    if s.startswith("data:"):
        return {"type": "image_url", "image_url": {"url": s}}
    if s.startswith("http://") or s.startswith("https://"):
        # inline remote images as base64 so EVERY provider accepts them
        # (bare URLs 400 on some Azure/Anthropic routes). Fall back to the raw
        # URL if the download fails, so we never hard-crash on a fetch hiccup.
        try:
            return {"type": "image_url", "image_url": {"url": _url_to_data_uri(s)}}
        except Exception:
            return {"type": "image_url", "image_url": {"url": s}}
    return {"type": "image_url", "image_url": {"url": "data:image/png;base64," + s}}


_ENHANCE_SYSTEM = (
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
    "- Even soft daylight-balanced (5500K) studio lighting, a subtle natural contact shadow under the "
    "product, sRGB colour.\n"
    "- NO text added by you, NO logos added, NO watermarks, NO badges, NO props, NO people, single "
    "product only, shown OUTSIDE its packaging.\n"
    "CRITICAL — PRODUCT FIDELITY: an EXACT PRODUCT SPEC may be provided. Reproduce the product PRECISELY "
    "from it and from the reference image — keep the identical shape, colours, materials, layout, logo "
    "placement, and reproduce ALL label text exactly as written, letter for letter. Do NOT invent, "
    "redesign, restyle, translate, or omit any text or feature. Be specific about lighting, angle, "
    "shadow, and finish. Output ONLY the prompt text, no preamble, 350-650 words."
)


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
        ref = _img_to_ref(im)
        if ref:
            content.append(ref)
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


def strategize_images(config: dict, image: str = "", product_title: str = "",
                      product_spec: str = "", n: int = 3, kind: str = "main",
                      provider: str = None, custom_instructions: str = "") -> dict:
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
    ref = _img_to_ref(image)
    if ref:
        content.append(ref)
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
    sysmsg = {"main": _ENHANCE_SYSTEM, "secondary": _SECONDARY_SYSTEM,
              "aplus": _APLUS_SYSTEM}.get(image_kind, _ENHANCE_SYSTEM)
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


def generate_image(config: dict, prompt: str, reference_image: str = "",
                   provider: str = None, strength: float = None,
                   aspect_ratio: str = "1:1", image_size: str = None,
                   extra_reference: str = "") -> dict:
    model = provider or select(config, "image_generate")
    if not _key(config):
        return {"ok": False, "error": "No openrouter_api_key in config.json"}
    if not model:
        return {"ok": False, "error": "No image model selected/available"}
    body = {"model": model, "prompt": prompt, "output_format": "png"}
    ref = _img_to_ref(reference_image)
    if ref:
        # reference image(s) for editing / product preservation. We can pass more
        # than one: e.g. [image-to-edit, ORIGINAL product] so a refine edits the
        # generated image while staying anchored to the REAL product.
        refs = [ref]
        ref2 = _img_to_ref(extra_reference) if extra_reference else None
        if ref2:
            refs.append(ref2)
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


def describe_product(config: dict, image: str, product_title: str = "",
                     provider: str = None) -> dict:
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
    ref = _img_to_ref(image)
    if not ref:
        return {"ok": False, "error": "no product image to read"}
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


def run_pipeline(config: dict, brief: str, reference_image: str = "",
                 product_title: str = "", text_provider: str = None,
                 image_provider: str = None, image_kind: str = "main",
                 read_product: bool = True, strength: float = 0.25,
                 extra_reference: str = "", target_w: int = 0, target_h: int = 0) -> dict:
    """Vision-first pipeline:
    1) (optional) vision AI reads the ACTUAL product in detail (exact label text,
       shape, colours, material) so the model can't alter it,
    2) prompt AI writes the detailed image prompt incorporating that spec,
    3) image AI generates with the product image attached as reference, using a
       LOW strength so the product is preserved (lower = more faithful).
    extra_reference: an optional SECOND reference image. Used by refine so the
    model edits the generated image while staying anchored to the ORIGINAL product.
    """
    product_spec = ""
    if read_product and reference_image:
        desc = describe_product(config, reference_image, product_title, provider=text_provider)
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
                         aspect_ratio=_ar, image_size="4K", extra_reference=extra_reference)
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


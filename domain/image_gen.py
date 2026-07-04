"""
image_gen.py
============================================================================
AI main-image generation for Amazon listings, using Google Gemini.

Built as a STANDALONE, swappable module: the dashboard calls generate_main_image()
and gets back image bytes (PNG). Nothing else in the app depends on the model
choice -- to swap to OpenAI later, only this file changes.

TWO MODES (user picks per run in the dashboard):
  mode="template"  -> uses a reference TEMPLATE image (your clean studio shot)
                      + the product's own raw image + a prompt, to produce a
                      consistent main image in your template's style/lighting.
  mode="clean"     -> takes the product's raw image alone and restyles it into
                      an Amazon-ready main image (pure white background, centred,
                      no props/text), no template needed.

CONFIG (local config.json, key name only -- you paste the real key locally):
  "gemini_api_key": "..."        # from aistudio.google.com (free tier available)
  "gemini_image_model": "gemini-2.0-flash-exp"   # optional override

AMAZON MAIN-IMAGE RULES baked into the prompt:
  pure white RGB(255,255,255) background, product fills ~85% of frame, centred,
  no text/logos/watermarks/props/people, realistic product photography, single
  product. The caller is responsible for human review before it goes live --
  this returns a candidate, not an auto-published image.

NOTE ON COMPLIANCE: only use this for products you actually sell. Generating a
colour/finish variant of a real product you own (from a real reference) is
defensible; inventing a product you've never photographed is not. The dashboard
button is per-listing and requires you to review, by design.
============================================================================
"""

import base64
import json
import mimetypes
import urllib.request
import urllib.error


# Amazon main-image requirements, expressed as prompt guidance.
_AMAZON_RULES = (
    "Produce a professional Amazon main product image. Requirements: "
    "pure solid white background (RGB 255,255,255), the product centred and "
    "filling about 85 percent of the frame, sharp realistic product photography, "
    "even studio lighting, no text, no logos, no watermarks, no props, no hands, "
    "no people, no borders, a single product only. Square aspect ratio."
)


def _model(config: dict) -> str:
    return (config.get("gemini_image_model") or "gemini-2.0-flash-exp").strip()


def _api_key(config: dict) -> str:
    key = (config.get("gemini_api_key") or "").strip()
    if not key:
        raise RuntimeError(
            "No gemini_api_key in config.json. Get one free at "
            "https://aistudio.google.com/apikey and add it to your local config."
        )
    return key


def _fetch_image_b64(url_or_b64: str):
    """Accept an http(s) URL or a raw base64 string; return (b64, mime)."""
    if not url_or_b64:
        return None, None
    s = url_or_b64.strip()
    if s.startswith("http://") or s.startswith("https://"):
        req = urllib.request.Request(s, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        mime = mimetypes.guess_type(s)[0] or "image/jpeg"
        return base64.b64encode(data).decode("ascii"), mime
    # already base64 (possibly a data: URL)
    if s.startswith("data:"):
        head, _, b64 = s.partition(",")
        mime = head.split(";")[0].replace("data:", "") or "image/png"
        return b64, mime
    return s, "image/png"


def _build_parts(prompt_text, images):
    """images: list of (b64, mime). Returns Gemini 'parts' array."""
    parts = [{"text": prompt_text}]
    for b64, mime in images:
        if b64:
            parts.append({"inline_data": {"mime_type": mime or "image/png", "data": b64}})
    return parts


def generate_main_image(config: dict,
                        mode: str = "clean",
                        product_image: str = "",
                        template_image: str = "",
                        extra_prompt: str = "",
                        product_title: str = "") -> dict:
    """
    Generate one Amazon-ready main image.

    Returns: {"ok": True, "image_b64": "<png base64>", "mime": "image/png"}
          or {"ok": False, "error": "..."}

    mode:
      "template" -> needs template_image (reference) + product_image (raw).
      "clean"    -> needs product_image (raw) only.
    extra_prompt: optional user guidance, e.g. "blue mirror lens variant".
    """
    try:
        key = _api_key(config)
    except RuntimeError as e:
        return {"ok": False, "error": str(e)}

    images = []
    if mode == "template":
        if not template_image:
            return {"ok": False, "error": "template mode needs a template_image"}
        if not product_image:
            return {"ok": False, "error": "template mode needs the product's raw image"}
        tb64, tmime = _fetch_image_b64(template_image)
        pb64, pmime = _fetch_image_b64(product_image)
        images = [(tb64, tmime), (pb64, pmime)]
        prompt = (
            "You are given two images. The FIRST is a TEMPLATE showing the exact "
            "studio style, framing, lighting and white background to match. The "
            "SECOND is the actual product to depict. Re-create the SECOND product "
            "in the EXACT style of the FIRST template image. Keep the real product's "
            "true shape, colour and details from the second image; only adopt the "
            "template's background, lighting and composition. "
            + (("Additional guidance: " + extra_prompt + ". ") if extra_prompt else "")
            + _AMAZON_RULES
        )
    else:  # clean
        if not product_image:
            return {"ok": False, "error": "clean mode needs the product's raw image"}
        pb64, pmime = _fetch_image_b64(product_image)
        images = [(pb64, pmime)]
        prompt = (
            "You are given a raw product photo. Restyle it into a clean Amazon main "
            "image: remove any background and replace with pure white, centre the "
            "product, remove props/hands/text. Keep the product's true shape, colour "
            "and details exactly as in the photo -- do not invent or alter the product. "
            + (("Additional guidance: " + extra_prompt + ". ") if extra_prompt else "")
            + _AMAZON_RULES
        )

    if product_title:
        prompt = f"Product: {product_title}. " + prompt

    body = {
        "contents": [{"parts": _build_parts(prompt, images)}],
        "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]},
    }
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{_model(config)}:generateContent?key={key}")
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            resp = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8")[:300]
        except Exception:
            pass
        return {"ok": False, "error": f"Gemini HTTP {e.code}: {detail}"}
    except Exception as e:
        return {"ok": False, "error": f"Gemini call failed: {str(e)[:200]}"}

    # extract the first inline image part from the response
    try:
        for cand in resp.get("candidates", []):
            for part in cand.get("content", {}).get("parts", []):
                inline = part.get("inline_data") or part.get("inlineData")
                if inline and inline.get("data"):
                    return {"ok": True, "image_b64": inline["data"],
                            "mime": inline.get("mime_type") or inline.get("mimeType") or "image/png"}
        return {"ok": False, "error": "No image returned by Gemini (response had no image part)."}
    except Exception as e:
        return {"ok": False, "error": f"Could not parse Gemini response: {str(e)[:200]}"}

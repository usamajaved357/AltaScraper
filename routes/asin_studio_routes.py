"""routes/asin_studio_routes.py -- generate a branded listing from ANY ASIN.

    "i want to put the name of a random asin for which i want to regenerate
     content ... that asin is not the part of my account ... i want to put the
     competitors of that asin from amazon as optional and i want to put the
     brand name of that asin which i want the content to be generated for, as i
     want to maintain the content as branded and not a generic content without
     brand words."

ONE SCREEN, THREE INPUTS: a source ASIN, optional competitor ASINs, and the
brand the finished listing goes out under. Out comes a DRAFT in this account --
copy, attributes and a seeded Image Studio -- which then travels the existing
road: compliance hold, IP hold, Auto-fix, Preview, Submit. There is no second
way to publish, because a second way to publish is a second set of rules to keep
in step.

WHAT THIS IS NOT
It is not a me-too listing and it does not touch the source ASIN. CLAUDE.md
Rule 1: the ASIN is a REFERENCE used to pull product facts, exactly as the SKU's
embedded ASIN always has been. Nothing here sends merchant_suggested_asin, and
nothing here uses LISTING_OFFER_ONLY.

A SEPARATE COPYWRITER, DELIBERATELY
amazon_listing_generator.py is not imported, called or modified. The build plan
is explicit -- "if any new analytics feature needs a listing copywriter, build
it as a SEPARATE tool on a SEPARATE route with SEPARATE files" -- and Rule 1
protects that file outright. What IS reused is the stuff that must not fork: the
one Anthropic wrapper (domain/ai_usage.call_anthropic, so the spend is recorded
like everything else), the IP scrubber, and the compliance rules.

THE BRAND FIELD TAKES ANY TEXT, BY REQUEST, and that is a smaller decision than
it looks. It changes what may be TYPED, not what Amazon receives:
resolve_account_brand still runs on the submit path and still substitutes this
account's own trademark for one it is not registered for, announcing the swap.
Changing THAT needs Rule 1's explicit sentence, which has not been given. So the
screen accepts the text and says plainly what will happen to it.

THE SOURCE BRAND MUST NOT LEAK, which is the real IP hazard here and the reason
the scrubber is not optional. The copy is generated from a competitor's title
and bullets; without scrubbing, their brand words walk straight into ours.
"""
import datetime as _dt
import json
import re

from flask import jsonify, request

from domain import ai_usage as _ai
from listing import compliance as _comp


def register(app, *, CONFIG_PATH, _cfg=None, _state=None, _active_account=None,
             _catalog_lookup=None):
    """Attach /asin-studio/*."""

    def _scope():
        b = request.get_json(silent=True) or {}
        aid = str(b.get("id") or request.args.get("id") or "").strip()
        mkt = str(b.get("marketplace") or request.args.get("marketplace")
                  or "").strip().upper()
        if not aid or not mkt:
            acc = {}
            try:
                acc = (_active_account() or {}) if callable(_active_account) else {}
            except Exception:
                acc = {}
            aid = aid or str(acc.get("id")
                             or (_state or {}).get("active_account_id") or "")
            mkt = mkt or str(acc.get("default_marketplace")
                             or (_state or {}).get("active_marketplace") or "").upper()
        return aid, (mkt or "UK")

    def _wrong_account(asked):
        from domain import account_scope as _acctscope
        open_id = (_state or {}).get("active_account_id")
        if _acctscope.is_mismatch(asked, open_id):
            return jsonify(_acctscope.refusal(asked, open_id, "listing")), 409
        return None

    _ASIN = re.compile(r"^[A-Z0-9]{10}$")

    def _ip_rules():
        """ip_rules.json, loaded the same way /compliance/scan loads it.

        Beside config.json first (that is the persistent disk on the host), then
        the repo copy. Same two places, same order, so this screen and the
        compliance screen cannot end up judging copy by different rules.
        """
        try:
            import os
            p = os.path.join(os.path.dirname(os.path.abspath(CONFIG_PATH)),
                             "ip_rules.json")
            if not os.path.exists(p):
                p = "ip_rules.json"
            with open(p, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return None

    def _lookup(asin, mkt):
        """One ASIN's public catalogue data. Read-only, and not ours.

        Goes through the SAME /catalog/lookup the ASIN research screen uses, by
        calling the app's own endpoint rather than re-implementing the SP-API
        call -- one place decides what a catalogue lookup returns (rule 12).
        """
        from flask import current_app
        with current_app.test_request_context(
                "/catalog/lookup", method="POST",
                json={"asin": asin, "marketplace": mkt}):
            try:
                fn = current_app.view_functions.get("catalog_lookup")
                if not fn:
                    return {"ok": False, "error": "catalog lookup is not available"}
                resp = fn()
                body = resp[0] if isinstance(resp, tuple) else resp
                return json.loads(body.get_data(as_text=True))
            except Exception as e:
                return {"ok": False, "error": str(e)[:200]}

    # ------------------------------------------------------------- research
    @app.route("/asin-studio/research", methods=["POST"])
    def asin_studio_research():
        """Pull the source ASIN, and any competitors, so the screen can show
        what the copy will be written FROM before a token is spent."""
        wsid, mkt = _scope()
        b = request.get_json(silent=True) or {}
        bad = _wrong_account(b.get("id"))
        if bad:
            return bad
        asin = str(b.get("asin") or "").strip().upper()
        if not _ASIN.match(asin):
            return jsonify({"ok": False,
                            "error": "Enter a valid ASIN (10 characters, like "
                                     "B0XXXXXXXX)."}), 400
        comps = [str(c).strip().upper() for c in (b.get("competitors") or [])]
        comps = [c for c in comps if _ASIN.match(c) and c != asin][:5]

        src = _lookup(asin, mkt)
        if not src.get("ok"):
            return jsonify({"ok": False,
                            "error": "Could not read %s from Amazon: %s"
                                     % (asin, src.get("error") or "no reason given")}), 502
        out_comps, failed = [], []
        for c in comps:
            r = _lookup(c, mkt)
            (out_comps if r.get("ok") else failed).append(
                r if r.get("ok") else {"asin": c, "error": r.get("error")})

        return jsonify({"ok": True, "marketplace": mkt, "source": src,
                        "competitors": out_comps, "failed": failed,
                        "note": ("These are read-only catalogue lookups. Nothing "
                                 "is claimed, listed against, or sent to Amazon "
                                 "— the ASIN is a reference for the product "
                                 "facts, and the listing you create is a NEW "
                                 "product under your own brand.")})

    # ------------------------------------------------------------- generate
    @app.route("/asin-studio/generate", methods=["POST"])
    def asin_studio_generate():
        """Write branded copy from the researched product, then scrub it."""
        wsid, mkt = _scope()
        b = request.get_json(silent=True) or {}
        bad = _wrong_account(b.get("id"))
        if bad:
            return bad
        src = b.get("source") or {}
        brand = str(b.get("brand") or "").strip()
        if not brand:
            return jsonify({"ok": False,
                            "error": "Enter the brand this listing goes out "
                                     "under. Copy with no brand in it is the "
                                     "generic writing you asked to avoid."}), 400
        title_in = str(src.get("title") or src.get("item_name") or "").strip()
        if not title_in:
            return jsonify({"ok": False,
                            "error": "Research an ASIN first — there is nothing "
                                     "to write from."}), 400

        key = ((_cfg() or {}).get("anthropic_api_key") or "").strip() \
            if callable(_cfg) else ""
        if not key:
            return jsonify({"ok": False,
                            "error": "No anthropic_api_key in config.json."}), 400

        comps = b.get("competitors") or []
        # WHAT THE MODEL IS SHOWN. Facts about the product, and competitors only
        # as a sense of the category. Their brand names are not sent -- a model
        # given "Acme Pro 3000" will reach for it, and the scrub afterwards
        # should be a safety net rather than the only thing standing in the way.
        def _facts(d):
            return {"title": str(d.get("title") or "")[:300],
                    "bullets": [str(x)[:220] for x in (d.get("bullets") or [])[:5]],
                    "attributes": {k: v for k, v in
                                   list((d.get("attributes") or {}).items())[:25]}}

        payload = {"product": _facts(src),
                   "category_examples": [_facts(c) for c in comps[:3]],
                   "brand": brand, "marketplace": mkt}

        system = (
            "You write Amazon listing copy for a seller's OWN-BRAND product.\n\n"
            "THE BRAND IS %s. Use it naturally in the title and at least one "
            "bullet so the listing reads as a branded product rather than a "
            "generic one. Never invent a sub-brand or model name that was not "
            "given to you.\n\n"
            "NEVER mention, imply or allude to any OTHER brand, manufacturer, "
            "seller or trademark, and never use comparison phrasing such as "
            "'compatible with', 'replacement for', 'alternative to', 'works "
            "with <brand>' or 'compare to'. The examples you are shown are the "
            "CATEGORY, not something to reference.\n\n"
            "Make no claim you cannot support from the facts given: no medical, "
            "safety, certification, eco or performance claims that are not in "
            "the source attributes. If a fact is unknown, leave it out rather "
            "than guessing.\n\n"
            "Write for the %s marketplace, metric units where relevant.\n\n"
            "Return ONLY minified JSON: {\"title\": str (<=200 chars), "
            "\"bullets\": [5 strings, <=250 chars each], "
            "\"description\": str (plain text, 3-5 short paragraphs), "
            "\"search_terms\": str (<=250 bytes, space separated, no commas, "
            "no brand names at all), "
            "\"attributes\": {flat map of any listing attributes you can state "
            "confidently from the source, e.g. material, colour, size}}"
            % (brand, mkt))

        # THE SHAPE IS ENFORCED BY THE API, NOT HOPED FOR.
        #
        # This used to ask for JSON in the prompt, pull the first {...} out of
        # the reply with a regex and json.loads it -- and roughly one call in
        # four came back with something that would not parse. Measured:
        #   "The copywriter's JSON would not parse: Expecting ',' delimiter:
        #    line 1 column 1287"
        # from a real run. When it happens the whole thing 502s and the user
        # gets nothing, having waited half a minute for it.
        #
        # output_config makes the model's reply conform to this schema, so
        # there is no prose to strip, no fence to find and nothing to repair.
        # The prompt still describes the fields because the model writes better
        # copy when it knows what each one is for -- but the prompt is no longer
        # what holds the format together.
        # TWO THINGS THE API WILL NOT ACCEPT, both measured against it rather
        # than assumed (CLAUDE.md Rule 4 -- the schema is available, so ask it):
        #
        #   "For 'array' type, 'minItems' values other than 0 or 1 are not
        #    supported (got: [2, 5])"
        #   "For 'object' type, 'additionalProperties: object' is not supported.
        #    Please set 'additionalProperties' to false"
        #
        # So the five-bullet count stays in the PROMPT, where it always was, and
        # the attributes come back as a list of pairs rather than an open map --
        # an array of fixed-shape objects is allowed where a free-form object is
        # not. It is turned back into a dict below, so nothing downstream sees
        # the difference.
        SCHEMA = {
            "type": "object",
            "properties": {
                "title": {"type": "string", "maxLength": 200},
                "bullets": {"type": "array", "items": {"type": "string"}},
                "description": {"type": "string"},
                "search_terms": {"type": "string"},
                "attributes": {
                    "type": "array",
                    "items": {"type": "object",
                              "properties": {"name": {"type": "string"},
                                             "value": {"type": "string"}},
                              "required": ["name", "value"],
                              "additionalProperties": False},
                },
            },
            "required": ["title", "bullets", "description", "search_terms"],
            "additionalProperties": False,
        }
        copy, text = None, ""
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=key)
            kw = dict(model="claude-opus-5", max_tokens=4000,
                      thinking={"type": "adaptive"},
                      system=system,
                      messages=[{"role": "user",
                                 "content": json.dumps(payload,
                                                       ensure_ascii=False)}])
            try:
                resp = _ai.call_anthropic(
                    client, CONFIG_PATH, feature="asin_studio",
                    workspace_id=wsid,
                    output_config={"format": {"type": "json_schema",
                                              "schema": SCHEMA}}, **kw)
            except TypeError:
                # An older SDK that has never heard of output_config. Fall back
                # rather than fail: the prompt already asks for JSON, and the
                # tolerant parse below still handles it.
                resp = _ai.call_anthropic(
                    client, CONFIG_PATH, feature="asin_studio",
                    workspace_id=wsid, **kw)
            text = "".join(getattr(blk, "text", "") for blk in (resp.content or [])
                           if getattr(blk, "type", "") == "text").strip()
        except Exception as e:
            return jsonify({"ok": False,
                            "error": "The copywriter failed: %s" % str(e)[:220]}), 502

        # With a schema the whole reply IS the object, so try that first and
        # only fall back to hunting for braces.
        try:
            copy = json.loads(text)
        except Exception:
            m = re.search(r"\{.*\}", text, re.S)
            if not m:
                return jsonify({"ok": False,
                                "error": "The copywriter did not return usable "
                                         "JSON.", "raw": text[:600]}), 502
            try:
                copy = json.loads(m.group(0))
            except Exception as e:
                return jsonify({"ok": False,
                                "error": "The copywriter's JSON would not parse: %s"
                                         % str(e)[:160], "raw": text[:600]}), 502
        if not isinstance(copy, dict):
            return jsonify({"ok": False,
                            "error": "The copywriter returned a %s, not a "
                                     "listing." % type(copy).__name__,
                            "raw": text[:600]}), 502
        # Attributes arrive as [{name, value}] under the schema above and as a
        # plain object on the fallback path. Normalise to the dict every caller
        # already expects, so the shape the API forced on us stops here.
        _at = copy.get("attributes")
        if isinstance(_at, list):
            copy["attributes"] = {
                str(p.get("name") or ""): str(p.get("value") or "")
                for p in _at if isinstance(p, dict) and p.get("name")}

        # THE SCRUB IS NOT OPTIONAL. The copy was written from a competitor's
        # words, so their brand can walk into ours. scrub_listing_copy is the
        # app's existing IP pass (ip_rules.json: "zero brand names except
        # seller's own brand") and it runs here for the same reason it runs on a
        # generated row.
        bl = list(copy.get("bullets") or [])[:5]
        # THE SHAPE THESE CHECKS ACTUALLY READ: bullet_1..bullet_5 as separate
        # keys, not a "bullets" list. Handed a list they inspect the title and
        # description and silently skip every bullet -- most of the copy, and
        # the likeliest place for a competitor's brand to land.
        flat = {"title": copy.get("title", ""),
                "description": copy.get("description", ""),
                "search_terms": str(copy.get("search_terms") or "")}
        for i in range(5):
            flat["bullet_%d" % (i + 1)] = bl[i] if i < len(bl) else ""

        # TWO DIFFERENT CHECKS, AND I HAD THE WRONG ONE FIRST.
        #
        # listing.compliance.scrub_copy is NOT a trademark check -- its own
        # docstring says it strips "seller self-promotion, shipping/fulfilment
        # claims, external links, or unverifiable superlatives". Handed
        # "Compatible with Hozelock fittings" it returns it untouched, which I
        # measured before trusting it.
        #
        # The real one is check_ip_violations (listing/compliance.py), reading
        # ip_rules.json's forbidden_phrases -- and domain/compliance_scan.scan
        # already wraps it together with the forbidden-brand check. That wrapper
        # is what /compliance/scan uses, so this screen and that screen judge
        # copy by the same rules (rule 12).
        ip_notes, findings = [], []
        try:
            from domain import compliance_scan as _cscan
            _res = _cscan.scan(flat, brand=brand,
                               product_type=str(src.get("product_type") or ""),
                               ip_rules=_ip_rules())
            findings = (_res.get("findings") if isinstance(_res, dict)
                        else _res) or []
        except Exception as e:
            ip_notes.append(
                "The compliance and IP scan could not run (%s), so this copy has "
                "NOT been checked for other brands' names or comparative "
                "phrasing. Read it before you submit." % type(e).__name__)

        # The promotional scrub still runs -- it removes superlatives and
        # shipping claims Amazon rejects, which is a different job from the IP
        # check and worth doing too.
        try:
            ip_notes.extend(_comp.scrub_listing_copy(flat) or [])
        except Exception:
            pass

        scrubbed = {"title": flat.get("title", ""),
                    "bullets": [flat.get("bullet_%d" % (i + 1), "")
                                for i in range(5)
                                if flat.get("bullet_%d" % (i + 1))],
                    "description": flat.get("description", ""),
                    "search_terms": flat.get("search_terms", "")}
        listing = {"title": copy.get("title", ""), "bullets": bl,
                   "description": copy.get("description", ""),
                   "search_terms": str(copy.get("search_terms") or "")}

        return jsonify({"ok": True, "brand": brand, "marketplace": mkt,
                        "copy": scrubbed, "attributes": copy.get("attributes") or {},
                        "ip_notes": ip_notes,
                        "brand_note": _brand_note(brand, wsid),
                        "raw_before_scrub": listing})

    def _brand_note(brand, wsid):
        """What will actually happen to this brand on the way to Amazon.

        The field accepts anything, by request. This says -- before any work is
        done, not after -- that the submit path still substitutes the account's
        own trademark for one it is not registered for. Saying nothing would let
        somebody generate a whole listing under a brand that cannot go out.
        """
        try:
            import accounts as _acc
            cfg = (_cfg() or {}) if callable(_cfg) else {}
            acc = _acc.get_account(cfg, wsid, CONFIG_PATH) or {}
            mine = [str(x) for x in (acc.get("brands") or []) if x]
            if not mine:
                return ("This account has no registered trademarks set, so "
                        "nothing can be checked against. Add them in Account "
                        "settings.")
            if any(str(brand).lower() == m.lower() for m in mine):
                return ""
            return ("“%s” is not one of this account's registered trademarks "
                    "(%s). You can generate with it, but when the draft is "
                    "submitted the account's own brand is sent instead and the "
                    "swap is reported — that rule is not changed by this screen. "
                    "If Amazon has approved this brand, add it in Account "
                    "settings and it will be used as typed."
                    % (brand, ", ".join(mine)))
        except Exception:
            return ""

    # ---------------------------------------------------------- make a draft
    @app.route("/asin-studio/create-draft", methods=["POST"])
    def asin_studio_create_draft():
        """Write the generated listing into this account as an ordinary draft.

        ORDINARY is the point. It gets a SKU and a row like any other, so the
        compliance hold, the IP hold, Auto-fix, Preview and Submit all work on
        it with no special case. A second kind of listing would be a second set
        of rules to keep in step, and they would drift.
        """
        wsid, mkt = _scope()
        b = request.get_json(silent=True) or {}
        bad = _wrong_account(b.get("id"))
        if bad:
            return bad
        copy = b.get("copy") or {}
        brand = str(b.get("brand") or "").strip()
        src_asin = str(b.get("source_asin") or "").strip().upper()
        price = str(b.get("price") or "").strip()
        if not copy.get("title"):
            return jsonify({"ok": False, "error": "Generate the copy first."}), 400
        if not brand:
            return jsonify({"ok": False, "error": "A brand is needed."}), 400

        # THE SKU KEEPS THE APP'S OWN FORMAT: price_days_ASIN. That embedded
        # ASIN is the competitor reference the whole app already understands --
        # rowAsin() reads it, the green ASIN link ignores it, and the duplicate
        # check keys off it. Inventing a new SKU shape for this one screen would
        # give every one of those a case it has never seen.
        days = str(b.get("handling_days") or "3").strip() or "3"
        sku = "%s_%sDays_%s" % (price or "0.00", days, src_asin or "MANUAL")

        bullets = list(copy.get("bullets") or [])[:5]
        row = {
            "SKU": sku,
            "Title": copy.get("title", ""),
            "Description (HTML)": copy.get("description", ""),
            "Brand": brand,
            "Search Terms": copy.get("search_terms", ""),
            "Handling Days": days,
            "Status": "NEEDS_REVIEW",
            "Notes": ("Generated by ASIN Studio from %s. The ASIN is a source "
                      "reference for the product facts, not a listing to join."
                      % (src_asin or "a manual entry")),
        }
        for i, bl in enumerate(bullets, 1):
            row["Bullet %d" % i] = bl
        if price:
            row["Our Price (GBP)"] = price
        attrs = b.get("attributes") or {}
        if attrs:
            row["Attributes JSON"] = json.dumps(attrs, ensure_ascii=False)
        if src_asin:
            row["UPC"] = ""            # never invent a barcode -- CLAUDE.md Rule 1

        try:
            from data import backend as _backend
            store = _backend.make(_state, CONFIG_PATH)
            ws = store.worksheet() if hasattr(store, "worksheet") else store
            if hasattr(ws, "upsert_row"):
                ws.upsert_row(row)
            else:
                from data.store import ListingStore
                ListingStore(wsid, CONFIG_PATH).upsert_row(row)
        except Exception as e:
            return jsonify({"ok": False,
                            "error": "Could not save the draft: %s"
                                     % str(e)[:220]}), 500

        return jsonify({"ok": True, "sku": sku,
                        "status": "NEEDS_REVIEW",
                        "message": ("Draft created. It is in Listings with the "
                                    "compliance and IP checks still to run — "
                                    "open it there to review, fix and submit. "
                                    "Nothing has been sent to Amazon.")})

    return app

// static/js/amazon_errors.js
// Plain-English translations for common Amazon listing errors. DISPLAY ONLY -- this
// never changes any logic; it only reformats an error the app already received. The
// raw Amazon text is ALWAYS kept and shown under a "Show original Amazon message"
// toggle, so nothing is hidden -- it just isn't the first thing you read.
//
// Add a pattern by pushing {id, test, build} to AMZ_ERROR_PATTERNS.
//   test(text)      -> true if this pattern applies
//   build(text,ctx) -> {icon, title, plain(HTML), action(text)}   ctx = {barcode, sku, productType}

(function (global) {
  "use strict";

  // self-contained escaper (works even if the app's global esc() loads later)
  function E(s) {
    if (typeof global.esc === "function") return global.esc(s);
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  // pull distinct 'quoted_snake_case' attribute names out of a message (drops the ASIN)
  //
  // AMAZON USES CURLY QUOTES TOO. Real messages carry both:
  //   The field 'width.unit' for the attribute 'Package Width Unit' ...
  //   The provided value for ‘Item Display Width’ is invalid
  // Matching only the straight quote missed every message of the second kind,
  // and those are 6 of the 11 the translator could not read.
  function quotedAttrs(t) {
    var out = [], m, re = /['‘]([A-Za-z][A-Za-z0-9_. ]*)['’]/g;
    while ((m = re.exec(t))) {
      var v = m[1].trim();
      if (v && !/^B0[A-Z0-9]{8}$/i.test(v) && out.indexOf(v) < 0) out.push(v);
    }
    return out;
  }

  // The attribute name Amazon prefixes its line with: "item_package_dimensions
  // The provided value ..." -> "item_package_dimensions".
  function leadField(t) {
    return (String(t).match(/^\s*([a-z][a-z0-9_]+)\b/) || [])[1] || "";
  }

  var AMZ_ERROR_PATTERNS = [
    {
      // The check-digit case. The generator already catches this BEFORE sending
      // (and falls back to the GTIN exemption), but the same wording reaches
      // this translator from stored error text, and "check digit" means nothing
      // to most people. The three patterns further down cover the barcode being
      // taken, conflicting, or refused for a new ASIN -- this covers the one
      // where the number itself is mistyped.
      id: "barcode_check_digit",
      test: function (t) { return /check digit is wrong|invalid checksum|not a valid (?:EAN|UPC|GTIN)/i.test(t); },
      build: function (t) {
        var code = (t.match(/(\d{8,14})/) || [])[1] || "";
        return {
          icon: "🔖",
          title: "That barcode has a typo in it",
          plain: "A barcode carries its own arithmetic check — the last digit " +
                 "is worked out from the ones before it, so a single mistyped " +
                 "digit can be spotted without looking anything up. " +
                 (code ? "<b>" + E(code) + "</b> fails that check, which means " +
                         "one digit is wrong." : "This one fails that check.") +
                 " It is the right length, so it is a typo rather than a made-" +
                 "up number.",
          action: "Read it off the supplier's invoice or the product packaging " +
                  "again, digit by digit. If no real barcode exists for this " +
                  "product, leave the field empty — the listing goes up under " +
                  "the GTIN exemption."
        };
      }
    },
    {
      // "Value '10.' ... has too few decimal places. It has 0 decimal places
      //  but the minimum allowed is '1'."
      //
      // Two different faults wear this message. '10.' is a MALFORMED number --
      // a trailing dot with nothing after it, which is what stripping zeros
      // without then handling the dot produces. '10' is a well-formed number
      // that Amazon still refuses, because these dimension attributes demand at
      // least one decimal place. Saying which one it is saves the guess.
      id: "too_few_decimals",
      test: function (t) { return /too few decimal places/i.test(t); },
      build: function (t) {
        var val = (t.match(/Value\s+['‘]([^'’]*)['’]/i) || [])[1] || "";
        var attr = (t.match(/for attribute\s+['‘]([^'’]+)['’]/i) || [])[1] || leadField(t) || "this field";
        var min = (t.match(/minimum allowed is\s+['‘](\d+)['’]/i) || [])[1] || "1";
        var malformed = /\.\s*$/.test(val);
        return {
          icon: "⚠️",
          title: "Number needs a decimal place",
          plain: "Amazon wants at least <b>" + E(min) + "</b> decimal place" +
                 (min === "1" ? "" : "s") + " for <b>" + E(attr) + "</b>" +
                 (val ? ", and got <b>" + E(val) + "</b>" : "") + ". " +
                 (malformed
                   ? "That value ends in a dot with nothing after it, which is a " +
                     "number that was trimmed badly rather than one you typed."
                   : "A whole number is not enough here."),
          action: "Write it as " + (val ? E(val.replace(/\.$/, "")) : "the number") +
                  ".0 rather than " + (val ? E(val.replace(/\.$/, "")) : "a whole number") +
                  ", then Preview again."
        };
      }
    },
    {
      // "The provided value for 'Item Display Width' is invalid" -- Amazon's
      // least helpful message, and 6 of the 11 the translator could not read.
      // It says nothing about WHY, so this must not pretend to know either.
      id: "provided_value_invalid",
      test: function (t) { return /the provided value for\s+['‘][^'’]+['’]\s+is invalid/i.test(t); },
      build: function (t) {
        var attr = (t.match(/provided value for\s+['‘]([^'’]+)['’]/i) || [])[1] || "a field";
        var parent = leadField(t);
        return {
          icon: "⚠️",
          title: "Value rejected",
          plain: "Amazon refused the value for <b>" + E(attr) + "</b>" +
                 (parent ? " (part of <b>" + E(parent) + "</b>)" : "") +
                 " and did not say why. In practice it is almost always the " +
                 "SHAPE rather than the number: a measurement needs both a value " +
                 "and a unit, and the unit has to be one from Amazon's own list.",
          action: "Open " + E(parent || attr) + " in the editor, check the value and " +
                  "its unit are both filled and the unit came from the dropdown, then Preview again."
        };
      }
    },
    {
      // Barcode already linked to a DIFFERENT product. Distinct from the
      // catalogue-conflict pattern below: this one names the ASIN outright and
      // tells you to dispute or delete, so it gets its own answer.
      id: "barcode_linked_elsewhere",
      test: function (t) { return /bar ?code[\s\S]*already linked to product/i.test(t); },
      build: function (t, ctx) {
        var bc = (t.match(/bar ?code\s+(\d{8,14})/i) || [])[1] ||
                 ((ctx && ctx.barcode) ? String(ctx.barcode).trim() : "");
        var asin = (t.match(/product\s+([A-Z0-9]{10})/i) || [])[1] || "another product";
        return {
          icon: "⛔",
          title: "Barcode belongs to another product",
          plain: "Barcode " + (bc ? "<b>" + E(bc) + "</b>" : "") + " is already " +
                 "registered to <b>" + E(asin) + "</b>, which Amazon can see is not " +
                 "what you are listing. This happens with bought or reused EANs — " +
                 "they carry whatever product they were first registered against.",
          action: "Clear the Barcode / GTIN box so the listing uses the GTIN exemption, " +
                  "or put in a barcode registered to THIS product. Never invent one."
        };
      }
    },
    {
      // Not an error at all. It was being shown in a red box beside real ones.
      id: "under_review",
      test: function (t) { return /reviewing this listing to determine if any additional information/i.test(t); },
      build: function (t) {
        var hrs = (t.match(/up to\s+(\d+)\s*hours/i) || [])[1] || "48";
        return {
          icon: "⏳",
          title: "Accepted — Amazon is reviewing it",
          plain: "This is not a rejection. Amazon has taken the listing and is " +
                 "checking whether it needs anything else, which takes up to <b>" +
                 E(hrs) + " hours</b>. If it needs something, it will say so here.",
          action: "Nothing to do. Check back after " + E(hrs) + " hours."
        };
      }
    },
    {
      // Barcode matched an EXISTING ASIN, then attributes disagreed with that catalogue record.
      id: "barcode_catalogue_conflict",
      test: function (t) {
        return /standard product ids[\s\S]*provided matches the asin/i.test(t) &&
               /(attribute value\(s\)[\s\S]*conflict|contradicts what is already)/i.test(t);
      },
      build: function (t, ctx) {
        var asin = (t.match(/matches the ASIN\s+([A-Z0-9]{10})/i) || [])[1] || "a different product";
        // leading field token (the [E] line begins with the attribute name, e.g. "color The Listing...")
        var lead = (t.match(/^\s*([a-z][a-z0-9_]+)\b/) || [])[1] || "";
        var attrs = quotedAttrs(t);
        if (lead && attrs.indexOf(lead) < 0) attrs.unshift(lead);
        var attrStr = attrs.length ? attrs.join(", ") : "one or more fields";
        var bc = (ctx && ctx.barcode) ? String(ctx.barcode).trim() : "";
        return {
          icon: "⚠️",
          title: "Barcode conflict",
          plain: "Your barcode " + (bc ? "<b>" + E(bc) + "</b> " : "") +
                 "is already registered to a different ASIN (<b>" + E(asin) + "</b>). Amazon matched " +
                 "your listing to that product and found a mismatch on <b>" + E(attrStr) + "</b>.",
          action: "Fix: clear the Barcode / GTIN field to use the GTIN exemption, or replace it with a unique barcode for THIS product."
        };
      }
    },
    {
      // Amazon says an attribute we sent doesn't apply to this product type (a warning, not a block).
      id: "attr_not_applicable",
      test: function (t) { return /does not belong or is no longer applicable to the product type/i.test(t); },
      build: function (t, ctx) {
        var attr = (t.match(/attribute\s+([A-Za-z0-9_ ]+?)\s+that does not belong/i) || [])[1] ||
                   (t.match(/^\s*([a-z][a-z0-9_]+)\b/) || [])[1] || "this field";
        var pt = (ctx && ctx.productType) ? String(ctx.productType) : "this product type";
        return {
          icon: "ℹ️",
          title: "Field ignored (not applicable)",
          plain: "Amazon says <b>" + E(attr.trim()) + "</b> doesn’t apply to <b>" + E(pt) + "</b>.",
          action: "It’s being ignored, not blocking your listing — no action needed."
        };
      }
    },
    {
      // Barcode rejected outright when CREATING a new ASIN (no existing match) -- GS1 check failed.
      id: "barcode_rejected_new_asin",
      test: function (t) {
        return /(does not match any asin|not in the catalog(?:ue)?|isn'?t (?:a )?valid (?:gtin|ean|upc))/i.test(t) &&
               !/matches the asin/i.test(t);
      },
      build: function (t, ctx) {
        var bc = (ctx && ctx.barcode) ? String(ctx.barcode).trim() : "";
        return {
          icon: "⛔",
          title: "Barcode rejected",
          plain: "Amazon won’t accept " + (bc ? "barcode <b>" + E(bc) + "</b>" : "this barcode") +
                 " to create a new listing — purchased/reseller EANs aren’t GS1-registered to your brand, so Amazon’s GS1 check rejects it.",
          action: "Replace it with a barcode registered to this product, or empty the Barcode / GTIN box to use the GTIN exemption (needs GTIN-exemption approval for this brand + category)."
        };
      }
    },
    {
      // Nested value+unit / structure rejected even though a value was sent.
      id: "value_structure_invalid",
      test: function (t) {
        return /(does not have enough values|invalid attribute value|not a valid value|does not match the expected)/i.test(t);
      },
      build: function (t, ctx) {
        var field = (t.match(/^\s*([a-z][a-z0-9_]+)\b/) || [])[1] || (quotedAttrs(t)[0] || "a field");
        return {
          icon: "⚠️",
          title: "Value not accepted",
          plain: "Amazon didn’t accept the value for <b>" + E(field) + "</b> — either it’s missing a required part (e.g. a unit) or it isn’t one of Amazon’s allowed values.",
          action: "Open the field in the editor and pick an allowed value (use the dropdown where shown), then Preview again."
        };
      }
    },
    {
      // Plain "required but missing" -> the app's Suggest-missing-fields handles this.
      id: "required_missing",
      test: function (t) { return /required but missing/i.test(t); },
      build: function (t, ctx) {
        var field = (t.match(/^\s*([a-z][a-z0-9_]+)\b/) || [])[1] || "a field";
        return {
          icon: "ℹ️",
          title: "Missing required field",
          plain: "Amazon needs a value for <b>" + E(field) + "</b>.",
          action: "Click “Suggest missing fields” above to fill what Amazon flagged, then Preview again."
        };
      }
    }
  ];

  // Translate one message line. Returns {matched:false} or {matched:true, id, icon, title, plain, action}.
  function translateAmazonError(text, ctx) {
    var t = String(text || "");
    for (var i = 0; i < AMZ_ERROR_PATTERNS.length; i++) {
      try {
        if (AMZ_ERROR_PATTERNS[i].test(t)) {
          var r = AMZ_ERROR_PATTERNS[i].build(t, ctx || {});
          r.matched = true; r.id = AMZ_ERROR_PATTERNS[i].id;
          return r;
        }
      } catch (e) { /* a bad pattern must never break the display */ }
    }
    return { matched: false };
  }

  // One translated card's HTML (already-escaped internals).
  function cardHTML(tr) {
    return '<div class="amztrans">' +
      '<div class="amztrans-h">' + tr.icon + ' <b>' + E(tr.title) + '</b></div>' +
      '<div class="amztrans-p">' + tr.plain + '</div>' +
      '<div class="amztrans-a">' + E(tr.action) + '</div></div>';
  }

  // Render a set of Amazon error LINES into translated cards (raw line if no pattern matches),
  // followed by ONE "Show original Amazon message" toggle holding the full verbatim text.
  //   lines   : array of message strings (already stripped of the [E]/[W] prefix)
  //   rawFull : the complete original text to keep under the toggle
  //   ctx     : {barcode, sku, productType}
  function renderAmazonErrors(lines, rawFull, ctx) {
    var arr = (lines && lines.length) ? lines : [String(rawFull || "")];
    var anyMatched = false;
    var body = arr.map(function (ln) {
      var tr = translateAmazonError(ln, ctx);
      if (tr.matched) { anyMatched = true; return cardHTML(tr); }
      return '<div class="amztrans amztrans-raw"><div class="amztrans-p">' + E(ln) + '</div></div>';
    }).join("");
    var toggle = '<details class="amzraw"><summary>Show original Amazon message</summary>' +
                 '<div class="ramz">' + E(String(rawFull || arr.join("  •  "))) + '</div></details>';
    return { html: body + toggle, matched: anyMatched };
  }

  global.translateAmazonError = translateAmazonError;
  global.renderAmazonErrors = renderAmazonErrors;
  global.AMZ_ERROR_PATTERNS = AMZ_ERROR_PATTERNS;
})(window);

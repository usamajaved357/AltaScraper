# PATCH_nested_subfields.py
# ============================================================================
# Adds NESTED SUB-FIELD rendering to dashboard.py.
#
# THE BUG IT FIXES
# ----------------
# Amazon attributes like `battery`, `maximum_speed`, `num_batteries` are OBJECTS
# with sub-fields (e.g. battery -> cell_composition, weight{value,unit},
# average_life{value,unit}). The dashboard's schema extractor only looked ONE
# level deep (`vp = ip.get("value", {})`), so it collapsed each nested attribute
# into a single dead box you couldn't fill — and Amazon kept flagging it.
# After this patch, nested attributes expand into their real sub-field boxes,
# each a dropdown/number input with the correct enum, saved FLAT into the
# Attributes JSON as "<field>.<subpath>" (e.g. "battery.weight.value": "180").
#
# APPLIES TO: your current brand/USA dashboard.py (the ~1445-line file).
# ALL FOUR EDITS ARE ADDITIVE. Nothing in the brand path (rowProvenance, _AHIDE,
# view_list/view_set, per-brand routing, scoped preview/submit) is touched.
#
# IMPORTANT — flat dot-keys at submit time:
#   The dashboard now stores e.g. "battery.weight.value" as a flat key. The
#   GENERATOR's build_api_attributes must RE-NEST these into Amazon's object
#   shape before putListingsItem. That generator-side un-flatten is a SEPARATE
#   change (do it in the merge chat). Until then, the dashboard captures the
#   values correctly; just don't expect nested submit to work until the
#   generator re-nests. (Re-nest helper is sketched at the bottom of this file.)
#
# After applying: restart Flask (Ctrl+C, re-run), then Ctrl+Shift+R in browser.
# ============================================================================


# ───────────────────────────────────────────────────────────────────────────
# EDIT 1 — deepen the schema extractor (Python).
# In _load_schema:
#
#   (1a) the empty-pt early return currently returns a dict MISSING attrs/subfields.
#        Find this line (≈ line 92):
#
#            return {"enums": {}, "required": []}
#
#        Replace with:
#
#            return {"enums": {}, "required": [], "attrs": [], "subfields": {}}
#
#   (1b) the info initialiser (≈ line 95):
#
#            info = {"enums": {}, "required": [], "attrs": []}
#
#        Replace with:
#
#            info = {"enums": {}, "required": [], "attrs": [], "subfields": {}}
#
#   (1c) inside the `for field, prop in (raw.get("properties", {}) or {}).items():`
#        loop, AFTER the existing block that sets info["enums"][field], add the
#        two lines marked NEW so the loop becomes:
#
#            for field, prop in (raw.get("properties", {}) or {}).items():
#                items   = prop.get("items", {})
#                ip      = items.get("properties", {}) if isinstance(items, dict) else {}
#                vp      = ip.get("value", {})
#                allowed = (vp.get("enum") or ip.get("enum") or items.get("enum") or prop.get("enum") or [])
#                if allowed:
#                    info["enums"][field] = [str(a) for a in allowed]
#                subs = _extract_subfields(prop)          # NEW
#                if subs:                                 # NEW
#                    info["subfields"][field] = subs      # NEW
#
# Then paste the THREE helper functions below ABOVE `def _load_schema(`.
# ───────────────────────────────────────────────────────────────────────────

_SUBFIELD_PLUMBING = {"language_tag", "marketplace_id", "audience"}


def _sf_enum_of(node):
    """Enum list for a schema node, unwrapping a localized array+items.value wrapper."""
    if not isinstance(node, dict):
        return None
    if isinstance(node.get("enum"), list):
        return [str(x) for x in node["enum"]]
    it = node.get("items")
    if isinstance(it, dict):
        props = it.get("properties")
        vp = props.get("value") if isinstance(props, dict) else None
        if isinstance(vp, dict) and isinstance(vp.get("enum"), list):
            return [str(x) for x in vp["enum"]]
    return None


def _sf_kind(node):
    t = node.get("type") if isinstance(node, dict) else None
    return "number" if t in ("number", "integer") else "text"


def _extract_subfields(prop) -> list:
    """
    Given ONE top-level attribute's schema node, return the fillable sub-field
    controls Amazon actually expects underneath it.

      []  -> plain single-value attribute (current single box is correct)
      [{path,label,kind,enum}, ...] -> render these sub-field boxes instead

    'path' is dot-joined keys UNDER the attribute. Saved flat into Attributes JSON
    as '<field>.<path>' (e.g. battery.weight.value), so the existing flat /edit
    write path needs NO change. Re-nesting happens generator-side at submit.
    """
    if not isinstance(prop, dict):
        return []
    node = prop
    if node.get("type") == "array" and isinstance(node.get("items"), dict):
        node = node["items"]
    sub = node.get("properties") if isinstance(node, dict) else None
    if not isinstance(sub, dict):
        return []
    keys = [k for k in sub.keys() if k not in _SUBFIELD_PLUMBING]
    # Only real key is "value" -> plain attribute, not nested.
    if keys == ["value"]:
        return []
    out = []
    for k in keys:
        child = sub[k]
        cnode = child
        if isinstance(child, dict) and child.get("type") == "array" and isinstance(child.get("items"), dict):
            cnode = child["items"]
        cprops = {}
        if isinstance(cnode, dict) and isinstance(cnode.get("properties"), dict):
            cprops = {ck: cv for ck, cv in cnode["properties"].items()
                      if ck not in _SUBFIELD_PLUMBING}
        if set(cprops.keys()) == {"value", "unit"}:
            out.append({"path": k + ".value", "label": (k + " value").replace("_", " "),
                        "kind": _sf_kind(cprops["value"]), "enum": _sf_enum_of(cprops["value"])})
            out.append({"path": k + ".unit", "label": (k + " unit").replace("_", " "),
                        "kind": "text", "enum": _sf_enum_of(cprops["unit"])})
        else:
            out.append({"path": k, "label": k.replace("_", " "),
                        "kind": _sf_kind(child), "enum": _sf_enum_of(child)})
    return out


# ───────────────────────────────────────────────────────────────────────────
# EDIT 2 — add a subfields accessor (Python).
# Directly BELOW the existing `def _schema_attrs(pt):` function, add:
# ───────────────────────────────────────────────────────────────────────────

def _schema_subfields(pt: str) -> dict:
    return _load_schema(pt).get("subfields", {})


# ───────────────────────────────────────────────────────────────────────────
# EDIT 3 — expose subfields through the /schema endpoint (Python).
# Find (≈ line 447):
#
#     return jsonify({"ok": True, "enums": _options_for(pt), "required": _schema_required(pt), "attrs": _schema_attrs(pt)})
#
# Replace with (adds the subfields key):
#
#     return jsonify({"ok": True, "enums": _options_for(pt), "required": _schema_required(pt), "attrs": _schema_attrs(pt), "subfields": _schema_subfields(pt)})
# ───────────────────────────────────────────────────────────────────────────


# ───────────────────────────────────────────────────────────────────────────
# EDIT 4 — render nested sub-fields (JavaScript, inside the big HTML <script>).
#
#   (4a) In loadSchemas(), store the new subfields. Find (≈ line 1262):
#
#     SCHEMAS[pt]=j.ok?{opts:(j.enums||{}),req:(j.required||[]),attrs:(j.attrs||[])}:{opts:{},req:[],attrs:[]};}catch(e){SCHEMAS[pt]={opts:{},req:[],attrs:[]};}
#
#        Replace with (adds subs:):
#
#     SCHEMAS[pt]=j.ok?{opts:(j.enums||{}),req:(j.required||[]),attrs:(j.attrs||[]),subs:(j.subfields||{})}:{opts:{},req:[],attrs:[],subs:{}};}catch(e){SCHEMAS[pt]={opts:{},req:[],attrs:[],subs:{}};}
#
#
#   (4b) In fullData(), replace the attrRows builder. Find these TWO lines
#        (≈ line 1147–1148 — note YOUR version has the provenance args
#        `_prov`, `_AHIDE`, and the 4th edRow arg; this replacement KEEPS them):
#
#     const _prov=rowProvenance(r); const attrRows=aKeys.filter(k=>!_AHIDE.has(k)).map(k=>edRow(k.replace(/_/g," "), editCell(sku,"attr",k,a[k],enums[k]||null), flagged[k], _prov&&_prov[k])).join("")
#       + missing.map(k=>edRowReq(k.replace(/_/g," "), editCell(sku,"attr",k,"",enums[k]||null), flagged[k])).join("");
#
#        Replace BOTH lines with this block:
#
#     const _prov=rowProvenance(r);
#     const subs=sc.subs||{};
#     // Render ONE attribute. If schema says it's a nested object (battery,
#     // maximum_speed, num_batteries), expand into its real sub-field boxes;
#     // each sub-field saves flat as "<field>.<path>".
#     const renderAttr=(k,isMissing)=>{
#       const sf=subs[k];
#       if(sf&&sf.length){
#         const head=`<tr class="subhead${isMissing?' flaggedrow':''}"><td class="k" colspan="2"><b>${esc(k.replace(/_/g," "))}</b>${isMissing?' <span class="fixhint">\u26a0 fill the sub-fields below</span>':''}</td></tr>`;
#         const rows=sf.map(s=>{
#           const full=k+"."+s.path;                 // flat dot-key in Attributes JSON
#           const val=(full in a)?a[full]:"";
#           return edRow("&nbsp;&nbsp;\u21b3 "+esc(s.label), editCell(sku,"attr",full,val,(s.enum&&s.enum.length?s.enum:null)), null, _prov&&_prov[full]);
#         }).join("");
#         return head+rows;
#       }
#       return isMissing
#         ? edRowReq(k.replace(/_/g," "), editCell(sku,"attr",k,"",enums[k]||null), flagged[k])
#         : edRow(k.replace(/_/g," "), editCell(sku,"attr",k,a[k],enums[k]||null), flagged[k], _prov&&_prov[k]);
#     };
#     // skip flat dot-keys that belong to a nested group (rendered under their head)
#     const isSubKey=k=>k.includes(".")&&subs[k.split(".")[0]];
#     // parents whose sub-values are already filled (so head + sub-rows still show)
#     const filledParents=[...new Set(aKeys.filter(isSubKey).map(k=>k.split(".")[0]))]
#         .filter(p=>!aKeys.includes(p)&&!missing.includes(p));
#     const presentTop=aKeys.filter(k=>!_AHIDE.has(k)&&!isSubKey(k));
#     const attrRows=presentTop.map(k=>renderAttr(k,false)).join("")
#       + filledParents.map(k=>renderAttr(k,false)).join("")
#       + missing.map(k=>renderAttr(k,true)).join("");
#
#
#   (4c) Make the optional-field picker expand nested fields too. Replace your
#        WHOLE addField(...) function (≈ line 1078) with this version:
#
#     function addField(sku, pt, sel){
#       const k=sel.value; if(!k) return;
#       const sc=SCHEMAS[pt]||{opts:{}}; const opts=(sc.opts||{}); const subs=(sc.subs||{});
#       const tb=document.getElementById("added_"+sid(sku));
#       if(!tb){ sel.value=""; return; }
#       if(tb.querySelector('tr[data-fk="'+k+'"]')){ sel.value=""; return; }
#       const sf=subs[k];
#       if(sf&&sf.length){
#         const head=document.createElement("tr");
#         head.setAttribute("data-fk",k); head.className="subhead";
#         head.innerHTML='<td class="k" colspan="2"><b>'+k.replace(/_/g," ")+'</b></td>';
#         tb.appendChild(head);
#         sf.forEach(s=>{
#           const full=k+"."+s.path;
#           const tr=document.createElement("tr");
#           tr.innerHTML='<td class="k">&nbsp;&nbsp;\u21b3 '+s.label+'</td><td class="v">'+editCell(sku,"attr",full,"",(s.enum&&s.enum.length?s.enum:null))+'</td>';
#           tb.appendChild(tr);
#         });
#       }else{
#         const tr=document.createElement("tr");
#         tr.setAttribute("data-fk",k);
#         tr.innerHTML='<td class="k">'+k.replace(/_/g," ")+'</td><td class="v">'+editCell(sku,"attr",k,"",opts[k]||null)+'</td>';
#         tb.appendChild(tr);
#       }
#       for(let i=sel.options.length-1;i>=0;i--){ if(sel.options[i].value===k) sel.remove(i); }
#       sel.value="";
#     }
#
#
#   (4d) Add CSS for the sub-field group header. Find (≈ line 757):
#
#     .flaggedrow .k{color:#e9c965}
#
#        Add these two lines directly after it:
#
#     .subhead td{padding-top:8px;border-top:1px solid #2a3142;color:#9cc1ff;font-size:12px}
#     .subhead.flaggedrow td{color:#e9c965}
# ───────────────────────────────────────────────────────────────────────────


# ============================================================================
# GENERATOR SIDE (do in the merge chat) — re-nest flat dot-keys at submit.
# build_api_attributes currently sends each Attributes-JSON key flat. Before it
# builds the SP-API payload, fold dot-keys back into nested objects, e.g.
#   "battery.weight.value":"180" + "battery.weight.unit":"grams"
#     -> {"battery":[{"weight":{"value":180,"unit":"grams"}, ...}]}
# Sketch (drop near the top of build_api_attributes, operating on the dict `pa`):
#
#     def _renest(flat: dict) -> dict:
#         nested, plain = {}, {}
#         for k, v in flat.items():
#             if "." in k:
#                 top, rest = k.split(".", 1)
#                 cur = nested.setdefault(top, {})
#                 parts = rest.split(".")
#                 for p in parts[:-1]:
#                     cur = cur.setdefault(p, {})
#                 cur[parts[-1]] = v
#             else:
#                 plain[k] = v
#         plain.update(nested)   # nested wins where both exist
#         return plain
#
# Then wrap each re-nested top-level object as Amazon expects (array of one
# object with marketplace_id), matching how the other attributes are wrapped in
# build_api_attributes. Validate against a real Preview before Submit.
# ============================================================================


# --- VALIDATION after applying (run these locally) --------------------------
#   python3 -m py_compile dashboard.py        # Python must compile
#   # extract the <script> block and:  node --check that.js   # JS must parse
#   # then: start Flask, open a drone (UNMANNED_AERIAL_VEHICLE) card —
#   #   battery / maximum_speed / num_batteries should now show INDENTED
#   #   sub-field boxes (↳), each a dropdown/number with the right options,
#   #   instead of one empty box.

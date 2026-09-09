/* static/js/textsearch.js -- does this query match this text? Decided ONCE.
 *
 *     "THE SEARCH CAMPAIGNS BAR IS NOT WORKING, i want to search campaigns,
 *      the search bar should use the same logic as amazon uses for the search
 *      bar of campaign manager"
 *
 * WHY THIS FILE EXISTS RATHER THAN A SECOND COPY OF THE RULE.
 *
 * listings.js already had the good answer -- "every word somewhere, in any
 * order" -- written out inside matchesSearch, wrapped up with barcode digits
 * and the two-ASIN lookup that only a listing has. The campaigns bar had a bare
 * indexOf on the name. Two screens, two ideas of what searching means, and the
 * campaigns one could not find anything with a space in it.
 *
 * So the part that is genuinely the same -- how a typed query is compared with
 * some text -- lives here, and each screen supplies its own fields. Rule 12.
 *
 * ── WHAT THE RULE IS, and why each part of it ──────────────────────────────
 *
 * TRIMMED. "  auto  " found 0 campaigns out of 254 before this, because the
 * spaces were part of the needle. Nobody types trailing spaces on purpose; they
 * arrive by pasting, which is exactly when you are least likely to suspect the
 * search box.
 *
 * CASE-INSENSITIVE, both sides.
 *
 * SUBSTRING, so "fol" finds Folding and Foldable, and "ceilingfan" finds
 * SP_AUTO_CeilingFan_DISC. Matching inside a word is most of what makes a
 * search feel immediate.
 *
 * EVERY WORD, IN ANY ORDER. This is the one that matters here. Campaign names
 * are underscore-joined segments -- SP_NB_FoldingTrayTable_Exact_GROW -- so a
 * single substring can never span two of them: "auto ceiling" is not a run of
 * characters in any name that exists. Requiring every word somewhere instead
 * means the two things you remember about a campaign are enough to find it,
 * and it stays strict: two words still cut 254 campaigns to one or two.
 *
 * ANY LINE, when several are given. Paste a list of campaign names -- one per
 * line, or comma separated -- and anything matching ANY of them is kept. That
 * is the bulk case Amazon's own campaign search is used for, and it is an OR
 * across lines with the AND above still applying within each line.
 *
 * WHAT IT DELIBERATELY DOES NOT DO: split camelCase. "ceiling fan" does not
 * find CeilingFan, because inserting word breaks that the data does not have
 * guesses at where a name divides and would quietly match things the reader
 * did not ask for. "ceilingfan" and "auto ceiling" both work, and both are
 * things the person typing can see are true of the name.
 */

/* One field, lowercased and safe for null. */
function altaSqText(v){ return String(v == null ? "" : v).toLowerCase(); }

/* Split a raw query into the alternatives to try. Lines and commas separate
 * alternatives; spaces inside one alternative are the AND above.
 *
 * A comma inside a campaign name would be split wrongly here -- none of this
 * account's 254 names contains one, and pasting a list is the case that
 * actually happens. */
function altaSearchTerms(q){
  return String(q == null ? "" : q)
    .split(/[\n\r,]+/)
    .map(function(s){ return s.trim().toLowerCase(); })
    .filter(function(s){ return s.length > 0; });
}

/* Does ONE alternative match? `hay` is the joined, already-lowercased text. */
function altaSearchOne(term, hay){
  if(!term) return true;
  if(hay.indexOf(term) >= 0) return true;          // the whole phrase, as typed
  // EVERY WORD SOMEWHERE, ANY ORDER. Single words are left to the substring
  // pass above -- it already matches inside a word, and this would add nothing.
  const words = term.split(/\s+/).filter(function(w){ return w.length > 0; });
  if(words.length < 2) return false;
  return words.every(function(w){ return hay.indexOf(w) >= 0; });
}

/* THE ONE ANSWER. `fields` is whatever the screen thinks is searchable.
 *
 * Returns true for an empty query, so a caller can use it as a filter without
 * special-casing "nothing typed yet". */
function altaSearchMatch(q, fields){
  const terms = altaSearchTerms(q);
  if(!terms.length) return true;
  // A SEPARATOR NOTHING CAN CONTAIN, so a typed PHRASE cannot match across two
  // fields -- "fan disc" has to be a run inside ONE of them, not the end of the
  // name and the start of the next. The per-word pass below is deliberately
  // allowed to span fields: "auto ceiling" being true of the row AS A WHOLE is
  // exactly the point of it.
  const hay = (fields || []).map(altaSqText).join(" \u0000 ");
  return terms.some(function(t){ return altaSearchOne(t, hay); });
}

/* Node's require, for the tests. Ignored by the browser. */
if(typeof module !== "undefined" && module.exports){
  module.exports = {altaSearchMatch: altaSearchMatch,
                    altaSearchTerms: altaSearchTerms,
                    altaSearchOne: altaSearchOne,
                    altaSqText: altaSqText};
}

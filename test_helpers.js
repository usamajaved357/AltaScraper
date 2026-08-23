// test_helpers.js -- shared helpers for the JavaScript tests.
//
// WHY THIS EXISTS: A COMMENT STRIPPER THAT ATE 5,716 CHARACTERS OF REAL CODE.
//
// Nine test files each carried their own regex-based comment remover -- one
// replace for block comments, one for line comments. It is necessary work,
// because these files explain themselves in comments using the very words the
// assertions look for, so without it a test can pass on its own explanation.
//
// But a REGEX LITERAL can end in the same two characters a block comment does.
// In static/js/listings.js:
//
//     .replace(/\bUKCA\b[^.;|]*/gi, "")
//
// the character class ends with a star and the literal ends with a slash, so
// the last two characters before "gi" are the block-comment terminator. There
// are eight such lines. The stripper counted each as a comment ending, its
// pairing went out of step, and a later comment opening matched a far-away
// terminator -- deleting lines 1654 to 1760 of listings.js, 5,716 characters of
// live code including the Preview, Auto-fix, Submit and Optimize buttons.
//
// test_one_card.js was therefore asserting things about a file with a hole in
// it, and reported that autoFixLoop and priceEdit did not exist. They do. The
// same idiom in the other eight files is a silent version of the same problem:
// an assertion cannot fail on code it cannot see, so it passes instead.
//
// (This header is in line comments for the same reason: written as a block, the
// examples above would close it early. That is not a workaround -- it is the
// bug, reproducing itself in the file that documents it.)
//
// So the stripping is done by SCANNING rather than by regex: strings, template
// literals and regex literals are copied through untouched, and only real
// comments are removed.
"use strict";

// Characters that can legally precede a regex literal. After a value -- an
// identifier, a number, a closing bracket -- a slash is division instead, and
// treating `a / b` as the start of a regex would swallow the rest of the file.
const _BEFORE_REGEX = new Set("(,=:[!&|?{};+-*%~^<>".split(""));

function stripJsComments(src) {
  const s = String(src == null ? "" : src);
  let out = "";
  let i = 0;
  let prev = "";                     // last non-space character emitted
  while (i < s.length) {
    const c = s[i];
    const d = s[i + 1];

    if (c === "/" && d === "*") {                 // block comment
      const end = s.indexOf("*/", i + 2);
      i = end < 0 ? s.length : end + 2;
      continue;
    }
    if (c === "/" && d === "/") {                 // line comment
      const nl = s.indexOf("\n", i);
      i = nl < 0 ? s.length : nl;                 // keep the newline itself
      continue;
    }
    if (c === '"' || c === "'" || c === "`") {    // a string or template
      let j = i + 1;
      while (j < s.length) {
        if (s[j] === "\\") { j += 2; continue; }
        if (s[j] === c) break;
        // A template literal can contain ${ ... }, and that expression may hold
        // any of the above -- including a comment, which is the idiom this
        // codebase uses to annotate markup: ${/* why */""}. Handled by scanning
        // the substitution as its own source and stripping it too.
        if (c === "`" && s[j] === "$" && s[j + 1] === "{") {
          let depth = 1;
          let k = j + 2;
          while (k < s.length && depth > 0) {
            // COMMENTS FIRST, and this is the whole of the bug that was here.
            // The walker skipped strings so that a brace inside one would not be
            // counted -- but not comments. So an apostrophe inside the very
            // comment being stripped ("Amazon's own", "nobody could find")
            // opened a string that ran to the next apostrophe hundreds of
            // characters away, the brace depth stopped meaning anything, and the
            // substitution ended in the wrong place: output came back with a
            // stray "}" on the end and later comments left in place.
            //
            // Which is exactly the failure this whole file exists to stop -- a
            // stripper that quietly returns something other than the code.
            if (s[k] === "/" && s[k + 1] === "*") {
              const e = s.indexOf("*/", k + 2);
              k = e < 0 ? s.length : e + 2;
              continue;
            }
            if (s[k] === "/" && s[k + 1] === "/") {
              const e = s.indexOf("\n", k);
              k = e < 0 ? s.length : e;
              continue;
            }
            if (s[k] === "{") depth++;
            else if (s[k] === "}") depth--;
            else if (s[k] === '"' || s[k] === "'" || s[k] === "`") {
              const q = s[k];
              k++;
              while (k < s.length && s[k] !== q) { if (s[k] === "\\") k++; k++; }
            }
            k++;
          }
          out += s.slice(i, j) + "${" + stripJsComments(s.slice(j + 2, k - 1)) + "}";
          i = k;
          j = k;
          // The template continues after the substitution.
          let m = i;
          while (m < s.length) {
            if (s[m] === "\\") { m += 2; continue; }
            if (s[m] === c) break;
            if (s[m] === "$" && s[m + 1] === "{") break;
            m++;
          }
          if (m < s.length && s[m] === c) { out += s.slice(i, m + 1); i = m + 1; prev = c; }
          else { out += s.slice(i, m); i = m; }
          break;
        }
        j++;
      }
      if (i < s.length && (s[i] === '"' || s[i] === "'" || s[i] === "`")) {
        out += s.slice(i, Math.min(j + 1, s.length));
        i = j + 1;
        prev = s[i - 1];
      }
      continue;
    }
    if (c === "/" && (prev === "" || _BEFORE_REGEX.has(prev))) {   // regex literal
      let j = i + 1;
      let inClass = false;
      let closed = false;
      while (j < s.length) {
        if (s[j] === "\\") { j += 2; continue; }
        if (s[j] === "\n") break;                 // unterminated -- not a regex
        if (s[j] === "[") inClass = true;
        else if (s[j] === "]") inClass = false;
        else if (s[j] === "/" && !inClass) { closed = true; break; }
        j++;
      }
      if (closed) {
        while (j + 1 < s.length && /[a-z]/i.test(s[j + 1])) j++;   // flags
        out += s.slice(i, j + 1);
        i = j + 1;
        prev = "/";
        continue;
      }
    }
    out += c;
    if (c.trim()) prev = c;
    i++;
  }
  return out;
}

module.exports = { stripJsComments };

// static/js/scopeq.js — which account and marketplace a request is about.
//
// ONE BUILDER, USED BY EVERY SCREEN.
//
// There were four copies of this, in daily.js, weekly.js, stock.js and
// ppcview.js, and they had already drifted into two different behaviours — which
// is what CLAUDE.md Rule 12 exists to stop, and why the fifth copy that this
// screen needed became this file instead.
//
// TWO REAL FAULTS WERE FOUND BY PUTTING THEM SIDE BY SIDE:
//
//   1. daily.js and weekly.js read a variable called WS_ID. Nothing in this app
//      has ever defined WS_ID. Those two screens have therefore always sent an
//      EMPTY account id and relied entirely on the server's idea of which
//      account is active. It works today because selecting an account updates
//      that server state — but it is the same shape as the fault that put one
//      account's orders on another account's Orders tab, and it survived only
//      because nobody compared the two versions. The account is CUR_ACCOUNT.id,
//      which shell.js actually maintains.
//
//   2. daily.js and weekly.js sent marketplace=__all__ verbatim. "__all__" is
//      the UI's word for "every marketplace", not a marketplace, and a screen
//      that forwards it is asking the server for a country called __all__. The
//      stock and PPC copies already dropped it; these did not.
//
// An ABSENT parameter is the right way to say "you decide": every route's
// _scope() falls back to the active account when a value is missing, and treats
// an empty string as missing. So omitting is both correct and honest, where
// sending an empty id looks like an answer.

function scopeQs(extra) {
  const qs = [];
  try {
    if (typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT && CUR_ACCOUNT.id) {
      qs.push("id=" + encodeURIComponent(CUR_ACCOUNT.id));
    }
    // "__all__" is the UI's word for "every marketplace". It is not a country
    // and must never be sent as one.
    if (typeof WS_MARKET !== "undefined" && WS_MARKET && WS_MARKET !== "__all__") {
      qs.push("marketplace=" + encodeURIComponent(WS_MARKET));
    }
  } catch (e) {}
  if (extra && typeof extra === "object") {
    Object.keys(extra).forEach(function (k) {
      const v = extra[k];
      if (v === null || v === undefined || v === "") return;
      qs.push(encodeURIComponent(k) + "=" + encodeURIComponent(v));
    });
  }
  return qs.length ? "?" + qs.join("&") : "";
}

// The account id on its own, for the callers that put it in a form body rather
// than a query string. Returns "" when there is no account, which every route
// already treats as "use the active one".
function scopeAccountId() {
  try {
    if (typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT && CUR_ACCOUNT.id) {
      return String(CUR_ACCOUNT.id);
    }
  } catch (e) {}
  return "";
}

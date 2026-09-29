"""The ASIN monitor must know its account; no jack_uk fallback (owner, 29 Sep 2026).

read.txt: "ASIN monitor: REMOVE the jack_uk fallback. A background monitor must
explicitly know which account it belongs to. If no account is configured, fail
safely and report the configuration problem."

Pinned here, with the tracked-ASIN list stubbed and no credentials anywhere, so
nothing can reach Amazon: an unset account stops the cycle BEFORE any call,
says so in the words the Monitor screen shows (phase "failed" + error), and a
configured account is used as named -- never replaced by jack_uk.
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

fails = []


def check(l, g, w):
    ok = g == w
    if not ok:
        fails.append(l)
    print("  %-64s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))


TMP = tempfile.mkdtemp(prefix="altamon_")
CFG_PATH = os.path.join(TMP, "config.json")
json.dump({"accounts": []}, open(CFG_PATH, "w"))

from monitor import checker as C

check("no built-in default account any more", hasattr(C, "_MONITOR_ACCOUNT_DEFAULT"), False)

print("=== nothing configured ===")
for cfg in ({}, {"asin_monitor_account": ""}, {"asin_monitor_account": "   "}):
    creds, err = C._resolve_creds(dict(cfg), CFG_PATH)
    check("no creds, the configuration problem (%r)" % cfg.get("asin_monitor_account"),
          (creds, err), (None, C.NO_ACCOUNT))
check("  and it names what to set", "asin_monitor_account" in C.NO_ACCOUNT, True)

print("=== a cycle stops before any call, and the screen is told ===")
_real_list = C._store.list_asins
C._store.list_asins = lambda cp: [{"asin": "B0TEST0001", "marketplaces": ["UK"]}]
said = []
try:
    r = C.check_all({}, CFG_PATH, log=said.append)
finally:
    C._store.list_asins = _real_list
check("refused", r, {"ok": False, "error": C.NO_ACCOUNT})
st = C.status() if hasattr(C, "status") else C._STATUS
check("  status: failed, with the reason the screen shows",
      (st.get("last_run_ok"), st.get("phase"), st.get("error")), (False, "failed", C.NO_ACCOUNT))
check("  and in the log", any(C.NO_ACCOUNT in s for s in said), True)

print("=== a configured account is used as named ===")
creds, err = C._resolve_creds({"asin_monitor_account": "nestwell_goods"}, CFG_PATH)
check("an account that does not exist is reported by its OWN name, not jack_uk",
      (creds, err), (None, "monitor account 'nestwell_goods' not found"))

if fails:
    raise SystemExit("FAILED: %d" % len(fails))
print("\nthe monitor only ever runs for the account it is given")

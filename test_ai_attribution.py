"""Where the AI money went: which feature, which account, which product.

"ai spend is also not reflecting correct data, many users are using the app now
 and if images are created or any other feature is used which caused ai to use
 credits it should be recorded accurately where spent went, to which feature
 which account"

THREE THINGS WERE WRONG, and the first is the one that mattered.

1. IMAGE GENERATION WAS NEVER RECORDED AT ALL.

   _post() logged the call only when the url contained "chat/completions", and
   generate_image posts to /images. So every picture the app has ever made was
   missing from the ledger. The reading, the thinking and the prompt-writing
   around each image were all there; the expensive part was not.

   Measured on the live ledger before the fix: 46 rows, images = 0 on every
   single one, and no row anywhere with the feature "image: generate" -- which
   _feature() sets at the top of generate_image.

2. THE SKU WAS ALWAYS BLANK. All 46 rows named an account and a feature and no
   product, so "which item did that spend go on" could not be answered.

3. AN IMAGE WAS PRICED AT NOTHING. PRICES has no entry for
   bytedance-seed/seedream-4.5, which is the model in use, so the first correctly
   recorded image came back with cost NULL -- honest, and still lower than the
   bill.

Verified live, generating a real image for 10.99_3Days_B0GGSCK998:
    before   46 rows, 0 images
    after    50 rows, 2 images, feature "image: generate",
             sku 10.99_3Days_B0GGSCK998, cost 0.04 from OpenRouter itself
"""
# THE TREE THIS TEST LIVES IN. It used to name the main checkout outright, so
# run from any other checkout it silently tested THAT checkout's code
# (Milestone 1, 28 Sep 2026: 141 files did this).
import os as _os_repo
_REPO = _os_repo.path.dirname(_os_repo.path.abspath(__file__))
import json
import os
import sys
import tempfile

sys.path.insert(0, _REPO)

# A FIXTURE OF ITS OWN (28 Sep 2026). The last section used to read the owner's
# live ledger, so it passed only on his machine. It now drives one fake image
# call through the real recorder into a database in a temp dir, and reads THAT.
# Set before any app import, so nothing can resolve the real config or database.
_FIX = tempfile.mkdtemp(prefix="fixt_ai_attribution_")
_CFG = os.path.join(_FIX, "config.json")
_DBP = os.path.join(_FIX, "altascraper.db")
with open(_CFG, "w", encoding="utf-8") as _fh:
    json.dump({"anthropic_api_key": "test-placeholder-not-a-key",
               "openrouter_api_key": "test-placeholder-not-a-key",
               "accounts": [{"id": "jack_uk", "name": "Test", "marketplace": "UK"}]},
              _fh)
os.environ["CONFIG_PATH"] = _CFG
os.environ["ALTASCRAPER_DB"] = _DBP
assert os.path.dirname(os.path.abspath(_DBP)) == os.path.abspath(_FIX)

fails = []
def check(l, g, w):
    ok = g == w
    if not ok: fails.append(l)
    print("  %-70s %s" % (l, "OK" if ok else "FAIL got=%r want=%r" % (g, w)))
def truthy(l, g): check(l, bool(g), True)
def falsy(l, g): check(l, bool(g), False)

from domain import ai_usage as U

P = open(_os_repo.path.join(_REPO, r"domain\ai_providers.py"), encoding="utf-8").read()
A = open(_os_repo.path.join(_REPO, r"domain\ai_usage.py"), encoding="utf-8").read()
D = open(_os_repo.path.join(_REPO, r"dashboard.py"), encoding="utf-8").read()

print("=== every call is recorded, whichever endpoint it used ===")
falsy("the chat-only condition is gone from the recorder",
      'if "chat/completions" in str(url):' in P)
truthy("  and the reason is written down", "posts to /images" in P)
truthy("a failed call is still recorded", "must not look free" in P)

print("\n--- and the pictures are counted, both reply shapes ---")
truthy("there is one counter for both", "def _count_images" in P)
truthy("  the chat shape", 'p.get("choices")' in P)
truthy("  and the images-endpoint shape",
       'p.get("data")' in P and 'd.get("b64_json")' in P)
truthy("  with the reason a third would be one line", "another silent zero" in P)

print("\n=== the provider's own cost beats our table ===")
truthy("there is a reader for it", "def cost_from_openrouter" in A)
check("  it takes usage.cost", U.cost_from_openrouter({"usage": {"cost": 0.04}}), 0.04)
check("  or total_cost", U.cost_from_openrouter({"usage": {"total_cost": 0.5}}), 0.5)
check("  and None when there is none", U.cost_from_openrouter({"usage": {}}), None)
check("  nonsense is not a cost", U.cost_from_openrouter({"usage": {"cost": "x"}}), None)
truthy("record() prefers it", "cost_usd if cost_usd is not None" in A)
truthy("  and the recorder passes it", "cost_usd=_usage.cost_from_openrouter(payload)" in P)
# The table is still there for calls that arrive without a cost.
check("a model in the table is still priced from it",
      U.cost_of("google/gemini-2.5-flash-image", 0, 0, 1), 0.039)
check("a model in NEITHER is unknown, not free",
      U.cost_of("some/model-nobody-has-heard-of", 0, 0, 1), None)

print("\n=== which product the spend was for ===")
truthy("the sku is read from the request", 'sku = str((_rq.args.get("sku")' in D)
truthy("  including a POST body", 'b.get("sku")' in D)
truthy("  in ONE place rather than in each of fourteen routes",
       "a per-route line is" in D)
truthy("and it is passed to the context", "sku=sku)" in D)

print("\n=== a call that names nothing says where it came from ===")
# "unknown" told nobody which of the fourteen call sites to look at.
truthy("there is a fallback", "def unnamed_feature" in A)
truthy("  naming the request path", "call from %s" in A)
truthy("  and saying so when there is no request", "call outside a request" in A)
truthy("record() uses it", 'str(feature or "") or unnamed_feature()' in A)
truthy("the openrouter recorder uses it", "_usage.unnamed_feature()" in P)
truthy("and it is called a safety net, not a substitute",
       "not a substitute for _feature()" in A)

print("\n=== what the ledger actually holds now ===")
# THE SAME CHECKS, ON A FIXTURE LEDGER. One image generation is pushed through
# the real _post() -> recorder path with the network replaced by a canned
# OpenRouter /images reply (the shape and cost measured live above), so the
# ledger holds exactly what the recorder wrote -- nothing seeded by hand.
try:
    import io
    import urllib.request as _ur
    from domain import ai_providers as AP
    from data import db as _db

    class _Reply(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    _canned = {"data": [{"b64_json": "aGVsbG8="}], "usage": {"cost": 0.04}}
    _real_open = _ur.urlopen
    _ur.urlopen = lambda req, timeout=None: _Reply(json.dumps(_canned).encode("utf-8"))
    try:
        AP.set_usage_context(feature="image: generate", workspace_id="jack_uk",
                             sku="10.99_3Days_B0GGSCK998", config_path=_CFG)
        AP._post("https://openrouter.invalid/api/v1/images",
                 {"openrouter_api_key": "test-placeholder-not-a-key"},
                 {"model": "bytedance-seed/seedream-4.5", "prompt": "x"})
    finally:
        _ur.urlopen = _real_open
    conn = _db.get_db(_CFG)
    check("  the ledger read is the fixture, not the real one",
          os.path.abspath(_db.db_path(_CFG)), os.path.abspath(_DBP))
    n = conn.execute("SELECT COUNT(*) c FROM ai_usage").fetchone()["c"]
    img = conn.execute("SELECT COALESCE(SUM(images),0) i FROM ai_usage").fetchone()["i"]
    gen = conn.execute("SELECT COUNT(*) c FROM ai_usage WHERE feature='image: generate'"
                       ).fetchone()["c"]
    withsku = conn.execute("SELECT COUNT(*) c FROM ai_usage WHERE IFNULL(sku,'')<>''"
                           ).fetchone()["c"]
    priced = conn.execute("SELECT COUNT(*) c FROM ai_usage WHERE kind='image' "
                          "AND cost_usd IS NOT NULL").fetchone()["c"]
    print("  ledger rows: %d   images counted: %d" % (n, img))
    truthy("image generations are in it at last", gen > 0)
    truthy("  and their pictures are counted", img > 0)
    truthy("some rows now name a product", withsku > 0)
    truthy("and at least one image carries a real cost", priced > 0)
except Exception as e:
    # A fixture that cannot be built is a failure, not a skip -- the old
    # "could not read the live ledger" skip is what let this pass silently.
    check("the fixture ledger could be written and read", str(e)[:70], "")

print("\nFAILURES: %d" % len(fails))
for f in fails:
    print("   -", f)
sys.exit(1 if fails else 0)

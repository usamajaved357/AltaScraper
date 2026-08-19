"""What does Amazon's RAW schema say about unit_count? (CLAUDE.md rule 4)

    [E] unit_count Based on the data from '', the 'count' on the field
    '"type.value"' for the attribute 'Unit Count' is not a valid value.
    Please provide a valid value.

We send:

    "unit_count": [{"marketplace_id": "A1F83G8C2ARO7P", "value": 2.0,
                    "type": {"language_tag": "en_GB", "value": "Count"}}]

The CACHED schema is a reduced form -- it records unit_count.type as kind
"text" with enum null, and not one of the 94 cached product types carries an
allowed-values list for it. So the cache cannot answer this, and rule 4 says do
not guess: fetch the raw JSON Amazon actually serves and read it.

Diagnostic only. Calls the live API, writes nothing, changes nothing.

    python probe_unit_count.py [PRODUCT_TYPE] [MARKETPLACE]
"""
import json
import sys

PT = sys.argv[1] if len(sys.argv) > 1 else "MACHINE_LUBRICANT"
MKT = sys.argv[2] if len(sys.argv) > 2 else "UK"

import amazon_listing_generator as G

cfg = json.load(open("config.json", encoding="utf-8"))
creds = G.sp_creds(cfg, MKT)

props, required, raw = G._raw_schema(PT, creds)
print("product type: %s (%s)" % (PT, MKT))
print("properties: %d   required: %d" % (len(props or {}), len(required or [])))

uc = (props or {}).get("unit_count")
print("\n===== RAW unit_count property =====")
print(json.dumps(uc, indent=1)[:5000] if uc else "unit_count NOT in properties")

print("\n===== required? =====")
print("unit_count" in (required or []))

# The other two failures from the same batch, while we have the schema open.
for k in ("capacity", "item_width_height", "non_lithium_battery_packaging"):
    v = (props or {}).get(k)
    print("\n===== %s =====" % k)
    print(("required: %s" % (k in (required or []))))
    print(json.dumps(v, indent=1)[:2500] if v else "not in properties")

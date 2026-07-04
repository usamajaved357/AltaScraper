"""listing/builder.py — Amazon listing payload building.

Phase 5 is extracting the payload builder bottom-up: this module first collects the small
self-contained helpers that build_api_attributes depends on; build_api_attributes itself
(the full-payload assembler) moves here LAST, once all its dependencies live in listing/.
All functions moved verbatim from amazon_listing_generator.py (behaviour unchanged).
"""
import re

# blank-token set used by _is_blank (private to this module)
_NA = {"", "n/a", "na", "none", "null", "-"}


def _is_blank(v) -> bool:
    return v is None or str(v).strip().lower() in _NA


def _truthy(v) -> bool:
    return str(v).strip().lower() in {"yes", "y", "true", "1", "included", "required", "t"}


def _clean_price(val) -> str:
    cleaned = re.sub(r"[^\d.]", "", str(val).split("-")[0])
    try:
        return str(round(float(cleaned), 2))
    except ValueError:
        return ""


def _item_props(field_schema: dict) -> dict:
    items = field_schema.get("items", {})
    return items.get("properties", {}) if isinstance(items, dict) else {}


def _offer(price, mid: str):
    return [{
        "marketplace_id": mid,
        "currency": "GBP",
        "our_price": [{"schedule": [{"value_with_tax": round(float(price), 2)}]}],
    }]


def _fulfillment(qty, handling_days):
    o = {"fulfillment_channel_code": "DEFAULT", "quantity": int(qty)}
    if not _is_blank(handling_days):
        try:
            o["lead_time_to_ship_max_days"] = int(float(str(handling_days)))
        except Exception:
            pass
    return [o]

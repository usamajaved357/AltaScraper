"""Backward-compatibility shim — the real module now lives in domain/brand_listing.py.

Kept during the Phase 2 -> Phase 6 transition so the existing monoliths
(dashboard.py, amazon_listing_generator.py) and older patch scripts can keep
doing `import brand_listing` unchanged. It re-points that name at
domain.brand_listing so there is exactly ONE module object in memory.
Delete this file once nothing imports `brand_listing` from the project root.
"""
import sys
import domain.brand_listing as _module

sys.modules[__name__] = _module

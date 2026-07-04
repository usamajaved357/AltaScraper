"""Backward-compatibility shim — the real module now lives in domain/miles_import.py.

Kept during the Phase 2 -> Phase 6 transition so the existing monoliths
(dashboard.py, amazon_listing_generator.py) and older patch scripts can keep
doing `import miles_import` unchanged. It re-points that name at
domain.miles_import so there is exactly ONE module object in memory.
Delete this file once nothing imports `miles_import` from the project root.
"""
import sys
import domain.miles_import as _module

sys.modules[__name__] = _module

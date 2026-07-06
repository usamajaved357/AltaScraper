"""Backward-compatibility shim — the real module now lives in domain/unified_export.py.

Kept during the Phase 2 -> Phase 6 transition so the existing monoliths
(dashboard.py, amazon_listing_generator.py) and older patch scripts can keep
doing `import unified_export` unchanged. It re-points that name at
domain.unified_export so there is exactly ONE module object in memory.
Delete this file once nothing imports `unified_export` from the project root.
"""
import sys
import domain.unified_export as _module

sys.modules[__name__] = _module

"""Backward-compatibility shim — the real module now lives in domain/inventory_module.py.

Kept during the Phase 2 -> Phase 6 transition so the existing monoliths
(dashboard.py, amazon_listing_generator.py) and older patch scripts can keep
doing `import inventory_module` unchanged. It re-points that name at
domain.inventory_module so there is exactly ONE module object in memory.
Delete this file once nothing imports `inventory_module` from the project root.
"""
import sys
import domain.inventory_module as _module

sys.modules[__name__] = _module

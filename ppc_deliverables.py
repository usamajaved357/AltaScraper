"""Backward-compatibility shim — the real module now lives in domain/ppc_deliverables.py.

Kept during the Phase 2 -> Phase 6 transition so the existing monoliths
(dashboard.py, amazon_listing_generator.py) and older patch scripts can keep
doing `import ppc_deliverables` unchanged. It re-points that name at
domain.ppc_deliverables so there is exactly ONE module object in memory.
Delete this file once nothing imports `ppc_deliverables` from the project root.
"""
import sys
import domain.ppc_deliverables as _module

sys.modules[__name__] = _module

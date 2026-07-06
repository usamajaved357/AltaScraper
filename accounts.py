"""Backward-compatibility shim — the real module now lives in domain/accounts.py.

Kept during the Phase 2 -> Phase 6 transition so the existing monoliths
(dashboard.py, amazon_listing_generator.py) and older patch scripts can keep
doing `import accounts` unchanged. It re-points that name at domain.accounts so
there is exactly ONE module object in memory (no accidental double-import).
Delete this file once nothing imports `accounts` from the project root anymore.
"""
import sys
import domain.accounts as _module

sys.modules[__name__] = _module

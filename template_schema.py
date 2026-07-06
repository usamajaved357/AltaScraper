"""Backward-compatibility shim — the real module now lives in domain/template_schema.py.

Kept during the Phase 2 -> Phase 6 transition so the existing monoliths
(dashboard.py, amazon_listing_generator.py) and older patch scripts can keep
doing `import template_schema` unchanged. It re-points that name at
domain.template_schema so there is exactly ONE module object in memory.
Delete this file once nothing imports `template_schema` from the project root.
"""
import sys
import domain.template_schema as _module

sys.modules[__name__] = _module

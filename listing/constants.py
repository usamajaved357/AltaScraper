"""listing/constants.py — immutable Amazon marketplace constants.

These identifiers never change at runtime, so they are safe to share by importing.
(Contrast with the engine's MARKETPLACE_ID, which is REASSIGNED when the active
marketplace switches — that one must stay a live module global in the engine, because
an imported copy would go stale after a switch.)
"""

US_MARKETPLACE_ID = "ATVPDKIKX0DER"   # Amazon.com (USA)

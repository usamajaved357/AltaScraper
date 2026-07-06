"""config/constants.py — fixed, non-secret values used across the app (ports, limits, timeouts)."""

# Local development server binding. Hosting (Phase 7) overrides these via env.
HOST = "127.0.0.1"
PORT = 5000

# Auto-fix loop: never preview/repair a single listing more than this many rounds.
MAX_AUTOFIX_ROUNDS = 8

# How long a signed-in session stays valid before another login is required.
SESSION_HOURS = 8

# Default network timeout (seconds) for external API calls.
API_TIMEOUT_SECONDS = 30

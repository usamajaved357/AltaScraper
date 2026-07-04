"""config/settings.py — loads config.json from the project root and validates it.

Plain English: this file reads the app's settings file (config.json), makes sure
the important values are actually present, and hands them to the rest of the app
in one tidy object. If a required value is missing, it stops the app immediately
with a clear message instead of letting a confusing error surface later on.

It never prints or logs the secret values, and config.json itself is git-ignored
so credentials are never committed.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass


# The project root is the folder that contains this config/ package.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.environ.get("CONFIG_PATH", os.path.join(_ROOT, "config.json"))

# Keys config.json MUST contain for the app to function. Missing any of these
# is a hard stop, because nothing downstream can work without them.
REQUIRED_KEYS = (
    "anthropic_api_key",
    "accounts",
    "google_spreadsheet_id",
    "google_service_account_json",
)


class MissingConfigError(RuntimeError):
    """Raised when config.json is absent, unreadable, or missing a required key."""


@dataclass
class Settings:
    """Parsed, validated application settings."""

    raw: dict
    anthropic_api_key: str
    accounts: list
    google_spreadsheet_id: str
    google_service_account_json: str
    app_password: str | None
    secret_key: str

    def get(self, key, default=None):
        """Read any other (non-required) value straight from config.json."""
        return self.raw.get(key, default)


def load_settings(path: str = CONFIG_PATH) -> Settings:
    """Load config.json, validate the required keys, and return a Settings object.

    Raises MissingConfigError with a human-readable message if the file is
    missing, is not valid JSON, or is missing any required key.
    """
    if not os.path.exists(path):
        raise MissingConfigError(
            f"config.json not found at {path}. Place your credentials file here — "
            f"it is git-ignored and must never be committed."
        )

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as e:
        raise MissingConfigError(f"config.json is not valid JSON: {e}") from e

    missing = [k for k in REQUIRED_KEYS if not raw.get(k)]
    if missing:
        raise MissingConfigError(
            "config.json is missing required key(s): " + ", ".join(missing)
        )
    if not isinstance(raw.get("accounts"), list) or not raw["accounts"]:
        raise MissingConfigError("config.json 'accounts' must be a non-empty list.")

    return Settings(
        raw=raw,
        anthropic_api_key=raw["anthropic_api_key"],
        accounts=raw["accounts"],
        google_spreadsheet_id=raw["google_spreadsheet_id"],
        google_service_account_json=raw["google_service_account_json"],
        # Optional: enables the login gate. From env first, then config.json.
        app_password=os.environ.get("APP_PASSWORD") or raw.get("app_password"),
        # Signs the session cookie. Stable value from env/config, else random.
        secret_key=(
            os.environ.get("APP_SECRET_KEY")
            or raw.get("app_secret_key")
            or os.urandom(32).hex()
        ),
    )

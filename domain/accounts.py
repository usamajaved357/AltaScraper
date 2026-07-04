"""
accounts.py
============================================================================
Account model for the listing app. AN ACCOUNT = A WORKSPACE = one Amazon
Seller Central account with its own SP-API credentials. Marketplaces are
switched WITHIN an account (same refresh token, different marketplace_id).

Each account:
  {
    "id":            "account_1",
    "label":         "My Account",
    "lwa_client_id": "amzn1.application-oa2-client....",
    "lwa_client_secret": "...",
    "refresh_token": "...",
    "seller_id":     "",
    "output_spreadsheet_id": "",        # optional per-account sheet
    "marketplaces":  [],                 # auto-detected; [] = detect on load
    "brands":        []
  }

AUTO-MIGRATION: if a config has no "accounts" list, we build one from the
legacy blocks (main sp_api_* -> UK account, us_spapi -> US account) so nothing
breaks. The migrated accounts are written back to config.json once.

This module never logs or returns secret values except where the submit path
explicitly needs them to authenticate.
============================================================================
"""

import json
import os
import re


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "_", str(s or "").lower()).strip("_")[:40] or "account"


def migrate_legacy(cfg: dict) -> list:
    """Build an accounts list from the old sp_api_* / us_spapi blocks."""
    accts = []
    # UK / default (main block)
    if cfg.get("sp_api_client_id") or cfg.get("seller_id"):
        accts.append({
            "id": "jack_uk",
            "label": cfg.get("uk_account_label") or "UK account",
            "lwa_client_id": cfg.get("sp_api_client_id", ""),
            "lwa_client_secret": cfg.get("sp_api_client_secret", ""),
            "refresh_token": cfg.get("sp_api_refresh_token", ""),
            "seller_id": cfg.get("seller_id", ""),
            "output_spreadsheet_id": cfg.get("google_spreadsheet_id", ""),
            "marketplaces": [],
            "brands": [],
        })
    # US (us_spapi block)
    us = cfg.get("us_spapi") or {}
    if us.get("lwa_client_id") or us.get("seller_id"):
        accts.append({
            "id": "sheelady_us",
            "label": cfg.get("us_account_label") or "US account",
            "lwa_client_id": us.get("lwa_client_id", ""),
            "lwa_client_secret": us.get("lwa_client_secret", ""),
            "refresh_token": us.get("refresh_token", ""),
            "seller_id": us.get("seller_id", ""),
            "output_spreadsheet_id": "",
            "marketplaces": [],
            "brands": [],
        })
    return accts


def load_accounts(cfg: dict, config_path: str = None, persist: bool = True) -> list:
    """Return the accounts list, auto-migrating + persisting from legacy if absent."""
    accts = cfg.get("accounts")
    if isinstance(accts, list) and accts:
        return accts
    accts = migrate_legacy(cfg)
    if persist and config_path and accts:
        try:
            raw = json.load(open(config_path, encoding="utf-8"))
            if not raw.get("accounts"):
                raw["accounts"] = accts
                json.dump(raw, open(config_path, "w", encoding="utf-8"),
                          indent=2, ensure_ascii=False)
        except Exception:
            pass
    return accts


def get_account(cfg: dict, account_id: str, config_path: str = None) -> dict:
    for a in load_accounts(cfg, config_path):
        if a.get("id") == account_id:
            return a
    return {}


def account_creds(account: dict) -> dict:
    """SP-API creds for an account, in the shape the generator expects."""
    return {
        "lwa_app_id": account.get("lwa_client_id", "") or account.get("lwa_app_id", ""),
        "lwa_client_secret": account.get("lwa_client_secret", ""),
        "refresh_token": account.get("refresh_token", ""),
        "seller_id": account.get("seller_id", ""),
    }


def save_account(cfg: dict, config_path: str, account: dict) -> dict:
    """Add or update an account by id. Returns the saved account."""
    raw = json.load(open(config_path, encoding="utf-8"))
    accts = raw.get("accounts")
    if not isinstance(accts, list):
        accts = migrate_legacy(cfg)
    if not account.get("id"):
        account["id"] = _slug(account.get("label", "account"))
    found = False
    for i, a in enumerate(accts):
        if a.get("id") == account["id"]:
            accts[i] = {**a, **account}
            found = True
            break
    if not found:
        accts.append(account)
    raw["accounts"] = accts
    json.dump(raw, open(config_path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    return account


def delete_account(cfg: dict, config_path: str, account_id: str) -> bool:
    raw = json.load(open(config_path, encoding="utf-8"))
    accts = raw.get("accounts") or []
    new = [a for a in accts if a.get("id") != account_id]
    raw["accounts"] = new
    json.dump(raw, open(config_path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    return len(new) != len(accts)


# marketplace_id lookup (used until live auto-detect lands in step 2)
MARKETPLACE_IDS = {
    "US": "ATVPDKIKX0DER", "CA": "A2EUQ1WTGCTBG2", "MX": "A1AM78C64UM0Y8",
    "BR": "A2Q3Y263D00KWC",
    "UK": "A1F83G8C2ARO7P", "DE": "A1PA6795UKMFR9", "FR": "A13V1IB3VIYZZH",
    "IT": "APJ6JRA9NG5V4", "ES": "A1RKKUPIHCS9HS", "NL": "A1805IZSGTT6HS",
    "SE": "A2NODRKZP88ZB9", "PL": "A1C3SOZRARQ6R3", "BE": "AMEN7PMS3EDWL",
    "TR": "A33AVAJ2PDY3EV", "AE": "A2VIGQ35RCS4UG", "SA": "A17E79C6D8DWNP",
    "EG": "ARBP9OOSHTCHU", "IN": "A21TJRUUN4KGV",
    "JP": "A1VC38T7YXB528", "AU": "A39IBJ37TRP1C6", "SG": "A19VAU5U5O7RUS",
}


def marketplace_id(code: str) -> str:
    return MARKETPLACE_IDS.get(str(code or "").upper(), "")

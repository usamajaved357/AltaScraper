#!/bin/sh
# Seeds config.json / service_account.json onto the persistent disk from
# Render Secret Files on first boot, then starts the dashboard.
#
# Normal operation: the app reads/writes CONFIG_PATH (/data/config.json) on the
# persistent disk, so accounts you add in the app UI auto-save and survive
# redeploys -- you do NOT need to edit config manually.
#
# RESEED_CONFIG=1: force-overwrite CONFIG_PATH from the Secret File.
#
# This USED to overwrite on EVERY boot while the variable was set, silently wiping the
# sheets, tabs and accounts you had since saved in the UI -- which looked like "the app
# keeps forgetting my Nestwell sheets". It is now IDEMPOTENT: the checksum of the Secret
# File is recorded after each seed, and we only reseed when that checksum CHANGES. So
# leaving RESEED_CONFIG=1 set is harmless, and uploading a genuinely new Secret File
# still applies exactly once. A timestamped backup is taken before any overwrite.
set -e

CONFIG_PATH="${CONFIG_PATH:-/data/config.json}"
CONFIG_DIR=$(dirname "$CONFIG_PATH")
SEED_SRC=/etc/secrets/config.json
SEED_STAMP="$CONFIG_DIR/.config_seed_sha"
mkdir -p "$CONFIG_DIR"

# Hash with python, not sha256sum: this script ends in `exec python`, so python is
# guaranteed, whereas a missing coreutils would leave _seed_sha empty and silently turn
# "the secret changed" into "never reseed" -- a genuinely new Secret File would then
# never be applied, with no error.
_hash() {
    python -c "import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" "$1" 2>/dev/null || true
}

_seed_sha=""
if [ -f "$SEED_SRC" ]; then
    _seed_sha=$(_hash "$SEED_SRC")
fi
_last_sha=""
if [ -f "$SEED_STAMP" ]; then
    _last_sha=$(cat "$SEED_STAMP")
fi

# Seed when: there is no config at all, OR the Secret File genuinely changed while
# RESEED_CONFIG=1. Never on an unchanged Secret File -- that is what clobbered the UI.
_do_seed=0
if [ ! -f "$CONFIG_PATH" ]; then
    _do_seed=1
elif [ "${RESEED_CONFIG:-}" = "1" ] && [ -z "$_seed_sha" ]; then
    # Cannot tell whether the secret changed. Refuse to overwrite live data on a guess.
    echo "RESEED_CONFIG=1 but the Secret File could not be hashed — refusing to overwrite $CONFIG_PATH. Fix the secret file, or delete $CONFIG_PATH to force a reseed."
elif [ "${RESEED_CONFIG:-}" = "1" ] && [ "$_seed_sha" != "$_last_sha" ]; then
    _do_seed=1
elif [ "${RESEED_CONFIG:-}" = "1" ]; then
    echo "RESEED_CONFIG=1 but /etc/secrets/config.json is unchanged since the last seed -- keeping the config on disk (your saved accounts/sheets are safe)."
fi

if [ "$_do_seed" = "1" ]; then
    if [ -f "$SEED_SRC" ]; then
        if [ -f "$CONFIG_PATH" ]; then
            _bak="$CONFIG_PATH.bak-$(date +%s)"
            cp "$CONFIG_PATH" "$_bak"
            echo "Backed up current config to $_bak before overwriting."
        fi
        cp "$SEED_SRC" "$CONFIG_PATH"
        [ -n "$_seed_sha" ] && printf '%s' "$_seed_sha" > "$SEED_STAMP"
        echo "Seeded $CONFIG_PATH from $SEED_SRC (RESEED_CONFIG=${RESEED_CONFIG:-unset})"
    else
        echo "WARNING: $CONFIG_PATH not found and no seed at $SEED_SRC — the app will fail to start."
    fi
else
    echo "Using existing $CONFIG_PATH from the persistent disk."
fi

# Say, out loud at boot, which sheet/tab each account is bound to. When the sheets
# "revert", this line is the evidence of what the app actually loaded.
python - "$CONFIG_PATH" <<'PY' || true
import json, sys
try:
    cfg = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception as e:
    print(f"  (could not read config for the account summary: {e})"); raise SystemExit(0)
accts = cfg.get("accounts", [])
print(f"  {len(accts)} account(s) loaded from {sys.argv[1]}:")
for a in accts:
    print(f"    {a.get('id','?'):<20} out_sheet={str(a.get('output_spreadsheet_id') or '(none)')[:14]:<16}"
          f" out_tab_gid={str(a.get('output_tab_gid') or '(NONE)'):<12}"
          f" in_tab_gid={str(a.get('input_tab_gid') or '(NONE)')}")
PY

SERVICE_ACCOUNT_TARGET="$CONFIG_DIR/service_account.json"
if [ ! -f "$SERVICE_ACCOUNT_TARGET" ] && [ -f /etc/secrets/service_account.json ]; then
    cp /etc/secrets/service_account.json "$SERVICE_ACCOUNT_TARGET"
    echo "Seeded $SERVICE_ACCOUNT_TARGET from /etc/secrets/service_account.json"
fi

mkdir -p "$CONFIG_DIR/media" "$CONFIG_DIR/ppc_out" "$CONFIG_DIR/inventory_out" \
         "$CONFIG_DIR/brands" "$CONFIG_DIR/miles_templates" "$CONFIG_DIR/autofix_logs"

exec python dashboard.py

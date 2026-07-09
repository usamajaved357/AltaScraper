#!/bin/sh
# Seeds config.json / service_account.json onto the persistent disk from
# Render Secret Files on first boot, then starts the dashboard.
#
# Normal operation: the app reads/writes CONFIG_PATH (/data/config.json) on the
# persistent disk, so accounts you add in the app UI auto-save and survive
# redeploys -- you do NOT need to edit config manually.
#
# RESEED_CONFIG=1: force-overwrite CONFIG_PATH from the Secret File on this boot
# (for pushing a whole new config without the Render Shell `rm` dance). It first
# BACKS UP the current config to CONFIG_PATH.bak-<timestamp> so nothing is lost.
# Set it, redeploy once, then UNSET it (otherwise every deploy re-overwrites and
# clobbers accounts you've since added in the UI).
set -e

CONFIG_PATH="${CONFIG_PATH:-/data/config.json}"
CONFIG_DIR=$(dirname "$CONFIG_PATH")
mkdir -p "$CONFIG_DIR"

if [ "${RESEED_CONFIG:-}" = "1" ] && [ -f "$CONFIG_PATH" ]; then
    _bak="$CONFIG_PATH.bak-$(date +%s)"
    cp "$CONFIG_PATH" "$_bak"
    echo "RESEED_CONFIG=1: backed up current config to $_bak before overwriting."
fi

if [ ! -f "$CONFIG_PATH" ] || [ "${RESEED_CONFIG:-}" = "1" ]; then
    if [ -f /etc/secrets/config.json ]; then
        cp /etc/secrets/config.json "$CONFIG_PATH"
        echo "Seeded $CONFIG_PATH from /etc/secrets/config.json (RESEED_CONFIG=${RESEED_CONFIG:-unset})"
    else
        echo "WARNING: $CONFIG_PATH not found and no seed at /etc/secrets/config.json — the app will fail to start."
    fi
fi

SERVICE_ACCOUNT_TARGET="$CONFIG_DIR/service_account.json"
if [ ! -f "$SERVICE_ACCOUNT_TARGET" ] && [ -f /etc/secrets/service_account.json ]; then
    cp /etc/secrets/service_account.json "$SERVICE_ACCOUNT_TARGET"
    echo "Seeded $SERVICE_ACCOUNT_TARGET from /etc/secrets/service_account.json"
fi

mkdir -p "$CONFIG_DIR/media" "$CONFIG_DIR/ppc_out" "$CONFIG_DIR/inventory_out" \
         "$CONFIG_DIR/brands" "$CONFIG_DIR/miles_templates" "$CONFIG_DIR/autofix_logs"

exec python dashboard.py

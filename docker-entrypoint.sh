#!/bin/sh
# Seeds config.json / service_account.json onto the persistent disk from
# Render Secret Files on first boot, then starts the dashboard. Safe to
# re-run on every boot: it only copies files that don't already exist.
set -e

CONFIG_PATH="${CONFIG_PATH:-/data/config.json}"
CONFIG_DIR=$(dirname "$CONFIG_PATH")
mkdir -p "$CONFIG_DIR"

if [ ! -f "$CONFIG_PATH" ]; then
    if [ -f /etc/secrets/config.json ]; then
        cp /etc/secrets/config.json "$CONFIG_PATH"
        echo "Seeded $CONFIG_PATH from /etc/secrets/config.json"
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
         "$CONFIG_DIR/brands" "$CONFIG_DIR/miles_templates"

exec python dashboard.py

#!/bin/bash
# Uninstall claude-bar: stop daemon, clean up hooks and state.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BINARY="$SCRIPT_DIR/target/release/claude-bar"

# 1. Stop daemon
PLIST_LABEL="com.claude.claude-bar-daemon"
PLIST="$HOME/Library/LaunchAgents/$PLIST_LABEL.plist"

launchctl bootout "gui/$(id -u)/$PLIST_LABEL" 2>/dev/null || true
rm -f "$PLIST"
echo "Stopped and removed daemon: $PLIST_LABEL"

# 2. Remove hook config from settings.json
SETTINGS="$HOME/.claude/settings.json"
if [[ -f "$SETTINGS" ]]; then
    if [[ -x "$BINARY" ]]; then
        "$BINARY" hooks-uninstall --settings "$SETTINGS"
        echo "Removed hook config from settings"
    else
        echo "Warning: $BINARY not found, skipping hook cleanup in settings"
    fi
fi

# 3. Clean up state files
rm -f "$HOME/.claude/claude-bar.sock"
rm -rf "$HOME/.claude/claude-bar"
echo "Cleaned up state files"
echo "Note: You may remove any leftover .claude-bar/ directories from project folders"

echo "Uninstallation complete."

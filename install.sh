#!/bin/bash
# Install ClaudeBar symlinks into the SwiftBar plugins directory.
# Usage: ./install.sh [SLOTS]   (default: 5)

set -euo pipefail

SLOTS=${1:-5}
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

PLUGIN_DIR=$(defaults read com.ameba.SwiftBar PluginDirectory 2>/dev/null) || {
    echo "Error: Could not read SwiftBar plugin directory."
    echo "Is SwiftBar installed and configured?"
    exit 1
}

# Expand ~ if present
PLUGIN_DIR="${PLUGIN_DIR/#\~/$HOME}"

if [[ ! -d "$PLUGIN_DIR" ]]; then
    echo "Error: Plugin directory does not exist: $PLUGIN_DIR"
    exit 1
fi

# Warn if repo is inside plugin dir without dot-prefix (SwiftBar would execute all files)
case "$SCRIPT_DIR" in
    "$PLUGIN_DIR"/[!.]*)
        echo "Warning: This repo is inside the SwiftBar plugin directory without a dot-prefix."
        echo "SwiftBar will try to execute all files. Rename the directory to start with '.':"
        echo "  mv \"$SCRIPT_DIR\" \"$PLUGIN_DIR/.$(basename "$SCRIPT_DIR")\""
        exit 1
        ;;
esac

# Clean up old formats
rm -f "$PLUGIN_DIR"/ClaudeBar.*.sh
rm -f "$PLUGIN_DIR"/ClaudeBar-*.sh

# Create new symlinks
for i in $(seq 1 "$SLOTS"); do
    ln -sf "$SCRIPT_DIR/src/ClaudeBar.sh" "$PLUGIN_DIR/ClaudeBar-$i.2s.sh"
done

# Install SessionStart hook for TTY → transcript mapping
HOOK_CMD="$SCRIPT_DIR/src/session-track.sh"

# Merge hook config into ~/.claude/settings.json
SETTINGS="$HOME/.claude/settings.json"
python3 -c "
import json, os, sys

path = '$SETTINGS'
cfg = {}
if os.path.exists(path):
    with open(path) as f:
        cfg = json.load(f)

hook_cmd = '$HOOK_CMD'
new_hook = {'type': 'command', 'command': hook_cmd}
new_matcher = {'hooks': [new_hook]}

hooks = cfg.setdefault('hooks', {})
matchers = hooks.setdefault('SessionStart', [])

# Avoid duplicates
for m in matchers:
    for h in m.get('hooks', []):
        if h.get('command', '').endswith('session-track.sh'):
            sys.exit(0)

matchers.append(new_matcher)

with open(path, 'w') as f:
    json.dump(cfg, f, indent=2)
    f.write('\n')
"

echo "Installed $SLOTS slot(s) in $PLUGIN_DIR"
ls -la "$PLUGIN_DIR"/ClaudeBar-*.sh
echo "Installed SessionStart hook: $HOOK_CMD"

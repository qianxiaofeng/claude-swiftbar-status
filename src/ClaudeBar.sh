#!/bin/zsh
# <swiftbar.hideAbout>true</swiftbar.hideAbout>
# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>
# <swiftbar.hideDisablePlugin>true</swiftbar.hideDisablePlugin>
#
# Each symlink (ClaudeBar-N.2s.sh) monitors the Nth Claude Code session.
# Empty output when no session exists → icon auto-hides.

# Resolve symlinks so HELPER works when SwiftBar runs a symlinked plugin
SELF="$0"
ORIG="$SELF"
if [[ -L "$SELF" ]]; then
    LINK="$(readlink "$SELF")"
    [[ "$LINK" != /* ]] && LINK="$(dirname "$SELF")/$LINK"
    SELF="$LINK"
fi
SCRIPT_DIR="$(cd "$(dirname "$SELF")" && pwd)"
HELPER="$SCRIPT_DIR/focus-iterm.sh"

# Extract slot number from filename: ClaudeBar-N.2s.sh → N
# If no slot number found (running directly), default to 1
SLOT_NUM=1
BASENAME="$(basename "$ORIG")"
if [[ "$BASENAME" =~ ^ClaudeBar-([0-9]+)\. ]]; then
    SLOT_NUM=${match[1]}
fi

# sfconfig base64: {"renderingMode":"Palette","colors":["<hex>"]}
SF_GREEN=eyJyZW5kZXJpbmdNb2RlIjoiUGFsZXR0ZSIsImNvbG9ycyI6WyIjMzJENzRCIl19    # #32D74B
SF_ORANGE=eyJyZW5kZXJpbmdNb2RlIjoiUGFsZXR0ZSIsImNvbG9ycyI6WyIjRkY5RjBBIl19   # #FF9F0A
SF_GRAY=eyJyZW5kZXJpbmdNb2RlIjoiUGFsZXR0ZSIsImNvbG9ycyI6WyIjOEU4RTkzIl19     # #8E8E93

# 1) Get all iTerm2 session TTYs in tab order (window → tab → session)
ITERM_TTYS=("${(@f)$(osascript -e '
tell application "iTerm2"
    set out to ""
    repeat with w in windows
        tell w
            repeat with t in tabs
                repeat with s in sessions of t
                    set out to out & (tty of s) & linefeed
                end repeat
            end repeat
        end tell
    end repeat
    return out
end tell
' 2>/dev/null)}")

# 2) Map claude PIDs by their TTY
typeset -A PID_BY_TTY
for p in $(pgrep -x claude 2>/dev/null); do
    t="/dev/$(ps -o tty= -p "$p" 2>/dev/null | xargs)"
    [[ "$t" != "/dev/" ]] && PID_BY_TTY[$t]=$p
done

# 3) Filter to TTYs running Claude, preserving iTerm tab order
CLAUDE_TTYS=()
for t in "${ITERM_TTYS[@]}"; do
    [[ -n "${PID_BY_TTY[$t]}" ]] && CLAUDE_TTYS+=("$t")
done

# If the Nth session doesn't exist, output nothing → icon hides
if (( ${#CLAUDE_TTYS[@]} < SLOT_NUM )); then
    exit 0
fi

# SwiftBar renders menu bar icons right-to-left (slot1=rightmost),
# but users expect left-to-right = tab order. Reverse the index.
TTY_DEV="${CLAUDE_TTYS[${#CLAUDE_TTYS[@]} - SLOT_NUM + 1]}"
PID="${PID_BY_TTY[$TTY_DEV]}"
CWD=$(lsof -p "$PID" -Fn 2>/dev/null | grep '^n/' | head -1 | cut -c2-)
PROJECT_HASH=$(echo "$CWD" | sed 's|[/_]|-|g')
# Resolve transcript: state file → fallback (exclude transcripts claimed by other sessions)
TTY_SHORT="${TTY_DEV#/dev/}"
ACTIVE_CLAUDE_TTYS=""
for _ct in "${CLAUDE_TTYS[@]}"; do
    ACTIVE_CLAUDE_TTYS="${ACTIVE_CLAUDE_TTYS:+$ACTIVE_CLAUDE_TTYS,}${_ct#/dev/}"
done
TRANSCRIPT=$(/usr/bin/python3 "$SCRIPT_DIR/resolve_transcript.py" \
    "$TTY_SHORT" "$HOME/.claude/swiftbar" "$HOME/.claude/projects/$PROJECT_HASH" "$ACTIVE_CLAUDE_TTYS")
if [[ -n "$TRANSCRIPT" && -f "$TRANSCRIPT" ]]; then
    FILE_AGE=$(( $(date +%s) - $(stat -f %m "$TRANSCRIPT") ))
else
    TRANSCRIPT=""
    FILE_AGE=0
fi

# Debug: log slot→TTY→transcript mapping for diagnostics
DEBUG_LOG="$HOME/.claude/swiftbar/debug.log"
{
    echo "$(date '+%H:%M:%S') slot=$SLOT_NUM tty=$TTY_DEV pid=$PID cwd=$(basename "$CWD") transcript=$(basename "$TRANSCRIPT") age=$FILE_AGE"
} >> "$DEBUG_LOG" 2>/dev/null
if [[ -f "$DEBUG_LOG" ]] && (( $(wc -l < "$DEBUG_LOG") > 200 )); then
    tail -100 "$DEBUG_LOG" > "$DEBUG_LOG.tmp" && mv "$DEBUG_LOG.tmp" "$DEBUG_LOG"
fi

/usr/bin/python3 - "$HELPER" "$SF_GREEN" "$SF_ORANGE" "$SF_GRAY" \
    "$TTY_DEV" "$CWD" "$TRANSCRIPT" "$FILE_AGE" << 'PYEOF'
import json, sys, os

helper = sys.argv[1]
sf_green = sys.argv[2]
sf_orange = sys.argv[3]
sf_gray = sys.argv[4]
tty = sys.argv[5]
cwd = sys.argv[6]
transcript = sys.argv[7]
file_age = int(sys.argv[8])

STATUS_MAP = {
    "active":   ("bolt.fill",                   sf_green),
    "pending":  ("exclamationmark.triangle.fill", sf_orange),
    "idle":     ("moon.fill",                    sf_gray),
}
STATUS_LABEL = {"active": "Running", "pending": "Needs input", "idle": "Idle"}

def check_pending_tool(transcript):
    if not transcript:
        return False
    pending = False
    try:
        with open(transcript, 'rb') as f:
            f.seek(0, 2)
            size = f.tell()
            chunk = min(size, 65536)
            f.seek(size - chunk)
            lines = f.read().decode('utf-8', errors='replace').strip().split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except Exception:
                continue
            t = e.get('type', '')
            msg = e.get('message', {})
            role = msg.get('role', '')
            content = msg.get('content', [])
            if t == 'assistant' and role == 'assistant':
                if isinstance(content, list):
                    types = [c.get('type') for c in content if isinstance(c, dict)]
                    if 'tool_use' in types:
                        pending = True
            elif t == 'user' and role == 'user' and isinstance(content, list):
                types = [c.get('type') for c in content if isinstance(c, dict)]
                if 'tool_result' in types:
                    pending = False
    except Exception:
        pass
    return pending

# Determine status
if not transcript:
    status = "active"
elif file_age < 5:
    status = "active"
elif check_pending_tool(transcript):
    status = "pending"
else:
    status = "idle"

click = f"bash={helper} param1={tty} terminal=false"
project = os.path.basename(cwd) if cwd else ""
img, cfg = STATUS_MAP[status]

# Menu bar: status icon, click to focus
print(f"| sfimage={img} sfconfig={cfg} sfsize=15 {click}")

# Dropdown
print("---")
label = project if project else "Claude"
print(f"{label} | sfimage={img} sfconfig={cfg} {click}")
print(f"--{STATUS_LABEL[status]} | sfimage={img} sfconfig={cfg} size=12")
PYEOF

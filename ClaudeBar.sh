#!/bin/zsh
# <swiftbar.hideAbout>true</swiftbar.hideAbout>
# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>
# <swiftbar.hideDisablePlugin>true</swiftbar.hideDisablePlugin>
#
# Monitors up to MAX_SESSIONS Claude Code instances.
# Menu bar shows the most urgent status; dropdown lists each session.

MAX_SESSIONS=3
# Resolve symlinks so HELPER works when SwiftBar runs a symlinked plugin
SELF="$0"
if [[ -L "$SELF" ]]; then
    LINK="$(readlink "$SELF")"
    [[ "$LINK" != /* ]] && LINK="$(dirname "$SELF")/$LINK"
    SELF="$LINK"
fi
SCRIPT_DIR="$(cd "$(dirname "$SELF")" && pwd)"
HELPER="$SCRIPT_DIR/focus-iterm.sh"

# sfconfig base64: {"renderingMode":"Palette","colors":["<hex>"]}
SF_DARK=eyJyZW5kZXJpbmdNb2RlIjoiUGFsZXR0ZSIsImNvbG9ycyI6WyIjNDg0ODRBIl19
SF_GREEN=eyJyZW5kZXJpbmdNb2RlIjoiUGFsZXR0ZSIsImNvbG9ycyI6WyIjMzJENzRCIl19
SF_ORANGE=eyJyZW5kZXJpbmdNb2RlIjoiUGFsZXR0ZSIsImNvbG9ycyI6WyIjRkY5RjBBIl19
SF_GRAY=eyJyZW5kZXJpbmdNb2RlIjoiUGFsZXR0ZSIsImNvbG9ycyI6WyIjNjM2MzY2Il19

PIDS=($(pgrep -x claude 2>/dev/null | sort -n))
PID_COUNT=${#PIDS[@]}

# Gather per-session info: 4 positional args each (tty, cwd, transcript, file_age)
ARGS=()
for i in $(seq 1 $MAX_SESSIONS); do
    if (( PID_COUNT < i )); then
        ARGS+=("" "" "" "0")
    else
        PID=${PIDS[$i]}
        TTY_DEV="/dev/$(ps -o tty= -p "$PID" 2>/dev/null | xargs)"
        CWD=$(lsof -p "$PID" -Fn 2>/dev/null | grep '^n/' | head -1 | cut -c2-)
        PROJECT_HASH=$(echo "$CWD" | sed 's|[/_]|-|g')
        TRANSCRIPT=$(ls -t "$HOME/.claude/projects/$PROJECT_HASH"/*.jsonl 2>/dev/null | head -1)
        if [[ -n "$TRANSCRIPT" ]]; then
            FILE_AGE=$(( $(date +%s) - $(stat -f %m "$TRANSCRIPT") ))
        else
            FILE_AGE=0
        fi
        ARGS+=("$TTY_DEV" "$CWD" "$TRANSCRIPT" "$FILE_AGE")
    fi
done

/usr/bin/python3 - "$HELPER" "$SF_DARK" "$SF_GREEN" "$SF_ORANGE" "$SF_GRAY" "$MAX_SESSIONS" "${ARGS[@]}" << 'PYEOF'
import json, sys, os

helper = sys.argv[1]
sf_dark = sys.argv[2]
sf_green = sys.argv[3]
sf_orange = sys.argv[4]
sf_gray = sys.argv[5]
max_sessions = int(sys.argv[6])

STATUS_MAP = {
    "inactive": ("circle.dashed", sf_dark),
    "active":   ("circle.fill",   sf_green),
    "pending":  ("exclamationmark.circle.fill", sf_orange),
    "idle":     ("circle.fill",   sf_gray),
}
PRIORITY = {"inactive": 0, "idle": 1, "active": 2, "pending": 3}

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

# Determine each session's status
sessions = []
idx = 7
for i in range(max_sessions):
    tty = sys.argv[idx]
    cwd = sys.argv[idx + 1]
    transcript = sys.argv[idx + 2]
    file_age = int(sys.argv[idx + 3])
    idx += 4

    click = f"bash={helper} terminal=false"
    if tty:
        click = f"bash={helper} param1={tty} terminal=false"

    if not tty:
        status = "inactive"
    elif not transcript:
        status = "active"
    elif file_age < 15:
        status = "active"
    elif check_pending_tool(transcript):
        status = "pending"
    else:
        status = "idle"

    project = os.path.basename(cwd) if cwd else ""
    sessions.append((status, click, project))

# Menu bar: show the most urgent session's icon
best_idx = max(range(max_sessions), key=lambda i: PRIORITY[sessions[i][0]])
best_status, best_click, _ = sessions[best_idx]
img, cfg = STATUS_MAP[best_status]
print(f"| sfimage={img} sfconfig={cfg} sfsize=14 {best_click}")

# Dropdown
print("---")
for i, (status, click, project) in enumerate(sessions):
    img, cfg = STATUS_MAP[status]
    label = f"Session {i + 1}"
    if project:
        label += f": {project}"
    print(f"{label} | sfimage={img} sfconfig={cfg} {click}")
PYEOF

#!/bin/sh
# SessionStart hook: maps TTY → transcript path for SwiftBar slot isolation.
# Called by Claude Code with JSON on stdin containing session_id + transcript_path.

# Walk up the process tree to find the claude process and its TTY
PID=$PPID
TTY=""
while [ "$PID" != "1" ] && [ -n "$PID" ]; do
    NAME=$(ps -o comm= -p "$PID" 2>/dev/null)
    if [ "$NAME" = "claude" ]; then
        TTY=$(ps -o tty= -p "$PID" 2>/dev/null | xargs)
        break
    fi
    PID=$(ps -o ppid= -p "$PID" 2>/dev/null | xargs)
done

# No TTY found or detached — nothing to do
[ -z "$TTY" ] || [ "$TTY" = "??" ] && exit 0

STATE_DIR="$HOME/.claude/swiftbar"
mkdir -p "$STATE_DIR"

# Read hook JSON from stdin and write state file
python3 -c "
import json, sys
d = json.load(sys.stdin)
with open('$STATE_DIR/session-$TTY.json', 'w') as f:
    json.dump({'session_id': d.get('session_id',''), 'transcript_path': d.get('transcript_path','')}, f)
"

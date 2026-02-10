"""Resolve the correct transcript file for a given TTY's Claude session.

Used by ClaudeBar.sh to map each slot to its own transcript, even when
multiple sessions share the same project directory.
"""

import json, os, glob


def resolve(tty_short: str, state_dir: str, project_dir: str,
            active_ttys: set[str]) -> str:
    """Return the transcript path for *tty_short*, or '' if none found.

    1) Use this TTY's state file if its transcript still exists.
    2) Otherwise fall back to the most-recently-modified transcript that
       is NOT claimed by another *active* session's state file.
    """
    # 1) Try this TTY's state file
    sf = os.path.join(state_dir, f"session-{tty_short}.json")
    if os.path.isfile(sf):
        try:
            with open(sf) as fh:
                tp = json.load(fh).get("transcript_path", "")
            if tp and os.path.isfile(tp):
                return tp
        except Exception:
            pass

    # 2) Collect transcripts claimed by OTHER active sessions
    claimed: set[str] = set()
    for f in glob.glob(os.path.join(state_dir, "session-*.json")):
        t = os.path.basename(f)[len("session-"):-len(".json")]
        if t == tty_short or t not in active_ttys:
            continue
        try:
            with open(f) as fh:
                ct = json.load(fh).get("transcript_path", "")
            if ct and os.path.isfile(ct):
                claimed.add(ct)
        except Exception:
            pass

    # Pick the most recent unclaimed transcript
    for t in sorted(
        glob.glob(os.path.join(project_dir, "*.jsonl")),
        key=lambda f: os.path.getmtime(f),
        reverse=True,
    ):
        if t not in claimed:
            return t

    return ""


if __name__ == "__main__":
    import sys
    tty_short = sys.argv[1]
    state_dir = sys.argv[2]
    project_dir = sys.argv[3]
    active_ttys = set(sys.argv[4].split(",")) if sys.argv[4] else set()
    print(resolve(tty_short, state_dir, project_dir, active_ttys))

"""Tests for tab→slot mapping logic.

The core mapping in ClaudeBar.sh:
  1. ITERM_TTYS: all iTerm2 TTYs in tab order (AppleScript)
  2. PID_BY_TTY: associative array of TTY→PID (from pgrep)
  3. CLAUDE_TTYS: filtered ITERM_TTYS keeping only those with a Claude PID
  4. SLOT_NUM indexes into CLAUDE_TTYS (1-based)

These tests run actual zsh snippets to verify the filtering/indexing logic.
"""

import subprocess
import unittest


def run_slot_mapping(iterm_ttys: list[str], claude_ttys_set: list[str],
                     slot_num: int) -> dict:
    """Run the zsh slot mapping logic and return parsed results.

    Args:
        iterm_ttys: TTYs in iTerm tab order (e.g. ["/dev/ttys009", "/dev/ttys000"])
        claude_ttys_set: TTYs that have a Claude PID (e.g. ["/dev/ttys009", "/dev/ttys000"])
        slot_num: 1-based slot number
    Returns:
        dict with keys: claude_ttys (list), tty_dev (str or ""), count (int)
    """
    # Build zsh script that mirrors ClaudeBar.sh logic
    iterm_arr = " ".join(f'"{t}"' for t in iterm_ttys)
    claude_pids = " ".join(f'PID_BY_TTY[{t}]={i+1000}'
                           for i, t in enumerate(claude_ttys_set))

    script = f"""
ITERM_TTYS=({iterm_arr})

typeset -A PID_BY_TTY
{claude_pids}

CLAUDE_TTYS=()
for t in "${{ITERM_TTYS[@]}}"; do
    [[ -n "${{PID_BY_TTY[$t]}}" ]] && CLAUDE_TTYS+=("$t")
done

SLOT_NUM={slot_num}

echo "count=${{#CLAUDE_TTYS[@]}}"
for i in {{1..${{#CLAUDE_TTYS[@]}}}}; do
    echo "claude_tty_$i=${{CLAUDE_TTYS[$i]}}"
done
if (( ${{#CLAUDE_TTYS[@]}} >= SLOT_NUM )); then
    echo "tty_dev=${{CLAUDE_TTYS[${{#CLAUDE_TTYS[@]}} - SLOT_NUM + 1]}}"
else
    echo "tty_dev="
fi
"""
    result = subprocess.run(
        ["zsh", "-c", script], capture_output=True, text=True, timeout=5
    )
    if result.returncode != 0:
        raise RuntimeError(f"zsh failed: {result.stderr}")

    out = {}
    claude_ttys = []
    for line in result.stdout.strip().split("\n"):
        k, _, v = line.partition("=")
        if k == "count":
            out["count"] = int(v)
        elif k.startswith("claude_tty_"):
            claude_ttys.append(v)
        elif k == "tty_dev":
            out["tty_dev"] = v
    out["claude_ttys"] = claude_ttys
    return out


class TestSlotMapping(unittest.TestCase):
    """Verify reversed slot indexing: slot1=rightmost icon=last tab, slotN=leftmost=first tab.

    SwiftBar renders menu bar icons right-to-left (ClaudeBar-1 is rightmost).
    Users expect left-to-right = tab order. So we reverse the index:
      tty_dev = CLAUDE_TTYS[count - SLOT_NUM + 1]
    """

    def test_two_sessions_reversed(self):
        """Two Claude tabs → slot1(right)=tab2, slot2(left)=tab1."""
        r1 = run_slot_mapping(
            iterm_ttys=["/dev/ttys009", "/dev/ttys000", "/dev/ttys002"],
            claude_ttys_set=["/dev/ttys009", "/dev/ttys000"],
            slot_num=1,
        )
        self.assertEqual(r1["claude_ttys"], ["/dev/ttys009", "/dev/ttys000"])
        # slot1 (rightmost icon) → last Claude tab (ttys000)
        self.assertEqual(r1["tty_dev"], "/dev/ttys000")

        r2 = run_slot_mapping(
            iterm_ttys=["/dev/ttys009", "/dev/ttys000", "/dev/ttys002"],
            claude_ttys_set=["/dev/ttys009", "/dev/ttys000"],
            slot_num=2,
        )
        # slot2 (leftmost icon) → first Claude tab (ttys009)
        self.assertEqual(r2["tty_dev"], "/dev/ttys009")

    def test_gap_in_tabs(self):
        """Claude in tab1 and tab3 → slot1(right)=tab3, slot2(left)=tab1."""
        r = run_slot_mapping(
            iterm_ttys=["/dev/ttys001", "/dev/ttys002", "/dev/ttys003"],
            claude_ttys_set=["/dev/ttys001", "/dev/ttys003"],
            slot_num=1,
        )
        self.assertEqual(r["claude_ttys"], ["/dev/ttys001", "/dev/ttys003"])
        self.assertEqual(r["tty_dev"], "/dev/ttys003")

    def test_single_session(self):
        """Only one Claude session → slot1 gets it (reversed index = same), slot2 is empty."""
        r1 = run_slot_mapping(
            iterm_ttys=["/dev/ttys009", "/dev/ttys000"],
            claude_ttys_set=["/dev/ttys000"],
            slot_num=1,
        )
        self.assertEqual(r1["claude_ttys"], ["/dev/ttys000"])
        self.assertEqual(r1["tty_dev"], "/dev/ttys000")

        r2 = run_slot_mapping(
            iterm_ttys=["/dev/ttys009", "/dev/ttys000"],
            claude_ttys_set=["/dev/ttys000"],
            slot_num=2,
        )
        self.assertEqual(r2["tty_dev"], "")

    def test_no_claude(self):
        """No Claude sessions → all slots empty."""
        r = run_slot_mapping(
            iterm_ttys=["/dev/ttys009", "/dev/ttys000"],
            claude_ttys_set=[],
            slot_num=1,
        )
        self.assertEqual(r["count"], 0)
        self.assertEqual(r["tty_dev"], "")

    def test_order_independent_of_tty_number(self):
        """TTY with higher number in earlier tab → slot1(right)=later tab."""
        r = run_slot_mapping(
            iterm_ttys=["/dev/ttys099", "/dev/ttys001"],
            claude_ttys_set=["/dev/ttys099", "/dev/ttys001"],
            slot_num=1,
        )
        # slot1 (rightmost) → last Claude TTY = ttys001
        self.assertEqual(r["tty_dev"], "/dev/ttys001")

    def test_five_sessions(self):
        """Five Claude sessions → reversed: slot1=tab5, slot5=tab1."""
        ttys = [f"/dev/ttys{i:03d}" for i in range(5)]
        for slot in range(1, 6):
            r = run_slot_mapping(
                iterm_ttys=ttys, claude_ttys_set=ttys, slot_num=slot,
            )
            # slot N → CLAUDE_TTYS[5 - N + 1] → reversed tab order
            self.assertEqual(r["tty_dev"], ttys[5 - slot])


class TestSlotReversal(unittest.TestCase):
    """Regression: SwiftBar icon order is right-to-left, causing visual mismatch.

    Bug: user had tab1(ttys009) and tab2(ttys000) running Claude.
    Without reversal, slot1(rightmost icon) mapped to tab1 and
    slot2(leftmost icon) mapped to tab2. Visually the user saw
    [left=tab2] [right=tab1], opposite of iTerm tab order.

    Fix: reverse the index so left icon = first tab, right icon = last tab.
    """

    def test_click_focus_matches_visual_position(self):
        """Left icon click → focuses tab1, right icon click → focuses tab2."""
        tabs = ["/dev/ttys009", "/dev/ttys000", "/dev/ttys002"]
        claude = ["/dev/ttys009", "/dev/ttys000"]

        # slot2 = leftmost icon in menu bar → should map to tab1 (ttys009)
        left_icon = run_slot_mapping(iterm_ttys=tabs, claude_ttys_set=claude, slot_num=2)
        self.assertEqual(left_icon["tty_dev"], "/dev/ttys009")

        # slot1 = rightmost icon in menu bar → should map to tab2 (ttys000)
        right_icon = run_slot_mapping(iterm_ttys=tabs, claude_ttys_set=claude, slot_num=1)
        self.assertEqual(right_icon["tty_dev"], "/dev/ttys000")

    def test_tab_reorder_reflected(self):
        """After user moves tabs, slot mapping follows new tab order."""
        # Original: tab1=ttys009, tab2=ttys000
        r = run_slot_mapping(
            iterm_ttys=["/dev/ttys009", "/dev/ttys000"],
            claude_ttys_set=["/dev/ttys009", "/dev/ttys000"],
            slot_num=2,
        )
        self.assertEqual(r["tty_dev"], "/dev/ttys009")  # left icon = tab1

        # After reorder: tab1=ttys000, tab2=ttys009
        r = run_slot_mapping(
            iterm_ttys=["/dev/ttys000", "/dev/ttys009"],
            claude_ttys_set=["/dev/ttys009", "/dev/ttys000"],
            slot_num=2,
        )
        self.assertEqual(r["tty_dev"], "/dev/ttys000")  # left icon = new tab1


class TestSlotExtraction(unittest.TestCase):
    """Verify SLOT_NUM extraction from plugin filename."""

    def _extract_slot(self, filename: str) -> int:
        script = f"""
SLOT_NUM=1
BASENAME="{filename}"
if [[ "$BASENAME" =~ ^ClaudeBar-([0-9]+)\\. ]]; then
    SLOT_NUM=${{match[1]}}
fi
echo $SLOT_NUM
"""
        r = subprocess.run(["zsh", "-c", script], capture_output=True, text=True, timeout=5)
        return int(r.stdout.strip())

    def test_slot_1(self):
        self.assertEqual(self._extract_slot("ClaudeBar-1.2s.sh"), 1)

    def test_slot_5(self):
        self.assertEqual(self._extract_slot("ClaudeBar-5.2s.sh"), 5)

    def test_no_slot_number(self):
        """Direct run (no slot in name) → defaults to 1."""
        self.assertEqual(self._extract_slot("ClaudeBar.sh"), 1)

    def test_different_interval(self):
        self.assertEqual(self._extract_slot("ClaudeBar-3.5s.sh"), 3)


if __name__ == "__main__":
    unittest.main()

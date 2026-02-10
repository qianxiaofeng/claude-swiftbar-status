"""Tests for tab→slot mapping logic (now in claude-status-cache.sh).

The core mapping:
  1. ITERM_TTYS: all iTerm2 TTYs in tab order (AppleScript)
  2. PID_BY_TTY: associative array of TTY→PID (from pgrep)
  3. CLAUDE_TTYS: filtered ITERM_TTYS keeping only those with a Claude PID
  4. Reversed index: slot N → CLAUDE_TTYS[count - N + 1]
  5. Results written to cache.env for slot plugins to source

SwiftBar renders menu bar icons right-to-left: slot1=rightmost.
To match visual position (left icon = left tab), the mapping is reversed.
"""

import os
import subprocess
import tempfile
import unittest


def run_cache_mapping(iterm_ttys: list[str], claude_ttys_set: list[str]) -> dict:
    """Run the zsh cache mapping logic and return parsed cache.env contents.

    Args:
        iterm_ttys: TTYs in iTerm tab order (e.g. ["/dev/ttys009", "/dev/ttys000"])
        claude_ttys_set: TTYs that have a Claude PID (e.g. ["/dev/ttys009", "/dev/ttys000"])
    Returns:
        dict with all cache.env key-value pairs
    """
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

count=${{#CLAUDE_TTYS[@]}}

ACTIVE_CLAUDE_TTYS=""
for _ct in "${{CLAUDE_TTYS[@]}}"; do
    ACTIVE_CLAUDE_TTYS="${{ACTIVE_CLAUDE_TTYS:+$ACTIVE_CLAUDE_TTYS,}}${{_ct#/dev/}}"
done

echo "SLOT_COUNT=$count"
echo "ACTIVE_CLAUDE_TTYS=$ACTIVE_CLAUDE_TTYS"

slot=1
while (( slot <= count )); do
    idx=$(( count - slot + 1 ))
    TTY_DEV="${{CLAUDE_TTYS[$idx]}}"
    PID="${{PID_BY_TTY[$TTY_DEV]}}"
    TTY_SHORT="${{TTY_DEV#/dev/}}"
    echo "SLOT_${{slot}}_TTY=$TTY_DEV"
    echo "SLOT_${{slot}}_PID=$PID"
    echo "SLOT_${{slot}}_CWD=/mock/cwd/$slot"
    echo "SLOT_${{slot}}_PROJECT_HASH=-mock-cwd-$slot"
    echo "SLOT_${{slot}}_TTY_SHORT=$TTY_SHORT"
    (( slot++ ))
done
"""
    result = subprocess.run(
        ["zsh", "-c", script], capture_output=True, text=True, timeout=5
    )
    if result.returncode != 0:
        raise RuntimeError(f"zsh failed: {result.stderr}")

    out = {}
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        k, _, v = line.partition("=")
        out[k] = v
    return out


class TestCacheMapping(unittest.TestCase):
    """Verify the cache builder produces correct slot→TTY mappings (reversed)."""

    def test_two_sessions(self):
        """Two Claude tabs → slot1(right)=tab2, slot2(left)=tab1."""
        c = run_cache_mapping(
            iterm_ttys=["/dev/ttys009", "/dev/ttys000", "/dev/ttys002"],
            claude_ttys_set=["/dev/ttys009", "/dev/ttys000"],
        )
        self.assertEqual(c["SLOT_COUNT"], "2")
        # slot1 (rightmost icon) → last Claude tab (ttys000)
        self.assertEqual(c["SLOT_1_TTY"], "/dev/ttys000")
        # slot2 (leftmost icon) → first Claude tab (ttys009)
        self.assertEqual(c["SLOT_2_TTY"], "/dev/ttys009")

    def test_gap_in_tabs(self):
        """Claude in tab1 and tab3 → slot1(right)=tab3, slot2(left)=tab1."""
        c = run_cache_mapping(
            iterm_ttys=["/dev/ttys001", "/dev/ttys002", "/dev/ttys003"],
            claude_ttys_set=["/dev/ttys001", "/dev/ttys003"],
        )
        self.assertEqual(c["SLOT_1_TTY"], "/dev/ttys003")
        self.assertEqual(c["SLOT_2_TTY"], "/dev/ttys001")

    def test_single_session(self):
        """Only one Claude session → slot1 gets it."""
        c = run_cache_mapping(
            iterm_ttys=["/dev/ttys009", "/dev/ttys000"],
            claude_ttys_set=["/dev/ttys000"],
        )
        self.assertEqual(c["SLOT_COUNT"], "1")
        self.assertEqual(c["SLOT_1_TTY"], "/dev/ttys000")
        self.assertNotIn("SLOT_2_TTY", c)

    def test_no_claude(self):
        """No Claude sessions → SLOT_COUNT=0, no slot entries."""
        c = run_cache_mapping(
            iterm_ttys=["/dev/ttys009", "/dev/ttys000"],
            claude_ttys_set=[],
        )
        self.assertEqual(c["SLOT_COUNT"], "0")
        self.assertNotIn("SLOT_1_TTY", c)

    def test_order_follows_tab_order(self):
        """TTY with higher number in earlier tab → slot1(right)=later tab."""
        c = run_cache_mapping(
            iterm_ttys=["/dev/ttys099", "/dev/ttys001"],
            claude_ttys_set=["/dev/ttys099", "/dev/ttys001"],
        )
        # slot1 (rightmost) → last Claude TTY = ttys001
        self.assertEqual(c["SLOT_1_TTY"], "/dev/ttys001")

    def test_five_sessions(self):
        """Five Claude sessions → slot N = tab (count - N + 1), reversed."""
        ttys = [f"/dev/ttys{i:03d}" for i in range(5)]
        c = run_cache_mapping(iterm_ttys=ttys, claude_ttys_set=ttys)
        self.assertEqual(c["SLOT_COUNT"], "5")
        for slot in range(1, 6):
            self.assertEqual(c[f"SLOT_{slot}_TTY"], ttys[5 - slot])

    def test_active_claude_ttys_list(self):
        """ACTIVE_CLAUDE_TTYS contains comma-separated short TTY names."""
        c = run_cache_mapping(
            iterm_ttys=["/dev/ttys009", "/dev/ttys000"],
            claude_ttys_set=["/dev/ttys009", "/dev/ttys000"],
        )
        ttys = set(c["ACTIVE_CLAUDE_TTYS"].split(","))
        self.assertEqual(ttys, {"ttys009", "ttys000"})

    def test_tty_short_field(self):
        """Each slot has TTY_SHORT without /dev/ prefix."""
        c = run_cache_mapping(
            iterm_ttys=["/dev/ttys042"],
            claude_ttys_set=["/dev/ttys042"],
        )
        self.assertEqual(c["SLOT_1_TTY_SHORT"], "ttys042")


class TestSlotOrder(unittest.TestCase):
    """Verify slot→tab mapping matches visual position.

    SwiftBar renders menu bar icons right-to-left (ClaudeBar-1 is rightmost).
    To match visual positions, the mapping is reversed:
    Left icon (highest slot) = first tab, right icon (slot 1) = last tab.
    """

    def test_click_focus_matches_visual_position(self):
        """Right icon click → focuses tab2, left icon click → focuses tab1."""
        c = run_cache_mapping(
            iterm_ttys=["/dev/ttys009", "/dev/ttys000", "/dev/ttys002"],
            claude_ttys_set=["/dev/ttys009", "/dev/ttys000"],
        )
        # slot1 = rightmost icon in menu bar → should map to tab2 (ttys000)
        self.assertEqual(c["SLOT_1_TTY"], "/dev/ttys000")
        # slot2 = leftmost icon in menu bar → should map to tab1 (ttys009)
        self.assertEqual(c["SLOT_2_TTY"], "/dev/ttys009")

    def test_tab_reorder_reflected(self):
        """After user moves tabs, cache mapping follows new tab order."""
        # Original: tab1=ttys009, tab2=ttys000
        c = run_cache_mapping(
            iterm_ttys=["/dev/ttys009", "/dev/ttys000"],
            claude_ttys_set=["/dev/ttys009", "/dev/ttys000"],
        )
        self.assertEqual(c["SLOT_1_TTY"], "/dev/ttys000")  # right icon = tab2
        self.assertEqual(c["SLOT_2_TTY"], "/dev/ttys009")  # left icon = tab1

        # After reorder: tab1=ttys000, tab2=ttys009
        c = run_cache_mapping(
            iterm_ttys=["/dev/ttys000", "/dev/ttys009"],
            claude_ttys_set=["/dev/ttys009", "/dev/ttys000"],
        )
        self.assertEqual(c["SLOT_1_TTY"], "/dev/ttys009")  # right icon = new tab2
        self.assertEqual(c["SLOT_2_TTY"], "/dev/ttys000")  # left icon = new tab1


class TestSlotPluginCacheRead(unittest.TestCase):
    """Verify ClaudeBar.sh's cache reading logic (source + eval)."""

    def _run_slot_from_cache(self, cache_content: str, slot_num: int) -> dict:
        """Write a cache.env, then run the source+eval logic from ClaudeBar.sh."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = os.path.join(tmpdir, "cache.env")
            with open(cache_path, "w") as f:
                f.write(cache_content)

            script = f"""
SLOT_NUM={slot_num}

source "{cache_path}" 2>/dev/null || exit 0
(( SLOT_COUNT < SLOT_NUM )) && {{ echo "HIDDEN=1"; exit 0; }}

eval "TTY_DEV=\\$SLOT_${{SLOT_NUM}}_TTY"
eval "PID=\\$SLOT_${{SLOT_NUM}}_PID"
eval "CWD=\\$SLOT_${{SLOT_NUM}}_CWD"
eval "PROJECT_HASH=\\$SLOT_${{SLOT_NUM}}_PROJECT_HASH"
eval "TTY_SHORT=\\$SLOT_${{SLOT_NUM}}_TTY_SHORT"

echo "TTY_DEV=$TTY_DEV"
echo "PID=$PID"
echo "CWD=$CWD"
echo "PROJECT_HASH=$PROJECT_HASH"
echo "TTY_SHORT=$TTY_SHORT"
echo "ACTIVE_CLAUDE_TTYS=$ACTIVE_CLAUDE_TTYS"
"""
            result = subprocess.run(
                ["zsh", "-c", script], capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0:
                raise RuntimeError(f"zsh failed: {result.stderr}")

            out = {}
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                k, _, v = line.partition("=")
                out[k] = v
            return out

    def test_read_slot1(self):
        """Slot 1 (rightmost icon) reads SLOT_1_* from cache."""
        cache = (
            "CACHE_TS=1739180000\n"
            "SLOT_COUNT=2\n"
            "ACTIVE_CLAUDE_TTYS=ttys009,ttys000\n"
            "SLOT_1_TTY=/dev/ttys000\n"
            "SLOT_1_PID=67890\n"
            "SLOT_1_CWD=/Users/test/project2\n"
            "SLOT_1_PROJECT_HASH=-Users-test-project2\n"
            "SLOT_1_TTY_SHORT=ttys000\n"
            "SLOT_2_TTY=/dev/ttys009\n"
            "SLOT_2_PID=12345\n"
            "SLOT_2_CWD=/Users/test/project1\n"
            "SLOT_2_PROJECT_HASH=-Users-test-project1\n"
            "SLOT_2_TTY_SHORT=ttys009\n"
        )
        r = self._run_slot_from_cache(cache, slot_num=1)
        self.assertEqual(r["TTY_DEV"], "/dev/ttys000")
        self.assertEqual(r["PID"], "67890")
        self.assertEqual(r["CWD"], "/Users/test/project2")
        self.assertEqual(r["PROJECT_HASH"], "-Users-test-project2")
        self.assertEqual(r["TTY_SHORT"], "ttys000")
        self.assertEqual(r["ACTIVE_CLAUDE_TTYS"], "ttys009,ttys000")

    def test_read_slot2(self):
        """Slot 2 (leftmost icon) reads SLOT_2_* from cache."""
        cache = (
            "CACHE_TS=1739180000\n"
            "SLOT_COUNT=2\n"
            "ACTIVE_CLAUDE_TTYS=ttys009,ttys000\n"
            "SLOT_1_TTY=/dev/ttys000\n"
            "SLOT_1_PID=67890\n"
            "SLOT_1_CWD=/Users/test/project2\n"
            "SLOT_1_PROJECT_HASH=-Users-test-project2\n"
            "SLOT_1_TTY_SHORT=ttys000\n"
            "SLOT_2_TTY=/dev/ttys009\n"
            "SLOT_2_PID=12345\n"
            "SLOT_2_CWD=/Users/test/project1\n"
            "SLOT_2_PROJECT_HASH=-Users-test-project1\n"
            "SLOT_2_TTY_SHORT=ttys009\n"
        )
        r = self._run_slot_from_cache(cache, slot_num=2)
        self.assertEqual(r["TTY_DEV"], "/dev/ttys009")
        self.assertEqual(r["PID"], "12345")
        self.assertEqual(r["CWD"], "/Users/test/project1")

    def test_slot_exceeds_count_hides(self):
        """Slot number > SLOT_COUNT → icon hides (exit 0)."""
        cache = "CACHE_TS=1739180000\nSLOT_COUNT=1\nSLOT_1_TTY=/dev/ttys000\n"
        r = self._run_slot_from_cache(cache, slot_num=2)
        self.assertEqual(r.get("HIDDEN"), "1")

    def test_missing_cache_hides(self):
        """Missing cache.env → icon hides (exit 0)."""
        script = """
SLOT_NUM=1
source "/nonexistent/cache.env" 2>/dev/null || { echo "HIDDEN=1"; exit 0; }
echo "TTY_DEV=$TTY_DEV"
"""
        result = subprocess.run(
            ["zsh", "-c", script], capture_output=True, text=True, timeout=5
        )
        out = {}
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            k, _, v = line.partition("=")
            out[k] = v
        self.assertEqual(out.get("HIDDEN"), "1")


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

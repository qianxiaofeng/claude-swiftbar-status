"""Tests for transcript resolution logic.

Covers the core bug: two sessions in the same project must each resolve
to their OWN transcript, not both to the most-recently-modified one.
"""

import json, os, sys, tempfile, time, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from resolve_transcript import resolve


class ResolveTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.state_dir = os.path.join(self.tmp, "swiftbar")
        self.project_dir = os.path.join(self.tmp, "project")
        os.makedirs(self.state_dir)
        os.makedirs(self.project_dir)

    def tearDown(self):
        self._tmp.cleanup()

    def add_transcript(self, name, age_offset=0):
        """Create a .jsonl file; age_offset shifts mtime backwards (seconds)."""
        p = os.path.join(self.project_dir, f"{name}.jsonl")
        with open(p, "w") as f:
            f.write("")
        if age_offset:
            t = time.time() - age_offset
            os.utime(p, (t, t))
        return p

    def add_state(self, tty, session_id, transcript_path):
        sf = os.path.join(self.state_dir, f"session-{tty}.json")
        with open(sf, "w") as f:
            json.dump({"session_id": session_id, "transcript_path": transcript_path}, f)


class TestBasicCases(ResolveTestBase):

    def test_state_file_valid(self):
        """State file points to existing transcript -> use it."""
        tp = self.add_transcript("aaa")
        self.add_state("ttys000", "aaa", tp)
        self.assertEqual(resolve("ttys000", self.state_dir, self.project_dir, {"ttys000"}), tp)

    def test_state_file_missing(self):
        """No state file -> fall back to most recent transcript."""
        self.add_transcript("old", age_offset=10)
        new = self.add_transcript("new", age_offset=0)
        self.assertEqual(resolve("ttys000", self.state_dir, self.project_dir, {"ttys000"}), new)

    def test_state_file_stale(self):
        """State file points to deleted transcript -> fall back."""
        self.add_state("ttys000", "gone", "/nonexistent/gone.jsonl")
        tp = self.add_transcript("real")
        self.assertEqual(resolve("ttys000", self.state_dir, self.project_dir, {"ttys000"}), tp)

    def test_no_transcripts(self):
        """No transcripts at all -> empty string."""
        self.assertEqual(resolve("ttys000", self.state_dir, self.project_dir, {"ttys000"}), "")


class TestTwoSessionsSameProject(ResolveTestBase):
    """The original bug scenario."""

    def test_both_valid(self):
        """Two sessions, both state files valid -> each gets its own."""
        tp_a = self.add_transcript("aaa", age_offset=0)
        tp_b = self.add_transcript("bbb", age_offset=5)
        self.add_state("ttys000", "aaa", tp_a)
        self.add_state("ttys009", "bbb", tp_b)
        active = {"ttys000", "ttys009"}

        self.assertEqual(resolve("ttys000", self.state_dir, self.project_dir, active), tp_a)
        self.assertEqual(resolve("ttys009", self.state_dir, self.project_dir, active), tp_b)

    def test_one_stale_does_not_steal(self):
        """THE BUG: session A state stale, session B valid.
        A must NOT steal B's transcript."""
        tp_b = self.add_transcript("bbb", age_offset=0)   # newest
        tp_a = self.add_transcript("aaa", age_offset=5)   # older
        self.add_state("ttys000", "gone", "/nonexistent/gone.jsonl")  # stale
        self.add_state("ttys009", "bbb", tp_b)  # valid
        active = {"ttys000", "ttys009"}

        self.assertEqual(resolve("ttys009", self.state_dir, self.project_dir, active), tp_b)
        # A's fallback must skip tp_b (claimed by B) and pick tp_a
        self.assertEqual(resolve("ttys000", self.state_dir, self.project_dir, active), tp_a)

    def test_both_stale_known_limitation(self):
        """Both state files stale -> no claims -> both get newest (known limitation)."""
        tp_new = self.add_transcript("new", age_offset=0)
        self.add_transcript("old", age_offset=5)
        self.add_state("ttys000", "x", "/nonexistent/x.jsonl")
        self.add_state("ttys009", "y", "/nonexistent/y.jsonl")
        active = {"ttys000", "ttys009"}

        self.assertEqual(resolve("ttys000", self.state_dir, self.project_dir, active), tp_new)
        self.assertEqual(resolve("ttys009", self.state_dir, self.project_dir, active), tp_new)


class TestDeadSessionState(ResolveTestBase):

    def test_dead_session_state_ignored(self):
        """State file from a TTY no longer running Claude is ignored."""
        tp_live = self.add_transcript("live", age_offset=0)
        self.add_transcript("dead", age_offset=5)
        self.add_state("ttys005", "dead", os.path.join(self.project_dir, "dead.jsonl"))
        active = {"ttys000"}  # ttys005 NOT active

        self.assertEqual(resolve("ttys000", self.state_dir, self.project_dir, active), tp_live)

    def test_dead_session_claim_not_blocking(self):
        """Dead session claims the only transcript -> still available."""
        tp = self.add_transcript("only")
        self.add_state("ttys005", "only", tp)
        active = {"ttys000"}

        self.assertEqual(resolve("ttys000", self.state_dir, self.project_dir, active), tp)


class TestThreeSessions(ResolveTestBase):

    def test_one_stale_gets_remaining(self):
        """Three sessions, one stale -> stale gets the remaining transcript."""
        tp_a = self.add_transcript("aaa", age_offset=10)
        tp_b = self.add_transcript("bbb", age_offset=5)
        tp_c = self.add_transcript("ccc", age_offset=0)
        self.add_state("ttys000", "gone", "/nonexistent/gone.jsonl")
        self.add_state("ttys001", "bbb", tp_b)
        self.add_state("ttys002", "ccc", tp_c)
        active = {"ttys000", "ttys001", "ttys002"}

        self.assertEqual(resolve("ttys001", self.state_dir, self.project_dir, active), tp_b)
        self.assertEqual(resolve("ttys002", self.state_dir, self.project_dir, active), tp_c)
        self.assertEqual(resolve("ttys000", self.state_dir, self.project_dir, active), tp_a)


class TestEdgeCases(ResolveTestBase):

    def test_corrupt_state_file(self):
        """Corrupt JSON -> treated as missing, falls back."""
        sf = os.path.join(self.state_dir, "session-ttys000.json")
        with open(sf, "w") as f:
            f.write("NOT VALID JSON{{{")
        tp = self.add_transcript("real")
        self.assertEqual(resolve("ttys000", self.state_dir, self.project_dir, {"ttys000"}), tp)

    def test_empty_active_ttys(self):
        """Empty active set -> all claims void, pick newest."""
        tp = self.add_transcript("only")
        self.add_state("ttys009", "only", tp)
        self.assertEqual(resolve("ttys000", self.state_dir, self.project_dir, set()), tp)

    def test_state_dir_nonexistent(self):
        """State dir doesn't exist -> fall back gracefully."""
        tp = self.add_transcript("only")
        result = resolve("ttys000", "/nonexistent/swiftbar", self.project_dir, {"ttys000"})
        self.assertEqual(result, tp)


if __name__ == "__main__":
    unittest.main()

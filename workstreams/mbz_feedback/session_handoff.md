# Session handoff

**State:** 2/10 done on `main` at `2d64f94`, as of 2026-11-05.

**Just landed:** MF-01 (`bae5adf83b`), MF-02 (`2d64f94526`)

**Next:** `ws claim --commit MF-03` (phase 2).

**Gotchas:**
- MF-02: - A line of only ### and a backticked path inside the text is read as a new file. That is the marker D-TEXT and T4 chose, so it stays; the text with such a line can't be carried whole.
- `tests/test_settle.py`, not on this task's file list, had to change: one assertion quoted the old "under Gotchas" wording, and `test_long_decision_logs_get_trimmed_with_a_pointer` used a fixed `--max-chars` that the new worker rule pushed the last decision out of, so it rose from 3100 to 3250.
- `ws evidence new` on the PATH runs main's code (T1), so this file has no Text to apply section until this task lands.
- The new `docs/rule-map.md` row gives its source as `new`, since the rule comes from the MBZ feedback and not from either source harness.

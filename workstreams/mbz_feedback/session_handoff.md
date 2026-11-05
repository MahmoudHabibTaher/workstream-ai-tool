# Session handoff

**State:** 9/10 done on `main` at `b26da0a`, as of 2026-11-05.

**Just landed:** MF-08 (`431851e770`), MF-09 (`b26da0af75`)

**Next:** `ws claim --commit MF-10` (phase 5).

**Gotchas:**
- MF-08: - Each worker rule added moves `test_long_decision_logs_get_trimmed_with_a_pointer`'s fixed `--max-chars` again: MF-02 and this task both raised it. Deriving the limit from the brief's length would end that.
- `ws-coordinate` still shows the `--acceptance` correction without `--expect`. It stays valid, and the skill wasn't on this task's file list.
- MF-09: - For MF-10: the harness runs the worker as the top-level `claude -p` in `acceptEdits`, not as a background subagent, and `cannot_edit` describes the background. A real run shows whether `.claude/notes.md` is refused there. If it isn't, the agent still has the brief's "Don't try", and the check fails a worker that edits anyway.
- `text` is in the default scenario list, so `make eval AGENT=copilot-cli` runs it too. Copilot's adapter has no `cannot_edit`, so its brief gives no warning and a Copilot worker may fairly edit the file and fail. Copilot evals are out of scope here.

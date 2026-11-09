# Session handoff

**State:** 2/5 done on `main` at `9373a40`, as of 2026-11-09.

**Just landed:** CF-01 (`d94e2802ba`), CF-04 (`9373a4004b`)

**Text to apply:**
- CF-04: .claude/agents/ws-worker.md (evidence/CF-04.md)

**Next:** `ws claim --commit CF-02` (phase 1).

**Gotchas:**
- CF-01: - Copilot's `task` tool may write sub-sessions to their own `events.jsonl`. The fallback takes only the newest one, so a run whose log has no figure could under-report. Not seen yet; CF-05's real run would show it.
- CF-04: - In the worker file the rule is a plain bullet under the one-paragraph body, with no "On Claude Code" label, as that file is Claude Code's own.
- `ws brief` reads the integration checkout's code, so this repo's own briefs keep the old unlabelled line until the branch merges.

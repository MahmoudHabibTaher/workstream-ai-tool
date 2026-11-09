# Session handoff

**State:** 4/5 done on `main` at `c18f7cb`, as of 2026-11-09.

**Just landed:** CF-03 (`c18f7cbdc4`)

**Text to apply:**
- CF-04: .claude/agents/ws-worker.md (evidence/CF-04.md)

**Next:** `ws claim --commit CF-05` (phase 2).

**Gotchas:**
- CF-03: - The check reports changes on trunk ahead of changes in the working tree. An agent that edited the file but didn't commit gets "in the working tree".
- Whether Copilot runs the capture entry with a `bash` key and empty stdout as an allow is assumed from the generated entry's shape. CF-05's real run will show it.

# Session handoff

**State:** 7/10 done on `main` at `3860811`, as of 2026-11-11.

**Just landed:** JX-07 (`3860811bb6`)

**Open decisions:**
- D023: Run This Task… is left out of the Run group until JX-08 (waiting: JX-08, JX-09, JX-10)

**Next:** `ws claim --commit JX-08` (phase 3).

**Gotchas:**
- JX-07: - The empty state when only closed workstreams exist says "No open workstreams" / "Show Done lists the done and abandoned ones." This is a third empty state beside the two D-MENUS names.
- The how-to-plan line is `To plan one, run ws new <id>, then ws seed it from an approved plan.` It can't name a skill, because `NoPromptTextTests` rejects the word in Kotlin.
- Tools ▸ Workstreams reads the focused component's data, so its groups are offered only while the Workstreams tab has focus. Elsewhere the submenu is empty and shown disabled.

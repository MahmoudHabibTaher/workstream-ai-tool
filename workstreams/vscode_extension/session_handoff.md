# Session handoff

**State:** 7/8 done on `main` at `69c422e`, as of 2026-11-06.

**Just landed:** VS-07 (`69c422e0d5`)

**Open decisions:**
- D009: `--show` is left out of cli.ts until VS-06 (waiting: VS-08)
- D010: `@types/node` is a fifth dev dependency, pinned to Node 20 (waiting: VS-08)
- D029: a workstream's tasks file is the first path its own snapshot's `watch` lists that the root snapshot's doesn't (waiting: VS-08)

**Next:** `ws claim --commit VS-08` (phase 4).

**Gotchas:**
- VS-07: - Every reload now also runs `ws snapshot -w <id>` for each workstream that has a finding, closed ones included (beta in the fixture), to find its tasks file. D029's `paths.tasks` would still need these calls.
- `vscode.executeCodeActionProvider` throws `Illegal argument` unless the document is open, so the test opens the tasks file first, as a click in the Problems panel would.

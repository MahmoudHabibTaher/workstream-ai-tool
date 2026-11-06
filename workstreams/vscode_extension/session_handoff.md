# Session handoff

**State:** 5/8 done on `main` at `208aa0b`, as of 2026-11-06.

**Just landed:** VS-05 (`208aa0beec`)

**Open decisions:**
- D009: `--show` is left out of cli.ts until VS-06 (waiting: VS-06, VS-07, VS-08)
- D010: `@types/node` is a fifth dev dependency, pinned to Node 20 (waiting: VS-06, VS-07, VS-08)

**Next:** `ws claim --commit VS-06` (phase 3).

**Gotchas:**
- VS-05: - act prints its refusal with a `refused: ` prefix (`refused: stale view: …`). The extension shows it as given.
- After `ws claim`, the queue is dirty, so act refuses every write until it is committed. The integration test commits the claim first, as an orchestrator would.

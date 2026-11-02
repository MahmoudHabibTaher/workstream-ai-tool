# Session handoff

**State:** 1/6 done on `main` at `c2a79aa`, as of 2026-11-02.

**Just landed:** PI-01 (`c2a79aa1a3`)

**Next:** `ws claim --commit PI-02` (phase 1).

**Gotchas:**
- PI-01: Only 65 of the Copilot sessions for that project have per-call records: older ones don't. An older harness's workers need `--worker-marker`, and that is a rough text match. Claude Code's slug prefix can match a sibling folder that shares its start.

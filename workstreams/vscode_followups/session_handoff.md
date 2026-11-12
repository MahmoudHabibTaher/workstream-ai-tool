# Session handoff

**State:** 1/5 done on `main` at `cd59e0b`, as of 2026-11-12.

**Just landed:** VF-01 (`cd59e0bb83`)

**Next:** `ws claim --commit VF-02` (phase 1).

**Gotchas:**
- VF-01: - Budget now lives in the panel, so working in the side bar no longer hides it. While the Budget tab is showing, every Refresh runs `ws audit context`. That is what D030 says should happen, but it will run more often than it did in the activity bar.

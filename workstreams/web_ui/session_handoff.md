# Session handoff

**State:** 3/6 done on `main` at `1523ebe`, as of 2026-11-03.

**Just landed:** WU-03 (`1523ebeef9`)

**Next:** `ws claim --commit WU-04 WU-05` (phase 2).

**Gotchas:**
- WU-03: Each stream holds one of the browser's connections to this origin, so about six tabs on one server will stall.

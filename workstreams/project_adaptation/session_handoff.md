# Session handoff

**State:** 2/5 done on `main` at `334053b`, as of 2026-11-02.

**Just landed:** AD-02 (`334053b1da`)

**Next:** `ws claim --commit AD-03` (phase 1).

**Gotchas:**
- AD-02: A command that changes tracked files at init leaves those changes in the tree: `ws init` reports it and doesn't undo them, because undoing could lose something. It says to review what's left.

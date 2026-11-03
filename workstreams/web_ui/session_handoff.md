# Session handoff

**State:** 1/6 done on `main` at `220e17b`, as of 2026-11-03.

**Just landed:** WU-01 (`220e17bc9d`)

**Next:** `ws claim --commit WU-02` (phase 1).

**Gotchas:**
- WU-01: `--checks` writes loose objects through `verify.code_tree`'s throwaway index, as `ws settle --dry-run` does. It doesn't touch the real index.

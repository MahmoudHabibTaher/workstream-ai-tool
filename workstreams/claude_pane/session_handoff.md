# Session handoff

**State:** 3/4 done on `main` at `f5cf21f`, as of 2026-11-03.

**Just landed:** CP-03 (`f5cf21f9d5`)

**Next:** `ws claim --commit CP-04` (phase 3).

**Gotchas:**
- CP-03: A scratch test drove every screen on all four surfaces with real snapshots from three repos: 12 pass. It isn't committed, as it holds real project data. Nobody has yet seen the pane drawn in a real app: `-p` opens no surface, and that needs the user.

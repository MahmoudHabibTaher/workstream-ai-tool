# Session handoff

**State:** 1/7 done on `main` at `3411d65`, as of 2026-11-12.

**Just landed:** VX-01 (`3411d6508a`)

**Next:** `ws claim --commit VX-02` (phase 1).

**Gotchas:**
- VX-01: - `ws verify` takes about 8 minutes for `make test` here.
- `views/registry.ts` still uses `registry.ts`'s builders. VX-02 should move it to `listRows`/`taskLanes` and retire the old ones.

# Session handoff

**State:** 2/6 done on `main` at `cf0058b`, as of 2026-11-03.

**Just landed:** WU-02 (`cf0058b049`)

**Next:** `ws claim --commit WU-03` (phase 2).

**Gotchas:**
- WU-02: `frame-ancestors 'none'` will need loosening, on an explicit flag, for M9's webview. A cross-site frame also wouldn't get the Lax cookie, so M9 will need its own answer there.

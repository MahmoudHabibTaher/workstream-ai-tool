# Session handoff

**State:** 6/6 done on `main` at `fb907f1`, as of 2026-11-03.

**Just landed:** WU-06 (`fb907f1e2d`)

**Next:** The queue is finished; `ws close` closes the workstream.

**Gotchas:**
- WU-06: The Rust project was viewed read-only: its HEAD, status, ref count and registry hash matched before and after. Only landed tasks were opened there, as a branch task's gates write loose objects. M9 needs its own way past `frame-ancestors 'none'` and the Lax cookie, on an explicit flag.

# Session handoff

**State:** 2/8 done on `main` at `7e12e6b`, as of 2026-11-13.

**Just landed:** TU-01 (`7e12e6b594`)

**Still in progress:** TU-02 (coordinator)

**Next:** `ws claim --commit TU-04 TU-05 TU-06` (phase 1).

**Gotchas:**
- TU-01: - `brief._with_decisions` (src/workstream/brief.py:358) counts only entry texts against `max_chars`; the heading and the `more:` pointer are added on top, so a rendered brief can exceed `--max-chars` by up to about 80 characters. Not changed here (scope rule).
- `python3 -m unittest` needs `PYTHONPATH=src` when run outside `make`.

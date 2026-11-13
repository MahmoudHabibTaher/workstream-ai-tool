# Session handoff

**State:** 8/8 done on `main` at `5471736`, as of 2026-11-13.

**Just landed:** TU-08 (`54717363d1`)

**Next:** The queue is finished; `ws close` closes the workstream.

**Gotchas:**
- TU-08: - `brief._with_decisions` (src/workstream/brief.py:358) lets a brief run about 80 characters over `--max-chars` (found by TU-01). Recorded as unproven in 0020; not changed under the scope rule.

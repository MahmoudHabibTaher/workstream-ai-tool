# Session handoff

**State:** 1/10 done on `main` at `e739060`, as of 2026-11-11.

**Just landed:** JX-02 (`e73906035e`)

**Still in progress:** JX-01 (ws-run)

**Next:** `ws claim --commit JX-03` (phase 1).

**Gotchas:**
- JX-02: - `ws show` still computes "unblocks" inline in `src/workstream/cli.py` (`_print_task`); it could call `snapshot.task_graph_facts` or a shared graph helper so there's one copy. Not done here (cli.py is outside this task's files).

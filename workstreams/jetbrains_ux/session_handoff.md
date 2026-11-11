# Session handoff

**State:** 3/10 done on `main` at `5d6ad3d`, as of 2026-11-11.

**Just landed:** JX-03 (`5d6ad3dcfe`)

**Next:** `ws claim --commit JX-04` (phase 1).

**Gotchas:**
- JX-03: - The skills check uses only `adapt.adapted` (the manifest's list), as T4 says. It doesn't look at `adapt.drift`, so skills that were installed and then deleted or edited still pass. A later task could add drift as a second warning.
- The `dirty` check uses the same owner filter as `act.check_checkout` (the registry, or this workstream's folder), written again in `launch.check_dirty` because `act.py` isn't in this task's files. A shared helper in snapshot.py would leave one copy.
- JX-04/JX-05 need `ws launch check` added to `tests/test_jetbrains_files.py`'s argv list (T8) when Cli.kt calls it.

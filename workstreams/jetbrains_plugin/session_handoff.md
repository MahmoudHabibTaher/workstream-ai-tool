# Session handoff

**State:** 2/7 done on `main` at `390e495`, as of 2026-11-08.

**Just landed:** JB-02 (`390e495518`)

**Next:** `ws claim --commit JB-03` (phase 2).

**Gotchas:**
- JB-02: - `make verify-jetbrains` is UP-TO-DATE when nothing changed, and then prints no verdicts. Use `./gradlew verifyPlugin --rerun` to see them again.
- JB-03 and JB-04 should extend `SINK` and `PROCESS` in `tests/test_jetbrains_files.py` when they add tooltips, dialogs and the launcher. The process check currently allows only `Cli.kt`.
- `workstreams-terminal.xml` is an empty `<idea-plugin>` for JB-04 to fill. The verifier accepted it on both IDEs.

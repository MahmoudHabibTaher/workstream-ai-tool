# 0007: How a project adopts the tool

Decided while building M4. The workstream's own `DECISIONS.md` has the smaller calls.

**Profiles are data, and the engine knows no stack.** A profile is a TOML file under `src/workstream/assets/profiles/` holding candidates and generic conditions, so adding a stack means adding a file. They ship inside the package rather than in a top-level `profiles/` folder, so a plain install can find them.

**A proposal only becomes active by working.** `ws init` runs each key's candidates in order until one works. What passes, or fails with findings its parser can read, becomes an active key. Everything else stays in the config as a commented line with its reason, so a broken build is seen rather than dropped.

**A failing test or compile is a comment, not a baseline.** A key the exit-code parser would always fail can't be active, because it would block every task naming it. Recording failing tests as known would hide regressions. So only commands with a real parser can carry debt, and the profiles give one to lint alone.

**Known findings live in `.workstream/baseline.json`,** and a workstream's own record overrides them key by key. It is committed, so workers see it. `ws baseline record` stays useful when a workstream wants a fresher record.

**An existing config is never touched.** To start again, delete it. Merging into hand-edited TOML would be easy to get wrong, and the cost of redoing it is one command.

**Only one profile per repo.** A repo matching several gets the most specific by `priority`, and is told about the others. Combining them needs key prefixes nobody has asked for yet; subsonic's mixed Rust and frontend repo will test this in M6.

**Tiers:** `lite` is a plan, a queue and evidence. `standard` adds decisions, progress and a handoff. `full` adds a release: it needs a runbook, requires `releaseImpact`, and `ws status` and `ws close` report the bump. This changes M1, where any project with a runbook needed `releaseImpact` on every task.

**`ws doctor` is read-only, and warnings don't change its exit code.** `--run` judges each command against the baseline, the on-demand form of the start-of-session check that decision 0006 removed.

**Real toolchains are opt-in.** Stubs keep `make test` fast and free of dependencies; `make test-real` adopts small real projects with what is installed. That split is worth keeping: only the real `cargo` showed that a first build writes `Cargo.lock`, which the stubbed tests had read as fine and the first implementation read as a command changing tracked files.

**Still unproven:** no real `go`, `ruff`, `pytest` or `detekt` has run. Their commands and patterns come from documented formats. No real repository has been adopted, which is M6.

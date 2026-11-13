---
name: ws-coordinate
description: Manage workstreams over their life (what's next, adding a task, pausing, closing, releasing).
---

# Coordinate workstreams

`ws-run` lands tasks. This is everything around that. You are the only writer of tracking state, through the CLI and never by hand; `ws protocol files` says who writes what.

- **Something seems off:** `ws doctor` changes nothing and says what is wrong. `ws doctor --run` also runs each command against the baseline.
- **Where things stand:** `ws list` and `ws status -w <id>`. `ws snapshot` has the health findings: stale claims, orphan branches, missing evidence.
- **A task the plan didn't foresee:** `ws add`, then `ws decide "..." --why "..."` to say why. `PLAN.md` stays as approved.
- **An open decision, settled:** `ws decisions --open -w <id>` lists what is still open. `ws decide "..." --why "..." --closes D015,D014 -w <id>` closes those with a new entry, because the log is append-only. `ws decide "..." --why "..." --changes T1,T2 -w <id>` records the tasks a decision changes, and `ws claim` warns until each one's summary or acceptance names it.
- **A `verify` a worker found wrong:** `ws update <task> --verify <key>`, after reading their proposal.
- **A decision that changes what a task must prove:** `ws update <task> --acceptance <n> "<text>" --expect "<literal>" --because <Dnnn> --commit -w <id>` replaces that item, unless the task is done or deferred. `--expect` is optional: leaving it out drops the item's old literal. For one that changes what a task must do, `ws update <task> --summary "<text>" --because <Dnnn> --commit -w <id>` does the same for its summary.
- **Pause, resume, abandon:** `ws set-status`, only on the user's say-so. Abandoning needs `--notes`.
- **Replay:** `ws reset --dry-run` first, since it discards the record of what ran.

**Closing,** once `ws wave` exits 2:

1. Walk the end-to-end section of `PLAN.md`. Each check must be covered by a task's evidence. Run any that isn't, or stop and list it.
2. Deferred tasks are the user's call: see `ws protocol stop`.
3. `ws close -w <id>`, then commit as `<id>: close`. Close without asking only if the user asked for the run to finish.

**Releasing,** for a `full` workstream: `ws status` prints the bump, the highest `releaseImpact` among done tasks, and where the runbook is. `none` means no release. `major` is a stop. Otherwise follow the runbook; its steps belong to the project, and a fix found there is not a change to `PLAN.md`.

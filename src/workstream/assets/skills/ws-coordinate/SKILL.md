---
name: ws-coordinate
description: Manage workstreams over their life: choose what's next, add a task, pause, close and release.
---

# Coordinate workstreams

`ws-run` lands tasks. This is everything around that. You are the only writer of tracking state, through the CLI and never by hand; `ws protocol files` says who writes what.

- **Where things stand:** `ws list` and `ws status -w <id>`. `ws snapshot` has the health findings: stale claims, orphan branches, missing evidence.
- **A task the plan didn't foresee:** `ws add`, with a `DECISIONS.md` entry saying why. `PLAN.md` stays as approved.
- **A `verify` a worker found wrong:** `ws update <task> --verify <key>`, after reading their proposal.
- **Pause, resume, abandon:** `ws set-status`, only on the user's say-so. Abandoning needs `--notes`.
- **Replay:** `ws reset --dry-run` first, since it discards the record of what ran.

**Closing,** once `ws wave` exits 2:

1. Walk the end-to-end section of `PLAN.md`. Each check must be covered by a task's evidence. Run any that isn't, or stop and list it.
2. Deferred tasks are the user's call: see `ws protocol stop`.
3. `ws close -w <id>`, then commit as `<id>: close`. Close without asking only if the user asked for the run to finish.

**Releasing,** for a `full` workstream: `ws status` prints the bump, the highest `releaseImpact` among done tasks, and where the runbook is. `none` means no release. `major` is a stop. Otherwise follow the runbook; its steps belong to the project, and a fix found there is not a change to `PLAN.md`.

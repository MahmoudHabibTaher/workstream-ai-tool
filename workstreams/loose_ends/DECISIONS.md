# Decisions: Loose ends

Settled judgment calls, closed unless new evidence shows up. Append, never rewrite. To reverse an entry, add one that supersedes it.

Entry shape: `## Dnnn (YYYY-MM-DD, <who>): <the call>`, then the reason and the rejected alternative, ending **Closed.** or **Open.**

---

## D001 (2026-11-05, user): scope approved

The title above is the tool's fixed wording. When this was seeded, the user had not yet seen the plan: another session asked for it to be seeded and validated, ready for the user to approve and run. Starting it is the user's call, and their approval goes in its own later entry. The standing constraints that session relayed from the user: tasks_list.json is written only through the CLI; prove branches with make test, since ws is an editable install; Opus 5.5 at medium effort for workers and evals; no Copilot evals without asking, as they use paid work-account credits; no changes in subsonic-server or the Kotlin harness; no reversing closed decisions, including the 4500 brief budget. **Closed.**

## D002 (2026-11-05, user): The user approved the plan, including Claude Code evals in LE-10

Asked whether to approve running loose_ends, including about $2.50 of Claude Code evals, the user answered: Approve the plan. This is the approval D001 says comes in a later entry. Copilot evals stay out, and every other constraint in D001 stands. **Closed.**

## D003 (2026-11-05, LE-04): reuse `act.changed_paths` for the comparison

D-NOOP says to compare the queue before and after, ignoring `updated`. `act.changed_paths` (`src/workstream/act.py`) already does exactly that, so `_commit_queue` calls it. `act.py` isn't changed, and neither is `act.commit`'s refusal.
Rejected: a second comparison in `cli.py`, which would duplicate that logic. **Closed.**

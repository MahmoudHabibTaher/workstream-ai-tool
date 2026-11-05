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

## D004 (2026-11-05, LE-02): Count a leftover's commits from the integration branch, not from baseCommit

D-LEFTOVER says "commits since `baseCommit`", but `baseCommit` is the commit before `claim --commit`, and the worktree's branch starts after it. On this very task, baseCommit is f40e12a and the branch started at 8402f5f "loose_ends: claim LE-02, LE-03, LE-05". So `baseCommit..branch` counts 1 on a fresh claim, which would print the section acceptance 3 forbids. `integration..branch` counts only the worker's commits, needs no baseCommit, and matches what `_resume_lines` already does.

Rejected: `baseCommit..branch` as written, for the reason above; and subtracting one, which is wrong for a claim made without `--commit`. **Closed.**

## D005 (2026-11-05, LE-02): The section goes just before Acceptance, not at the top as `## Resuming` does

Unlike `## Resuming`, it needs no closing `## The task` heading there, since the next heading always follows it, and the worker reads it right before the items it must check the work against.

Rejected: the top of the brief, which needs that extra heading and sits apart from the acceptance items. **Closed.**

## D006 (2026-11-05, LE-05): the raise is worded in place of the `requires` item, not at the end of the line

D-RAISED only shows `requires` alone. `release-impact` is named after `requires`, so words added at the end would read `requires, release-impact, which raised mode to foreground` and blame the wrong field. The line reads `updated X-01: requires, which raised mode to foreground, release-impact`, and `test_the_raise_stays_next_to_the_requires_that_caused_it` holds it.
Rejected: appending to the end of the line, for the misattribution above. **Closed.**

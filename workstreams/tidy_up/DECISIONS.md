# Decisions: Tidy up

Settled judgment calls, closed unless new evidence shows up. Append, never rewrite. To reverse an entry, add one that supersedes it.

Entry shape: `## Dnnn (YYYY-MM-DD, <who>): <the call>`, then the reason and the rejected alternative, ending **Closed.** or **Open.**

---

## D001 (2026-11-13, user): scope approved

The owner chose to include D029 in full: the snapshot gains paths.tasks, and both the VS Code extension and the JetBrains plugin read it.
The owner kept the ### text-to-apply marker as mbz_feedback D-TEXT designed it: out of scope.
D010 (@types/node) is not reopened: D034 accepted it.
Copilot evals stay out, as they use paid work-account credits. **Closed.**

## D002 (2026-11-13, TU-03): several files in one item are joined as "A, written by X, and B, written by Y"

The plan says to list each file with its writer but gives only the one-file form. Each file keeps the one-file shape ("NAME, written by WRITERS") and the last is joined with ", and ", then ", not the worker, so ..." follows once. Rejected: semicolons between files, which read worse before "not the worker". **Closed.**

## D003 (2026-11-13, TU-01): the bare brief is rendered with DECISIONS.md removed, and the limit adds half an entry beyond five

The fixture's scaffold already writes a DECISIONS.md, so the test unlinks it before measuring the bare brief, then writes the 39-entry log. Room is five entries' length plus half of one: `_with_decisions` budgets only the entry texts against `--max-chars`, not the `## Decisions that apply` heading or the `N more:` pointer, so exactly five entries' room would put the output over the limit. Half an entry keeps the sixth from fitting (so five are kept) and covers the heading and pointer.
Rejected: a fixed overhead constant for the heading and pointer, which is another number to keep in step with the code. **Closed.**

## D004 (2026-11-13, TU-06): `view` drops the `tasks` key by name rather than keeping a whitelist of document names

The repo has no `DOC_NAMES` constant on the Kotlin side (grep finds none), so `view` keeps reading every string in `paths` as before and excludes only `tasks`. The documents stay the four narrative files the CLI gives.
Rejected: adding a fixed list of plan/progress/decisions/handoff in Kotlin, which would duplicate the CLI's `NARRATIVE_FILES` and drop any new document the CLI adds. **Closed.**

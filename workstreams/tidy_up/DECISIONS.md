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

# Decisions: Left open

Settled judgment calls, closed unless new evidence shows up. Append, never rewrite. To reverse an entry, add one that supersedes it.

Entry shape: `## Dnnn (YYYY-MM-DD, <who>): <the call>`, then the reason and the rejected alternative, ending **Closed.** or **Open.**

---

## D001 (2026-11-04, user): scope approved

The user asked for one task and one fresh background worker per bug under Left open in docs/decisions/0012-run-feedback.md, with a final proof task. Foreground tasks always get a worktree, including those with requires, and their briefs land through --root, so the main checkout never changes branch. Rejected: keeping the refusal for tasks with requires. Claude Code eval spend is approved for LO-09; Copilot evals are not. D013 and the rest of run_feedback's decisions stay binding, including the 4500 brief budget, and D013's doubled marker is not rewritten. **Closed.**

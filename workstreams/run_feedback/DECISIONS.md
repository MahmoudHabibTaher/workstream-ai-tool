# Decisions: Run feedback

Settled judgment calls, closed unless new evidence shows up. Append, never rewrite. To reverse an entry, add one that supersedes it.

Entry shape: `## Dnnn (YYYY-MM-DD, <who>): <the call>`, then the reason and the rejected alternative, ending **Closed.** or **Open.**

---

## D001 (2026-11-04, user): scope approved

The user asked for each issue to be handled by its own agent, instead of grouped steps. So there is one task per issue, each worked by a fresh background worker, plus one final proof task. Subsonic-server's own fixes stay out of this queue. RF-14 (expected output on acceptance items) was offered as the one to drop, and the user kept it. Claude Code eval spend is approved for RF-15; Copilot evals are not. **Closed.**

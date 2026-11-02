# Decisions: Agent adapters

Settled judgment calls, closed unless new evidence shows up. Append, never rewrite. To reverse an entry, add one that supersedes it.

Entry shape: `## Dnnn (YYYY-MM-DD, <who>): <the call>`, then the reason and the rejected alternative, ending **Closed.** or **Open.**

---

## D001 (2026-11-02, user): scope approved

The user said to start M5. Copilot here is on a work account and the user keeps this project separate from work, so no real Copilot run happens without asking. Headless Claude Code has no valid login here, and the user must sign in themselves. **Closed.**

## D002 (2026-11-02, AA-01): a file already at a skill's path counts as not ours

It could be someone's own skill with the same name, so it gets the same refusal as a hand edit. Rejected: overwriting it because the name matches. **Closed.**

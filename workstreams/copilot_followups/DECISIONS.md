# Decisions: Copilot follow-ups

Settled judgment calls, closed unless new evidence shows up. Append, never rewrite. To reverse an entry, add one that supersedes it.

Entry shape: `## Dnnn (YYYY-MM-DD, <who>): <the call>`, then the reason and the rejected alternative, ending **Closed.** or **Open.**

---

## D001 (2026-11-09, user): scope approved

The owner chose, on 2026-11-09:
- `text` runs only for agents whose adapter has a cannot_edit folder, and is reported N/A elsewhere. Rejected: hard-coding Claude Code, and inventing a Copilot cannot_edit folder.
- The Copilot hook is proven by a real run that records its payload, as well as by scripted tests. The owner approved the Copilot credits for the `hook` and `text` scenarios in CF-05, about 25. A full Copilot rerun needs asking again.
- The edit-tools / one-command-per-call rule moves to the Claude Code adapter, so Copilot workers no longer get it. Rejected: keeping it for every agent and enforcing it on Copilot through a narrower eval allowlist. **Closed.**

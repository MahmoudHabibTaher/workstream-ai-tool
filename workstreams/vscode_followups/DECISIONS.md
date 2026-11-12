# Decisions: VS Code follow-ups

Settled judgment calls, closed unless new evidence shows up. Append, never rewrite. To reverse an entry, add one that supersedes it.

Entry shape: `## Dnnn (YYYY-MM-DD, <who>): <the call>`, then the reason and the rejected alternative, ending **Closed.** or **Open.**

---

## D001 (2026-11-12, user): scope approved

The owner asked for these after the vscode_ux hand check (2026-11-12):
- Review, Health and Budget go to panel tabs of their own: four panel containers, matching the JetBrains tool window's tabs. Rejected: activity bar icons; one container holding Health and Budget.
- A blocked launch shows a read-only quick pick of its checks, blocking first. Rejected: a modal dialog.
- The Terminal path gets both shortenings: a repeat-last row at the top of the first pick, and one combined agent × effort × permissions pick. No option is removed.
- vscode_ux D020 is settled here: the snapshot's per-row `launches` drive the menus and the prompts. **Closed.**

# Decisions: VS Code extension

Settled judgment calls, closed unless new evidence shows up. Append, never rewrite. To reverse an entry, add one that supersedes it.

Entry shape: `## Dnnn (YYYY-MM-DD, <who>): <the call>`, then the reason and the rejected alternative, ending **Closed.** or **Open.**

---

## D001 (2026-11-06, user): scope approved

The owner chose native VS Code UI over a webview (decision 0016), with the ws CLI as the only source of facts and writes, not ws serve.
The owner removed Cursor from scope: M9 is proven in VS Code only, and M10 targets IntelliJ.
The owner chose an integrated terminal for Run, Coordinate, Close and Abandon, with chat windows as a later goal; the launcher is built to take a second target, but M9 ships the terminal only, with the clipboard when no agent command is set.
Planning chose: a local .vsix, no Marketplace; dev-only npm dependencies (typescript, @types/vscode, @vscode/test-electron, @vscode/vsce) and no runtime ones; integration tests against the installed VS Code with no download; the extension disabled in untrusted workspaces. **Closed.**

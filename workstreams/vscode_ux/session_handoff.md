# Session handoff

**State:** 6/7 done on `main` at `2d07d33`, as of 2026-11-12.

**Just landed:** VX-06 (`2d07d331f9`)

**Open decisions:**
- D020: the launch menu still uses the D022 status rule (waiting: VX-07)

**Next:** `ws claim --commit VX-07` (phase 4).

**Gotchas:**
- VX-06: - On the claim commit, `make test-vscode` fails at the clipboard step's terminal count (see D024). VX-05's recorded pass was probably on an earlier VS Code build, which kept exited terminals open.
- VX-07's manual check needs Copilot Chat installed (plan T3). The Claude Code target has only been run with a stub here. The handler code was read in `anthropic.claude-code-2.1.318`: `new URLSearchParams(E.query)` → `claude-vscode.primaryEditor.open(session, prompt)`.

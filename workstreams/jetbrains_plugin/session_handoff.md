# Session handoff

**State:** 4/7 done on `main` at `5553b56`, as of 2026-11-08.

**Just landed:** JB-04 (`5553b56ed2`)

**Open decisions:**
- D014: the Terminal tab is opened with the public `createNewSession(runner, TerminalTabState)`, not the five-argument overload plan T7 names (waiting: JB-05, JB-06, JB-07)

**Next:** `ws claim --commit JB-05` (phase 3).

**Gotchas:**
- JB-04: - The confirm says `This commits "alpha: pause" on main.`, while `ws act` commits `alpha: pause (ws act)`. VS Code's `commitLine` says the same. If the confirm should quote the subject exactly, the commit line belongs in the snapshot, not in a fourth copy.
- `ui/vscode/src/logic/actions.ts` and this port both rebuild the commit line. They are held together by a test only within each UI.
- JB-07's manual check should cover a real Terminal tab (D014) and the popup menu on a right-click.

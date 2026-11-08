# Session handoff

**State:** 6/7 done on `main` at `1406479`, as of 2026-11-08.

**Just landed:** JB-06 (`1406479ac0`)

**Open decisions:**
- D014: the Terminal tab is opened with the public `createNewSession(runner, TerminalTabState)`, not the five-argument overload plan T7 names (waiting: JB-07)

**Next:** `ws claim --commit JB-07` (phase 4).

**Gotchas:**
- JB-06: - The JB-07 manual check should click the notification's Show Health once in a real IDE. The headless test only checks that the action is there and is `ShowHealthAction`.

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

## D002 (2026-11-12, VF-01): the integration suite hides Budget by focusing the Workstreams tab, not the Explorer

The plan (D-PANELS) said the integration suite would keep passing unchanged. It did not. The first `ws verify` failed in `healthAndBudget` with `2 !== 1`. The suite hid Budget with `workbench.view.explorer`, which only changes the side bar. A panel tab stays visible through that, so the next Refresh ran `ws audit context` a second time. The one change in `ui/vscode/test/integration/suite.ts` replaces it with `workstreams.list.focus`. That switches the panel to the Workstreams tab and hides Budget, and it also exercises the separate tabs. D030 (audit only while Budget is visible) still holds, and the assertion is unchanged. The suite is outside the files the brief listed, and acceptance 2 said the suite would be unchanged. That is why this is recorded here.
Rejected: `workbench.action.closePanel`, which also hides it but says nothing about the tabs being separate; leaving the suite as it was, which cannot pass with Budget in the panel. **Closed.**

## D003 (2026-11-12, VF-01): icons for the three new containers

Panel containers need an `icon`, so I added `ui/vscode/media/review.svg` (a page with a check), `health.svg` (a pulse line) and `budget.svg` (bars). All three use the same 24px stroke style as `workstreams.svg`.
Rejected: reusing `workstreams.svg` for all four, which makes the tabs look the same when they are dragged into a side bar. **Closed.**

## D004 (2026-11-12, VF-02): the health-backed checks are a fixed list, `HEALTH_CHECKS = ['validate', 'claim']` in logic/launch.ts

`ws launch check --json` does not say which checks come from the health findings, and src/workstream is out of scope, so the two ids the plan names are kept as a constant that the unit test pins. Picking either runs `workstreams.health.focus` (a literal, since importing `HEALTH_VIEW` from views/health.ts would make an import cycle through commands.ts).
Rejected: a `health` flag on each check from the CLI, which needs a change to src/workstream. **Closed.**

## D005 (2026-11-12, VF-02): `say` still shows its error toast with the short line, before the list opens

The plan rejects "keeping the toast", meaning the old toast that carried every check's message. `say` is shared and shows a toast for every message; the brief says it still gets the one short line, so the person now sees `Run alpha is blocked by 3 checks` as a toast and the list of checks as the pick. `blockedLine` keeps its name and now returns that short line, which is also the pick's title.
Rejected: a quiet `say` variant without a toast, which changes `say`'s contract for one caller. **Closed.**

## D006 (2026-11-12, VF-03): `src/extension.ts` changes by one line though the brief does not list it

It calls `contextValue(w.kind, w.writes, w.launch)` to set the selected-item key that the title menus match, so it now passes `w.launches`. Without that line the build fails, and the title menus could not see `launch:<kind>`. `test/integration/suite.ts` also changes, for acceptance 3 and the new contextValue words. Neither file is in the brief's list.
Rejected: leaving the title menus on the old word. That would split one rule between two places. **Closed.**

## D007 (2026-11-12, VF-03): `ListRow.launch: boolean` becomes `launches: Launch[]`, and `launches(row)` keeps only the kinds the extension can start

`launches(row)` returns the snapshot's kinds filtered through `LAUNCHES` and in that order. A kind the extension has no command for, such as `run-task`, is never offered. The prompt itself is read from `node.row.launches` when the command runs. `needsReason` now takes the offer (`ask === 'reason'`), and `offerPrompt(offer, why)` appends the reason. `WHY`, `promptText` and `PROMPTS` are gone, and `launchFlow`'s `Ask` carries `prompt` in place of `why`.
Rejected: passing the whole offer list to `contextValue`. Its callers only need the kind words. **Closed.**

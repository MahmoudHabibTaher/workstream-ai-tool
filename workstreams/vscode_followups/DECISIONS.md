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

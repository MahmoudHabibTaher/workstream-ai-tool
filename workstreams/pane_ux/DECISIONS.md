# Decisions: Claude Code pane UX

Settled judgment calls, closed unless new evidence shows up. Append, never rewrite. To reverse an entry, add one that supersedes it.

Entry shape: `## Dnnn (YYYY-MM-DD, <who>): <the call>`, then the reason and the rejected alternative, ending **Closed.** or **Open.**

---

## D001 (2026-11-10, user): scope approved

The owner chose layout plus pre-flight for the pane. It keeps filling the prompt box only: no other targets and no presets. **Closed.**

## D002 (2026-11-13, PX-01): abandon fills its prompt plus `<reason>`, taken from the launch's `ask`

The old `promptText` appended `<why>`. Now the placeholder is the launch's own `ask` field, so the CLI names it, and the pane has no wording of its own. Rejected: keeping a literal `<why>` in the pane, which is a second copy of what the snapshot already says. **Closed.**

## D003 (2026-11-13, PX-01): the status writes stay between run/coordinate and the other launches

Pause and Resume still sit after Run and Coordinate, as before. Close and Abandon follow, in the snapshot's order. Rejected: drawing all launches first, which would move the buttons around before PX-02's layout work. **Closed.**

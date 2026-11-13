# Session handoff

**State:** 2/5 done on `main` at `94a42d4`, as of 2026-11-13.

**Just landed:** PX-02 (`94a42d4c19`)

**Next:** `ws claim --commit PX-03` (phase 1).

**Gotchas:**
- PX-02: - The tags were bumped to `view-5` (the view gains `sub`) and `snapshot-4`. PX-01 added `launches` to `RegistryRow` without bumping `snapshot-3`. It held up only because the pane reads `row?.launches ?? []`. This bump covers both changes.
- The new files `ui/mod/hooks/views/graph.tsx` and `overview.tsx` follow D-SCREENS' one file per screen, but they are not in the task's file list.
- `overview.tsx` imports `ageOf` from `detail.tsx`, and `detail.tsx` imports `Overview`. The cycle is safe because both are only used at render time. Moving `ageOf` to `style.tsx` would remove it.
- In `claude plugin test`, `ui.find({ key })` finds keyed Buttons but not keyed Texts, so the Overview tests match those lines by text.

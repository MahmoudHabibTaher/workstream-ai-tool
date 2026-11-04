# Session handoff

**State:** 13/16 done on `main` at `324f866`, as of 2026-11-04.

**Just landed:** RF-12 (`324f86618a`)

**Next:** `ws claim --commit RF-13 RF-14` (phase 4).

**Gotchas:**
- RF-12: - `decisions.relevant` is unchanged, so "Decisions that apply" can still show a closed entry with its `**Open.**` mark, as RF-10 noted. The new section uses `open_entries` and is right; the two can disagree in one brief. An open entry from a direct blocker also appears in both.
- The brief's line sends the worker to `ws decisions --open`, which reads the current checkout, so from a worktree it can miss closures made since the claim, as RF-10 noted. The brief's own section reads the tracking copy and may be the more current of the two.
- `make test` under `ws verify` took 238.0s, so the 180s shell limit moved it to the background again.
- `docs/rule-map.md` has no row for the new stop rule. It isn't in this task's files.

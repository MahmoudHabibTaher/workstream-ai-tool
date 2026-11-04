# Session handoff

**State:** 7/15 done on `main` at `a48a8ef`, as of 2026-11-04.

**Just landed:** RF-06 (`1a49870834`), RF-07 (`a48a8effa0`)

**Next:** `ws claim --commit RF-08` (phase 2).

**Gotchas:**
- RF-06: - The reason no longer appears on the web task screen or in `ws show`. Both only print `notes` (`src/workstream/assets/web/task.js:33`, `src/workstream/cli.py:373`), and until now the reason reached them by overwriting it. `blockedReason` is already in the snapshot's task data, so showing it is a small follow-up. Left alone: neither file is in this task's list, and D-REASON names only the handoff.
- `ws update` has no way to set `blockedReason`, so a hand-blocked task has no reason until someone adds that.
- I avoided the shared-TMPDIR problem RF-02 and RF-05 reported by setting a private TMPDIR, so this run neither reproduced nor ruled it out. Not fixed: out of scope.
- RF-07: - A workstream that exists only on a side branch can't be briefed or verified while another checkout is on the integration branch. `ws new` doesn't require the integration branch, so this can arise. From a linked checkout on `feature`, I got `error: no workstream with id 'gamma' (see `ws list --all`)` from `ws brief` after `ws new gamma` there. Before this change it read that checkout's registry. Claimed tasks aren't affected, since a claim has to be on the integration branch. Not worked around, because D-SOURCE says everything the brief reads comes from the integration checkout. A fallback for a workstream the integration checkout doesn't have would be small if this matters.
- From a worktree with no `-w`, the "only open workstream" fallback now counts the integration checkout's open workstreams. One opened since the claim gives a "several open" refusal rather than a guess. Briefs always pass `-w`, so workers don't hit it.
- `ws decisions` still reads the current checkout, so from a worktree it misses decisions made since the claim, including the "N more" a brief points to with `ws decisions --for`. Outside this task's issue as written.
- `ws verify` still reads `[commands]` and baselines from the worktree: the task's list is current, but what a key expands to is as of the claim. From reading the code, not run: a command key added to the config on the integration branch after the claim shows in the brief, but the worktree's config doesn't have it when verify runs.

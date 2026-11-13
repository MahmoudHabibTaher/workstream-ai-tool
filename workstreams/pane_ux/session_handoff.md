# Session handoff

**State:** 3/5 done on `main` at `1d0d4bb`, as of 2026-11-13.

**Just landed:** PX-03 (`1d0d4bb500`)

**Next:** `ws claim --commit PX-04` (phase 2).

**Gotchas:**
- PX-03: - The view tag was bumped to `view-6` for the new `'task'` screen.
- `ui/mod/hooks/views/detail.tsx` (the expansion removed, and `onReview`/`onJump` dropped from its props) and the existing tests in `detail.test.tsx` and `health.test.tsx` changed, though they are not in this task's files. The health tests now press Back from the task page before checking detail's Pause/Resume and Health.
- Review's Back going to the task page is not covered by a test. The review tests open Review from the task page but don't press Back.

# Session handoff

**State:** 4/14 done on `main` at `4e80f04`, as of 2026-11-04.

**Just landed:** LO-02 (`c753594bbc`), LO-03 (`36ddfd9c7b`), LO-04 (`4e80f04fbd`)

**Next:** `ws claim --commit LO-05 LO-06` (phase 3).

**Gotchas:**
- LO-02: - A plain `git status` rewrites the real index and smudges the racy entry, which hides this bug. My first version of the setup asserted with it, and both tests passed on `copyfile`. The setup now uses `git --no-optional-locks status`, and a comment there says why. Anyone reusing this setup needs the same.
- `EDITED` in `tests/test_gates.py:11` is deliberately a different size, with a comment saying a same-size edit can look clean to `code_tree`. That comment is now out of date. I left it, as the file is outside this task.
- LO-04: - `is_open` matches `**Open.**` anywhere in the text, so a closed reason that merely quotes that mark mid-text renders with no closed marker and counts as open. This is the same quoting problem as this task's, on the other mark. Not touched here.
- The shell moved `ws verify` to the background after 180s despite the longest timeout, because the full suite takes about 323s. The run still finished and recorded its result.

# Session handoff

**State:** 11/16 done on `main` at `89ac7cd`, as of 2026-11-04.

**Just landed:** RF-10 (`89ac7cdfd8`)

**Next:** `ws claim --commit RF-11` (phase 3).

**Gotchas:**
- RF-10: - This task was first blocked on `make audit` failing on `brief RF-15  2873 of 2500  OVER`, on main as well. D013 and RF-16 fixed that with a separate brief budget. RF-15's brief is still growing, now 3166 of 4500.
- `make test` took 269.9s under `ws verify`, so the 180s foreground shell limit moved the verify to the background. It still finished and recorded.
- `decisions.relevant` ignores closures, so a brief can still show a closed entry with its `**Open.**` mark, without the later entry that closed it. RF-12 is about open decisions in briefs and may want `open_entries`.
- `settle` and plain `ws decide` don't validate a `Closes:` first line written by hand, so a worker's proposal or a `--why` starting `Closes: D014.` closes D014 with no check.
- `ws decisions --open` reads the current checkout, as RF-07 noted for `ws decisions` generally, so from a worktree it misses closures made since the claim. `--closes` checks ids against that same copy.
- `docs/rule-map.md` and the skills still show `ws decide` without `--commit`, as RF-09 noted. Not changed here.

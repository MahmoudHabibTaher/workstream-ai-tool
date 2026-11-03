# Session handoff

**State:** 6/8 done on `main` at `eb321f0`, as of 2026-11-03.

**Just landed:** PI-04 (`eb321f045f`)

**Next:** `ws claim --commit PI-05` (phase 3).

**Gotchas:**
- PI-04: D014 and D015 on the pilot branch are still open, and both are the user's. MBZ-06 to MBZ-10 are unclaimed. Merging the branch would also need `branches.integration` changed from ws-pilot back to develop, and the old pane and `workstreams/tools` still expect the old file format there.

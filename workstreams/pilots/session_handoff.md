# Session handoff

**State:** 2/6 done on `main` at `23b64ae`, as of 2026-11-02.

**Just landed:** PI-02 (`23b64aefa6`)

**Next:** `ws claim --commit PI-03` (phase 2).

**Gotchas:**
- PI-02: A root-shape queue's top-level `validation` commands are dropped: its open tasks' keys come back as needing a person, and they go in [commands] by hand. Its old baselines don't convert: run `ws baseline record`. The old queues have no recorded verification, so open imported tasks start fresh.

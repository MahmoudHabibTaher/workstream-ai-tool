# Decisions: Pilots and measurement

Settled judgment calls, closed unless new evidence shows up. Append, never rewrite. To reverse an entry, add one that supersedes it.

Entry shape: `## Dnnn (YYYY-MM-DD, <who>): <the call>`, then the reason and the rejected alternative, ending **Closed.** or **Open.**

---

## D001 (2026-11-02, user): scope approved

The user asked to start M6. Standing limits: the Kotlin harness's repo gets nothing pushed and gives no content here; the real project's migration stays on a branch and merging is the user's call; further Copilot spend on the work account needs asking again; Opus 5.5 on medium effort is the preferred model. **Closed.**

## D002 (2026-11-02, PI-01): A checkout elsewhere counts when it names the same remote

The real sessions' worktrees sit beside the project on disk, so a path match found 37 of the sessions and none with per-call figures. Rejected: a folder-name prefix, which matches unrelated siblings. **Closed.**

## D003 (2026-11-02, PI-02): Conversion is one-way, in `ws import`, and `tasks.load` still refuses old versions

Otherwise the old shapes stay supported for good. Rejected: reading them on the fly. **Closed.**

## D004 (2026-11-02, PI-02): A frozen protocol copy is removed from open work and kept in closed work

Open work reads `ws protocol` now, and closed work is a record. Rejected: removing all of them, which rewrites history for no gain. **Closed.**

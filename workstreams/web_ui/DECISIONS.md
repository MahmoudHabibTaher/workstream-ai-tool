# Decisions: Web UI

Settled judgment calls, closed unless new evidence shows up. Append, never rewrite. To reverse an entry, add one that supersedes it.

Entry shape: `## Dnnn (YYYY-MM-DD, <who>): <the call>`, then the reason and the rejected alternative, ending **Closed.** or **Open.**

---

## D001 (2026-11-03, user): scope approved

The user asked for M8 and set its limits: localhost only, review screens first, no Node at runtime, nothing pushed, no sub-agents, no writes to a real project through the UI without asking. No build step was this session's call, reported to the user with a note that a build tool would be a separate decision. **Closed.**

## D002 (2026-11-03, WU-01): the queue is every reviewable task in an open workstream, with no notion of "reviewed"

Nothing in the tracking files says a person has reviewed a task, and adding it would be a new kind of write. The page keeps its own per-browser marks, keyed by `revision`. Rejected: a `reviewed` field on the task written through `ws act`, which is a tracked fact nothing else would read. **Closed.**

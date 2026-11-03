# Decisions: Web UI

Settled judgment calls, closed unless new evidence shows up. Append, never rewrite. To reverse an entry, add one that supersedes it.

Entry shape: `## Dnnn (YYYY-MM-DD, <who>): <the call>`, then the reason and the rejected alternative, ending **Closed.** or **Open.**

---

## D001 (2026-11-03, user): scope approved

The user asked for M8 and set its limits: localhost only, review screens first, no Node at runtime, nothing pushed, no sub-agents, no writes to a real project through the UI without asking. No build step was this session's call, reported to the user with a note that a build tool would be a separate decision. **Closed.**

## D002 (2026-11-03, WU-01): the queue is every reviewable task in an open workstream, with no notion of "reviewed"

Nothing in the tracking files says a person has reviewed a task, and adding it would be a new kind of write. The page keeps its own per-browser marks, keyed by `revision`. Rejected: a `reviewed` field on the task written through `ws act`, which is a tracked fact nothing else would read. **Closed.**

## D003 (2026-11-03, WU-02): a per-launch token as well as Host and Origin checks

Host and Origin stop a web page. They don't stop another account on the same machine, which can reach the port and would be able to read a private repo's diffs and commit as this user. The token costs one query parameter. Rejected: Host and Origin alone, which is what a dev server usually does, but a dev server doesn't commit. **Closed.**

## D004 (2026-11-03, WU-02): the cookie is SameSite=Lax

Strict isn't sent on the redirect after a link followed from another app's page, which shows a confusing 401 on first open. Lax still holds it back from cross-site POSTs and frames, and the Origin check stops the write anyway. Rejected: Strict. **Closed.**

## D005 (2026-11-03, WU-02): a stable port per project, chosen from the root's hash

A browser's own storage is per origin, so a fresh port each launch would lose the review queue's "seen" marks. If the port's taken, any free one is used. Rejected: a fixed port, as two projects can be served at once. **Closed.**

## D006 (2026-11-03, WU-03): the confirm box keeps the revisions from when it opened

With live updates, the latest snapshot would pass the guard for something the person never saw. So the box pins them, and warns if they've moved. Rejected: taking them at click time from the newest snapshot, which turns the guard off. **Closed.**

## D007 (2026-11-03, WU-03): copying a prompt stands in for filling a prompt box

A browser has no prompt box to fill. Copying leaves the send to the person, as the pane does. Rejected: launching an agent, which the plan rules out for a standalone page. **Closed.**

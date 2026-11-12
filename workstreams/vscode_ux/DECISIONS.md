# Decisions: VS Code UX redesign

Settled judgment calls, closed unless new evidence shows up. Append, never rewrite. To reverse an entry, add one that supersedes it.

Entry shape: `## Dnnn (YYYY-MM-DD, <who>): <the call>`, then the reason and the rejected alternative, ending **Closed.** or **Open.**

---

## D001 (2026-11-10, user): scope approved

The owner chose native views (keeping 0016) over a webview detail panel.
VS Code targets: Terminal, Copilot Chat and the Claude Code extension. Air has no VS Code version.
Copilot Chat must be installed in VS Code for the manual check; it isn't today. **Closed.**

## D002 (2026-11-12, VX-01): "waiting on" comes only from the snapshot's `waitingOn`

`detail.ts` drops the `waits on` badge that `format.ts`'s `badgesOf` works out from `blockedBy`, and the task row's description takes "waiting on" from `task.waitingOn` instead. This follows jetbrains_ux T3: the IDE doesn't compute graph facts. `format.ts` wasn't in this task's files, so I didn't change it.
Rejected: changing `badgesOf` in `format.ts` to read `waitingOn`. That touches the Registry view's badges, which VX-02 replaces anyway. **Closed.**

## D003 (2026-11-12, VX-01): the builders mint stable ids for every section, item and graph node

Each graph node's id is its path from the root, so a task that appears twice still gets two distinct ids. Section and item ids come from their position under the task's or overview's id. This keeps `TreeItem.id` stable across reloads (plan T2).
Rejected: leaving ids to the views. **Closed.**

## D004 (2026-11-12, VX-01): the snapshot shape types live in `registry.ts`

`SnapTask`, `Scope`, `Baseline`, `BaselineKey` and the widened `WsSnapshot` sit next to the existing `WsSnapshot`. `DetailRow` (the registry row's other fields) sits in `detail.ts`.
Rejected: a separate types module. **Closed.**

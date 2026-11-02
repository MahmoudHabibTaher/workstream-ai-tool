# Decisions: Project adaptation

Settled judgment calls, closed unless new evidence shows up. Append, never rewrite. To reverse an entry, add one that supersedes it.

Entry shape: `## Dnnn (YYYY-MM-DD, <who>): <the call>`, then the reason and the rejected alternative, ending **Closed.** or **Open.**

---

## D001 (2026-11-02, user): scope approved

The user said to start M4 after approving the overall plan, which has this tool's milestones run as workstreams on itself. Commands are verified by running them. Skills that need a worker pool are followed in the foreground, since this session starts no sub-agents unless asked. **Closed.**

## D002 (2026-11-02, AD-01): detection order lives in each profile as a `priority`

The literal check refused it in Python, rightly: a stack name there is what T1 forbids. It also means adding a stack touches one file. Rejected: an exempt constant in `profiles.py`, which would make the check mean less. **Closed.**

## D003 (2026-11-02, AD-02): `ws init` no longer writes a config when it refuses

The dirty-tree check runs before anything is created, so a refused init leaves no half-set-up repo behind. Rejected: writing the registry first, which is what a run needs, and cleaning it up on refusal. **Closed.**

## D004 (2026-11-02, AD-02): when every candidate fails, the comment shows one that actually ran

A failure says more than a tool not being installed. Rejected: always showing the first candidate, which would hide an npm failure behind a missing pnpm. **Closed.**

## D005 (2026-11-02, AD-03): a standard workstream doesn't ask for releaseImpact either

Only `full` ships, so the field means nothing elsewhere. This changes M1, where any project with a runbook required it. Rejected: requiring it on standard in a releasing project, which makes the tier choice mean nothing. **Closed.**

# Decisions: Project adaptation

Settled judgment calls, closed unless new evidence shows up. Append, never rewrite. To reverse an entry, add one that supersedes it.

Entry shape: `## Dnnn (YYYY-MM-DD, <who>): <the call>`, then the reason and the rejected alternative, ending **Closed.** or **Open.**

---

## D001 (2026-11-02, user): scope approved

The user said to start M4 after approving the overall plan, which has this tool's milestones run as workstreams on itself. Commands are verified by running them. Skills that need a worker pool are followed in the foreground, since this session starts no sub-agents unless asked. **Closed.**

## D002 (2026-11-02, AD-01): detection order lives in each profile as a `priority`

The literal check refused it in Python, rightly: a stack name there is what T1 forbids. It also means adding a stack touches one file. Rejected: an exempt constant in `profiles.py`, which would make the check mean less. **Closed.**

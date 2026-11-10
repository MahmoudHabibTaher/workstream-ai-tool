# Decisions: JetBrains UX redesign

Settled judgment calls, closed unless new evidence shows up. Append, never rewrite. To reverse an entry, add one that supersedes it.

Entry shape: `## Dnnn (YYYY-MM-DD, <who>): <the call>`, then the reason and the rejected alternative, ending **Closed.** or **Open.**

---

## D001 (2026-11-10, user): scope approved

The owner (2026-11-10) finds the other workstream plugin's UI better and asked for our UIs to favour it. It is another workstream plugin: ideas only, no code or text.
Master-detail: a list plus Tasks/Graph/Overview detail; Review, Health and Budget stay as their own tabs.
Launch targets: Terminal, Copilot Chat and Air. Air is reached by guarded reflection into non-public classes, falling back to the clipboard; an exception to 0018's no-internal-API rule.
Launch options: agent presets (agent, effort, permissions) that ws maps to flags from the adapter TOMLs, plus pre-flight checks, a task pin and an editable prompt.
Ruled out: porting the other workstream plugin's raw tasks.py commands; any write other than ws act. **Closed.**

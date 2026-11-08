# Decisions: JetBrains plugin

Settled judgment calls, closed unless new evidence shows up. Append, never rewrite. To reverse an entry, add one that supersedes it.

Entry shape: `## Dnnn (YYYY-MM-DD, <who>): <the call>`, then the reason and the rejected alternative, ending **Closed.** or **Open.**

---

## D001 (2026-11-08, user): scope approved

Owner, 2026-11-08, while planning M10:
- Target both IDEs: one plugin built against platform 262 must install and work in IntelliJ IDEA 2026.3 (263) and Android Studio 2026.2 (262). PyCharm and older builds are out.
- The snapshot owns the launch prompts: each open registry row gains `launches`, so the Kotlin copies no prompt text. This settles M9's open question about launch offers (vscode_extension D022). The web UI, pane and VS Code keep their copies for now.
- Native UI calling the ws CLI, per decision 0016; no ws serve, no JCEF webview. **Closed.**

## D002 (2026-11-08, JB-01): `launches` is required on every row, and `snapshotVersion` stays 1

Every row the snapshot builds carries `launches` (empty when closed), so the schema requires it, as it does `actions`; the field is additive, as `actions` and `refresh` were without a version bump. Rejected: optional `launches`, which would let a consumer meet a row without it; bumping to 2. **Closed.**

## D003 (2026-11-08, JB-01): the prompt is filled with the row's id in the snapshot

`prompt` holds the finished text (`{ws}` already replaced), so the plugin copies nothing and formats nothing. Rejected: a template with `{ws}` for the UI to fill. **Closed.**

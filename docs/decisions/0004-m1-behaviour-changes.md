# 0004: Deliberate behaviour changes from the subsonic CLIs

- **One CLI.** `manage_tasks.py` and `manage_workstreams.py` become `ws`. A workstream is selected with `-w`, the current directory, or being the only open one, not `--file <path>` on every call.
- **`verify` is a list** of named command keys or raw commands, not one string. Named keys resolve through `[commands]`.
- **`releaseImpact` is required only when `release.mode` is not `none`.** Most projects don't release per workstream.
- **`requires` values come from config.** The defaults drop the subsonic-specific `media-library`.
- **`done` is reached through `ws close`, not `set-status`.** Closing is a checked operation, and `abandoned` now requires `--notes`, so the reason is recorded.
- **A workstream's folder may sit anywhere** (`path` in its registry row), for the Kotlin harness's module-level `workstreams/` folders.
- **Per-workstream `AGENTS.md` is gone.** The protocol moves to one versioned file in M3.
- **`wrong-branch` is a warning, not an error.** Sitting on a feature branch is normal in most repos, and it only disables UI writes.
- **`show` and `next` print compact text by default**, with `--json` for tools. They ran about 1.8 KB of JSON per call in subsonic.
- **Older queues are refused, not silently upgraded.** A `schemaVersion` other than 3 is an error. The subsonic CLI's tests for reading schema 1 and 2 in place weren't ported; `ws import` (M6) is the way across.
- **the Kotlin harness's `clear` isn't carried over.** Re-planning the same folder under a new graph is rare, and `reset` plus a new workstream covers it.
- **Two inherited weaknesses are closed.** A registry `path` can no longer leave the repository, which `close --purge` would otherwise delete, and a revision starting with `-` can no longer reach `git diff` as an option.

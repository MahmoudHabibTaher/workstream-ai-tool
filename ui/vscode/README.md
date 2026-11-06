# Workstreams for VS Code

Shows a workstream project in VS Code's own UI. Every fact comes from the `ws` CLI and every write goes through `ws act`; the extension only arranges what the CLI returns (decision 0016).

## Install

```sh
make vsix
code --install-extension ui/vscode/workstreams.vsix
```

The extension runs only in trusted workspaces, and not in virtual ones.

## Settings

- `workstreams.wsCommand`: the argv that runs the CLI, `["ws"]` by default. No shell parses it. Point it at a checkout's own code with `["python3", "-B", "-m", "workstream"]` and that checkout's `src` on `PYTHONPATH`.

When the CLI can't be started, the extension says so, names this setting, and runs nothing else. A window whose folders aren't workstream projects gets one message and nothing more.

## Develop

- `npm ci` in `ui/vscode` (a worktree's setup runs it).
- `make test` runs the logic tests under node, through `tests/test_vscode_files.py`.
- `make test-vscode` builds with `tsc` and runs the integration tests in the VS Code installed at `/Applications/Visual Studio Code.app` (override with `VSCODE_EXECUTABLE`). Nothing is downloaded. They run the checkout's own CLI, not the `ws` on PATH.
- Logic lives in modules that never import `vscode`, written in erasable TypeScript so `node --test` runs the `.ts` files directly.

# 0010: The Claude Code pane

Decided while building M7. The workstream's own `DECISIONS.md` has the smaller calls, and [the pane's guide](../../ui/mod/README.md) has how to install and use it.

**The pane draws and asks, and nothing else.** Every fact comes from `ws snapshot` and `ws review`, and every write goes through `ws act`, which refuses, writes and commits in one call. A new fact goes in Python with a test, not in TypeScript. Closing and abandoning aren't actions: those buttons only fill the prompt box, and nothing is sent until the user presses Enter.

**The CLI says where the project is.** `ws root` prints the checkout holding the integration branch, or the current one if none does. The old pane took the parent of git's common dir, which is wrong for a project in a linked checkout, as the pilot showed, since only the config knows the integration branch.

**The snapshot gained three fields, with no new version.** `watch` lists the files whose change should redraw, `verifyCommands` holds each verify entry's label and command, and `acceptanceText` holds each acceptance item as text. A UI can't work out any of these without the config or the queue's rules, and M8 and later will need the same ones.

**It took over the old pane's name.** It's `workstreams-pane@workstream`, with the command `/workstreams`. The two can't share a name and both be installed, as which one answers is left to chance, so for a while this one was `ws-pane`. Once it had been seen working, the user removed the old plugin and gave this one the name. So the Rust project's integration branch has no pane until its migration merges: `/workstreams` there says it isn't a project.

**It's a plugin from a folder marketplace at the repo root.** The source is a relative path, so it's read from the working tree: edits show up on `/reload-plugins`, and it doesn't load on a branch without `ui/mod`. Rejected: shipping it inside the Python package, which adds nothing while this stays private.

## Rules for changing it

- **Buttons and text only.** Mobile has no `Input` or `Select`.
- **State lives in `$.state` atoms,** declared in `types/index.d.ts`, with a shape tag bumped whenever a value's fields change. Module variables die on a reload.
- **Never call `$.prompt.submit`.** Prompts are filled.
- **One file per screen,** in `hooks/views/`, with the shared look in `style.tsx`.
- **The mod names no project, stack or old skill.** `tests/test_mod_files.py` holds that in `make test`, and runs the real `ws` with the commands the mod sends. The mod's own tests stub `ws` and need the agent's CLI, so they're in `make test-mod`.
- **One test file may be at most 1 MiB,** which is why real data isn't kept as a fixture.

## What was shown

| Check | Result |
|---|---|
| `claude plugin test`, with `ws` stubbed | 25 pass |
| `claude plugin validate` | Passes, with warnings such as a missing icon |
| Type-check against the engine's types | Clean |
| Marketplace add and install | Works, on this machine at user scope |
| `/workstreams` with a real `ws`, headless | Opens on this repo, a sample project, a task's worktree, the pilot branch and an explicit path, and refuses a folder that isn't a project |
| Every screen on all four surfaces, with real snapshots from three repos | 12 pass, before the rename. A scratch test, not committed, as it holds real project data |
| Seen drawn in a real app | The user opened it in the desktop app on this repo, which isn't the Rust project, and it looks good |

## Not proven

- **The other three surfaces on a real screen.** Terminal, VS Code and mobile have only been through the test harness's elements.
- **A write from the pane in real use.** `ws act` is tested, and the pane's confirm flow is tested with `ws` stubbed.
- **That the settings on `ws-pilot` are enough to run the pane there.** It opens headless, and hasn't been looked at.

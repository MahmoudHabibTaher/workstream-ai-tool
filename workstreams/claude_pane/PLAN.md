# Claude Code pane: plan

## 1. Context

M7 of `docs/plan.md`. The Rust project has a working pane, a Claude Code mod beside the chat that draws its harness's read model. The gate passed, so it comes across, tied to no project.

**Outcome:** `/workstreams` opens the pane in any project with `.workstream/config.toml`, on the same screens: registry, detail, health, feed and review. It's a plugin in a marketplace at this repo's root. `claude plugin test` passes, and it works on a repo that isn't the Rust one.

**Out of scope:** new screens, the web UI (M8), publishing the marketplace, and changing the Rust project's branch.

## 2. Traps

### T1: the pane is never a writer
Every write goes through `ws act`, and every fact comes from `ws snapshot` and `ws review`. A new fact goes in Python with a test, not in TypeScript.

### T2: "the main checkout" isn't always the project
The old pane took the parent of git's common dir. A project run from a linked checkout, as the pilot is, has its integration branch somewhere else, and that main checkout may not be a project at all. Only the CLI knows the integration branch.

### T3: the old pane knows its project
A CLI path, a `workstreams/` folder, `develop`, and two old skill names. The folder is configurable here, and the skills have new names.

### T4: `verify` changed shape
It's now a list that may hold keys, and `acceptance` items may be typed. The pane can't resolve a key without the config, so the snapshot must carry the text.

### T5: `ws` may not be on the app's PATH
The old pane ran a script inside the repo. This one runs an installed command, from an app that may not have a login shell's PATH. A missing `ws` has to say so, not read as "not a project".

### T6: buttons and text only
Mobile has no `Input` or `Select`. State lives in `$.state` atoms with shape tags, and prompts are filled, never submitted.

## 3. Design

### D-ROOT: `ws root`
Prints the checkout that holds the integration branch, or the current one if none does. The pane runs it instead of asking git. An explicit `/workstreams <path>` runs it there.

### D-SNAPSHOT: three additive fields
`watch` lists the files whose change should redraw, `verifyCommands` holds each entry's label and command, and `acceptanceText` holds each item as text. `snapshotVersion` stays 1.

### D-PACKAGE: `ui/mod`, and a marketplace at the root
A relative source, so the plugin follows the working tree. `make test-mod` runs validate and test, locally, as `make eval` does. Rejected: shipping the mod inside the Python package, which adds nothing while it's private.

## 4. Tasks

| ID | Title | Blocked by |
|---|---|---|
| CP-01 | `ws root` and the snapshot's new fields | |
| CP-02 | Port the pane | CP-01 |
| CP-03 | Package it, and check it on another repo | CP-02 |
| CP-04 | Docs say what is true | CP-03 |

All run in the foreground: this session starts no sub-agents unless asked.

## 5. End-to-end verification

`/workstreams` on this repo and on a sample repo that isn't the Rust project: a real `ws` behind it, with a task worktree and a linked checkout both resolving to the right root.

# 0016: The IDE extensions use native UI, not a webview

Decided with the owner on 2026-11-06, before M9 started. It replaces the plan's "key UI decision" for the IDEs: the plan stays as written, and this record says what changed.

**What the plan said.** One web UI would serve the browser, a VS Code webview and a JetBrains JCEF panel, so each IDE plugin stayed a thin wrapper.

**What changes.** The VS Code extension (M9) and the JetBrains plugin (M10) are built from each IDE's own UI framework. Neither embeds the web UI. The owner chose this so the extensions can use what the IDE already does well, instead of drawing a second app inside it.

**What stays.** The web UI from M8 stays as the standalone GUI, for the browser. The Claude Code mod stays as it is.

## What native buys

| Need | VS Code | JetBrains |
|---|---|---|
| Registry, waves and tasks | Tree view in its own view container | Tool window with a tree |
| A task's detail | Tree items, hovers, and the task's files opened in the editor | Tool window panel built with the Kotlin UI DSL |
| A review's diff | The built-in diff editor (`vscode.diff`) on the task's branch | The platform's diff viewer |
| Health findings | Diagnostics in the Problems panel | Notifications and a tool window list |
| At-a-glance state | Status bar item | Status bar widget |
| Actions (pause, resume, unclaim, sync) | Commands, in the palette and on tree items, with a modal confirm | Actions, in Find Action and on tree nodes, with a confirm dialog |
| Running a workstream | An integrated terminal, as M9 planned | The Terminal tool window |
| Keeping current | A file watcher on the snapshot's `watch` paths | VFS listeners on the same paths |

Theming, keyboard use, accessibility, settings and search come with the IDE rather than being rebuilt.

## How the extensions get their facts

**They call the `ws` CLI and read its JSON.** `ws snapshot`, `ws review --checks` and `ws review --queue` already return everything the web UI shows, and `ws act` is the one write. So neither extension needs `ws serve`, and the token, cookie and framing problem that 0011 left for M9 goes away. Rejected: talking to `ws serve` over HTTP, which adds a server to start, guard and keep alive for no fact the CLI lacks. If a screen ever needs something only the server has, it moves into the CLI first.

## Rules carried over from 0011

- **One writer.** Every write goes through `ws act`. A new kind of write starts there.
- **The extension decides nothing.** A new fact goes in Python with a test. Kotlin and TypeScript only arrange what the CLI returns.
- **Hashes are taken when the confirm opens.** The confirm passes the `revisions` from the snapshot it was drawn from, so a refresh just before a click can't approve something nobody saw. A refusal from `ws act` is shown as it is.
- **Repo text is text.** Titles, notes, proofs and diffs never become markup or commands.
- **Names no project.** The literals test covers the extensions' sources.

## What it costs

- **Two UIs to build and keep in step,** in TypeScript and Kotlin, instead of one shared page. Each screen is written twice. Keeping every fact in the CLI is what keeps the two from drifting.
- **Bigger milestones.** M9 and M10 were each sized M on the thin-wrapper assumption. Expect each nearer L, which the M9 plan should estimate properly.
- **A JVM toolchain.** M10 needs Gradle and the IntelliJ Platform Gradle Plugin, a first for this repo.

## Done means

Unchanged from the plan: M9 works in VS Code and Cursor, and M10 works in IntelliJ and Android Studio. Each also has to show that a stale action is refused, as M8 did.

# Workstreams for IntelliJ IDEA and Android Studio

A plugin that shows a project's workstreams with the IDE's own UI. Every fact comes from the `ws`
CLI, and the only write is `ws act` (decision 0016). It is built against IntelliJ IDEA 2026.2
(build 262) and installs in IntelliJ IDEA 2026.3 and Android Studio 2026.2.

## Build and test

From the repo root:

| Command | What it does |
|---|---|
| `make test-jetbrains` | `./gradlew test`: the JUnit tests and the headless IDE tests |
| `make jetbrains-zip` | `./gradlew buildPlugin`: writes `ui/jetbrains/build/distributions/*.zip` |
| `make verify-jetbrains` | `./gradlew verifyPlugin` against the local IntelliJ IDEA and Android Studio |

`make test` also runs `tests/test_jetbrains_files.py`, which needs no JVM: it scans `src/` for
project and agent names and markup sinks, and runs every argv `Cli.kt` builds through the real CLI.

The build needs:
- **A JetBrains Runtime 25.** The Gradle toolchain asks for JetBrains' JDK 25 and finds it among
  the installed JDKs (on a Mac, under `~/Library/Java/JavaVirtualMachines`). It never uses
  `JAVA_HOME` and never downloads one. To point at another, set
  `org.gradle.java.installations.paths` in `~/.gradle/gradle.properties`.
- **The network, once.** The first build downloads the 262 platform, about 1 GB, into `~/.gradle`.
  Every worktree shares that cache.
- **The two IDEs, for `verify-jetbrains`.** By default they are `~/Applications/IntelliJ IDEA.app`
  and `~/Applications/Android Studio.app`. Pass `-PlocalIdea=...` or `-PlocalStudio=...` to
  `./gradlew` to use others.

The headless tests run this checkout's CLI (`python3 -B -m workstream` with `PYTHONPATH` set to
its `src`), passed through the `wsCommand` setting. They never run the `ws` on PATH, which runs
main's code.

## Install

Settings | Plugins | the gear | Install Plugin from Disk, then pick the zip.

## Settings

Settings | Tools | Workstreams holds two commands. Each is split into an argv the way a run
configuration's arguments are, and neither goes through a shell.
- **ws command**, `ws` by default. An IDE started from the Dock or Toolbox may not have your shell's
  PATH, so if `ws` doesn't start, set the full path, such as `~/.local/bin/ws` written out in full.
- **Agent command**, empty by default: what the launcher starts in the Terminal.

## What it shows

- **The Workstreams tool window, Registry tab.** Each open workstream with its status, `done/total`
  and error count. A workstream opens to its wave line, its phases, each phase's tasks with badges,
  then Documents, whose files open in the editor on double-click or Enter. **Show Done** adds the
  done and abandoned workstreams; **Refresh** reads the snapshot again.
- **Review tab.** The `ws review --queue`: **On a branch**, then **Landed**. A task opens to its
  range, its gate summary and gates, each acceptance item with its proof, its Evidence, then Files.
  A file opens in the diff viewer with both sides from `ws review --show`, each titled with its
  revision, so a branch's old side is its merge base; a binary file opens nothing and says so. A
  landed task's evidence opens as its file, a branch task's read-only as the branch holds it.
- **Health tab.** The snapshot's findings, errors first. A finding that offers a fix (an unclaim of
  a stale claim, say) has it on its context menu. New errors since the last reload raise one
  notification between them, whose **Show Health** opens this tab.
- **Budget tab.** `ws audit context`: what each role's context costs against its limit. It runs
  only while the tab is showing; Refresh drops the held rows.
- **The status bar.** The first active workstream's wave line and error count. Clicking it opens
  the tool window.
- **Live refresh.** Every path in the snapshot's `refresh` list is watched by the IDE. A change
  under one of them, such as a commit from a shell, reloads the snapshot once per 300 ms burst, and
  so does the IDE window regaining focus.

## Writes and launches

- **Writes.** Pause, Resume, Sync and Unclaim are on a node's context menu only where the snapshot
  offers them. Each asks first, then runs `ws act` pinned to the revisions the node was drawn
  with, so a change made from a shell while the box is open is refused as stale and nothing is
  committed.
- **Run.** A workstream's launches come from the snapshot. Run starts the agent command in a new
  Terminal tab, in the project folder, with the prompt as its last argument. With no agent command
  set, or without the Terminal plugin, the prompt goes to the clipboard.

## Known issues

- The tool window's id is `Workstreams`. Another plugin that registers a tool window with the same
  id (one such is installed in some Android Studio setups) clashes with it; disable one of them.
- IntelliJ IDEA 2026.3's verifier reports one deprecated call, `FileEditorManager.openFile`, used
  in `ReviewOpen.openEvidence` to open a task's evidence from the Review tab.

## Layout

- `src/main/kotlin/dev/workstream/jetbrains/`: the platform code. `Cli.kt` is the one class that
  runs `ws`, always off the UI thread. `Text.kt` builds every piece of HTML, escaping repo text.
- `src/main/kotlin/dev/workstream/jetbrains/logic/`: plain Kotlin that never imports the platform:
  the ports of the VS Code extension's `waveLine`, `badgesOf`, `lanes`, `splitRows`, `gateSummary`,
  `rangeLine`, `statLine` and its Registry and Review trees.
- `src/main/resources/META-INF/plugin.xml`, plus `workstreams-terminal.xml`, which loads only when
  the Terminal plugin is there.
- `src/test/kotlin/`: JUnit tests, and headless `BasePlatformTestCase` tests against a sample
  project the branch's CLI builds.

The headless tests disable the IDE's bundled `com.intellij.modules.ultimate` plugin: its startup
activity can't be built in a light test project, and the plugin uses nothing from it.

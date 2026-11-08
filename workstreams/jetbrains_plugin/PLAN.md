# JetBrains plugin: plan

## 1. Context

M10 of `docs/plan.md`, on decision 0016 (`docs/decisions/0016-native-ide-ui.md`): the IntelliJ Platform's own UI, with every fact and write coming from the `ws` CLI, as the VS Code extension does (decision 0017, `docs/decisions/0017-vscode-extension.md`). M9 already put the facts a native UI needs into the CLI: the snapshot's row `actions` and `refresh` paths, and `ws review --show`. This milestone draws them with Swing, the platform's tool windows, its diff viewer, notifications, status bar and Terminal.

**Outcome:** one plugin zip built from `ui/jetbrains`, installed in IntelliJ IDEA 2026.3 (build 263) and Android Studio 2026.2 (build 262) on this Mac, that shows:
- a project's registry, waves, tasks and documents; the review queue and a task's review; health; the context budget;
- reviews in the platform's diff viewer, health findings as notifications and in a list, and a status bar widget;
- actions for pause, resume, unclaim and sync that go through `ws act`, behind a confirm dialog.

A write that's current lands, and a stale one is refused. Run, Coordinate, Close and Abandon start the configured agent in the Terminal tool window, with prompts that come from the snapshot.

**Out of scope:**
- PyCharm, other JetBrains IDEs, and platform builds older than 262.
- JetBrains Marketplace publishing; the repo stays private and ships a local zip.
- Chat or AI Assistant as a launch target; the launcher takes a second target later.
- New kinds of write.
- Moving the web UI, the pane or the VS Code extension onto the snapshot's `launches`.
- Untrusted projects, remote development and Gateway.

## 2. Traps

### T1: the two IDEs are on different platforms
`~/Applications/IntelliJ IDEA.app/Contents/Resources/product-info.json` says build `263.7307.200`, and Android Studio's says `262.10968.63`. A plugin built against 263 with no `sinceBuild` may not load in Android Studio. Set `sinceBuild = "262"`, leave `untilBuild` open, and compile against a 2026.2 (262) IntelliJ release from JetBrains' repository. Don't compile against the local Android Studio: its build number has no matching test-framework artifact. `verifyPlugin` checks both local installs through `pluginVerification { ides { local(...) } }`. Depend only on `com.intellij.modules.platform`, with `org.jetbrains.plugins.terminal` optional through its own config file. Never depend on `com.intellij.modules.java`.

### T2: Swing renders repo text as HTML
`JLabel`, tooltips and `Messages` dialogs treat a string starting `<html>` as markup, and `Notification` content is always HTML. A title, note or proof could therefore draw markup or a link. Tree nodes use `ColoredTreeCellRenderer.append`. Every tooltip, dialog message and notification body is built through one helper, `Text.kt`, which escapes repo text (`XmlStringUtil.escapeString`) and wraps it in `<html>` itself. Hyperlinks come only from the plugin's own constants. A source test holds this, the counterpart of M9's T6.

### T3: the IDE has neither the user's PATH nor a free UI thread
`ws` lives in `~/.local/bin` (`which ws`), and an IDE started from the Dock or Toolbox doesn't inherit the shell's PATH. Build commands with `GeneralCommandLine(argv).withParentEnvironmentType(CONSOLE)` from the `wsCommand` setting (an argv list, default `["ws"]`), with `GIT_OPTIONAL_LOCKS=0` (M9's D015). Calling the CLI on the EDT freezes the IDE: a snapshot takes about 0.4 s. Run every call on a background coroutine or pooled thread, with a 60-second timeout, and update Swing on the EDT. A missing `ws` gives one notification naming the setting.

### T4: `ws` on the PATH runs main's code
As M9's T5 found, a bare `ws` runs main's editable install, so tests in a worktree must run the branch's CLI: `python3 -B -m workstream` with `PYTHONPATH=<worktree>/src`, passed to the Gradle `test` task as an environment variable.

### T5: VFS sees outside changes only for watched roots
A commit from a shell reaches `BulkFileListener` only if the path is under a root the VFS watches, and `.git` internals usually aren't. Register every path in the snapshot's `refresh` with `LocalFileSystem.addRootsToWatch`, keeping each entry's recursive flag, and release them when the project closes. Filter `VFS_CHANGES` to those paths and debounce them 300 ms with `MergingUpdateQueue` or `Alarm`, for one snapshot per burst. Also reload when the IDE window regains focus (`ApplicationActivationListener`), and offer a Refresh action.

### T6: a fourth copy of the prompts
`promptText` lives at `src/workstream/assets/web/logic.js:79`, with copies in the pane and `ui/vscode/src/logic/launch.ts:10`. The owner chose to have the snapshot own them instead. Each open registry row gains `launches`. The snapshot schema is closed (`schema/snapshot.schema.json`, `additionalProperties: false`), so it gains the field too. Rows are built in `snapshot.row` (`src/workstream/snapshot.py:408`), beside `row_actions` (`snapshot.py:343`). "Open" means not `done` and not `abandoned`, as in `lanes.js:33`.

### T7: a terminal tab is a shell
`TerminalToolWindowManager.createShellWidget(...)` followed by `sendText` leaves quoting to the user's shell, and the abandon reason is free text. Both IDEs' `terminal.jar` have `createNewSession(String workingDir, String tabName, List<String> command, boolean requestFocus, boolean deferSessionStart)`, checked with `javap` on builds 262 and 263. It runs the agent's argv as the tab's process, with the prompt as the last argument. With no `agentCommand`, or without the Terminal plugin, the prompt goes to the clipboard and the notification names the setting. M9's owner found that fallback confusing, so the message must say why.

### T8: a refresh just before a click
As in 0011 and M9's T7, the confirm passes the `revisions` of the snapshot the node was drawn from, taken when the dialog opens. `Messages` dialogs are modal and can't redraw, so whether the view is out of date is judged when the dialog opens, as M9's D020 did. `ws act` still decides, and its refusal is shown as given, escaped (T2).

### T9: the JVM and Kotlin on this machine
The default `java` is Zulu 19 (`java -version`). The 2026.x platform needs a newer toolchain: JBR 25 is at `~/Library/Java/JavaVirtualMachines/jbr-25.0.4.1`. Set it with the Gradle JVM toolchain, or `org.gradle.java.installations.paths`, never by relying on `JAVA_HOME`. Set `kotlin.stdlib.default.dependency = false`, so the plugin uses the IDE's bundled Kotlin stdlib instead of shipping its own. The Gradle cache already holds IntelliJ Platform Gradle Plugin 2.19.0, and wrapper distributions 9.5.1 to 9.7.1. Pin the wrapper to a cached one unless the plugin needs newer. The first build still downloads the 262 platform, about 1 GB.

### T10: the source scans cover only core, the pane and VS Code
`tests/test_no_project_literals.py:13` scans `src/workstream`, and `tests/test_vscode_files.py:24` covers `ui/vscode`. 0016 says the literals rule covers every extension's sources. So `tests/test_jetbrains_files.py` scans `ui/jetbrains/src` for project and agent literals and for markup sinks (T2). It also shows the real CLI accepts each argv `Cli.kt` builds, as `tests/test_vscode_files.py:213` does. It needs no JVM, so it runs in `make test`.

### T11: build outputs and worktrees
Gradle writes `ui/jetbrains/build/`, `ui/jetbrains/.gradle/` and `ui/jetbrains/.intellijPlatform/`, all of which must be ignored. Its caches live in `~/.gradle`, which every worktree and the main checkout share. So unlike M9's npm install (`.workstream/config.toml` `[worktree] setup`), no setup line is needed. `ws settle`'s post-merge run in the main checkout works without one, which is the gap that skipped VS-03's check.

### T12: notifications on every reload
A health notification on every snapshot would bury the IDE. Notify only for an error finding not yet notified in this session, keyed by kind, workstream, task and message. The Health list always shows them all.

## 3. Design

### D-LAUNCHES: the snapshot owns the prompts
`snapshot.py` gains `LAUNCH_PROMPTS`, the same four texts as `logic.js:79-84`. Each open row gains `launches`, a list of `{kind, prompt}` in the order run, coordinate, close, abandon. Abandon's entry also has `"ask": "reason"`. Its prompt ends at `: `, and the UI appends the person's reason. A closed row gets `[]`. The schema gains the field. It is tested in `tests/test_snapshot.py` and `tests/test_schema.py`, and a test holds `LAUNCH_PROMPTS` equal to `promptText`'s strings, so the copies can't drift until they're removed. Rejected: a fourth table in Kotlin (owner's choice).

### D-PKG: the Gradle project
`ui/jetbrains/` holds:
- `settings.gradle.kts`, `build.gradle.kts`, `gradle.properties` and the wrapper, with `gradle-wrapper.jar` committed. It uses the Kotlin JVM plugin and IntelliJ Platform Gradle Plugin 2.x, with the platform at IntelliJ IDEA 2026.2 (262), `sinceBuild` 262 and the T9 toolchain.
- `src/main/resources/META-INF/plugin.xml`, plus `workstreams-terminal.xml` for the optional Terminal dependency.
- `src/main/kotlin/` for the platform code, and `src/main/kotlin/.../logic/`, plain Kotlin that never imports `com.intellij`.
- `src/test/kotlin/` for JUnit logic tests, and headless platform tests (`BasePlatformTestCase`) that build a sample project with the branch's CLI (T4).
- `README.md`, the guide.

`make test-jetbrains` runs `./gradlew test` and is local only, like `test-vscode`. `make jetbrains-zip` runs `buildPlugin`, which writes `ui/jetbrains/build/distributions/*.zip`. `make verify-jetbrains` runs `verifyPlugin` against the two local IDEs. `tests/test_jetbrains_files.py` does the scans in T10.

### D-CLI: one class talks to `ws`
`Cli.kt` follows `ui/vscode/src/cli.ts`. It has `resolveRoot` (`ws root`), `loadSnapshot` (which checks `snapshotVersion == 1`), `loadReview` (`--checks`, `--file`, `--show`), `loadQueue`, `loadBudget` (`ws audit context --json`) and `runAct` (`--expect-registry`, `--expect-tasks`, `--task`). JSON is parsed with the platform's bundled `kotlinx.serialization` or Gson, and adds no new library. It is the only class that starts a process apart from the launcher (T7). `runAct` is the only write. Settings (`wsCommand`, `agentCommand`) are an application-level `PersistentStateComponent`, with a page under Settings → Tools → Workstreams.

### D-VIEWS: a Workstreams tool window
One tool window, Workstreams, has tabs for Registry, Review, Health and Budget.
- **Registry.** It is a tree, like VS Code's: each open workstream shows its status, `done/total` and error count. A workstream opens to its wave line, then its phases, then each phase's tasks with badges. Last comes Documents, whose files open in the editor. A **Show done** toggle adds the closed workstreams. Tooltips hold the summary, acceptance and verify, escaped (T2). `logic/` ports `waveLine`, `badgesOf`, `lanes`, `splitRows`, `gateSummary` and `rangeLine`, as M9 did, with JUnit tests that mirror `ui/vscode/test/logic`.
- **Status bar.** A `StatusBarWidgetFactory` shows the first active workstream's wave line and error count, as M9's D017 does. Clicking it opens the tool window.
- **Live refresh.** As in T5.

### D-ACTIONS: writes and launches
Pause, Resume, Sync and Unclaim are `AnAction`s in the tree's popup menu and in Find Action. They're enabled only where the node's row `actions`, or its finding's `actions`, offer them. Each opens a confirm naming the commit line and the integration branch, with pinned revisions (T8), then calls `runAct`. `Launch.kt` holds the launch targets: the terminal (T7), then the clipboard. Callers don't know which one ran. Run, Coordinate, Close and Abandon come only from the row's `launches` (D-LAUNCHES); Abandon asks for the reason in an input dialog first.

### D-REVIEW-UI: review, health and budget
- **Review.** It has the queue's **On a branch** group, then **Landed**. A task opens to its range, its gate summary and gates, each acceptance item with its proof, and Evidence. A landed task's evidence opens as the file. A branch task's opens read-only as a `LightVirtualFile` from `--checks`. Then come Files, one per diffstat entry. A file opens `DiffManager.showDiff` on a `SimpleDiffRequest`, with both sides from `--show` (`DiffContentFactory.create`) and titled with each side's `rev`. A binary side opens nothing and says so. Kotlin never runs git.
- **Health.** It lists the findings, errors first, in the CLI's order. A finding's actions are in its popup and go through the same confirm. A new error finding also raises a notification (T12), whose action opens the Health tab.
- **Budget.** It shows each role's tokens against its limit, the share used, and `over`. It runs `ws audit context --json` when the tab is first selected and on Refresh, not on file-change reloads, as M9's D030 does.

## 4. Tasks

| ID | Title | Blocked by |
|---|---|---|
| JB-01 | The snapshot offers each open row's launches | |
| JB-02 | The plugin's Gradle project, CLI class and test harness | |
| JB-03 | Registry, documents, status bar and live refresh | JB-02 |
| JB-04 | Writes through `ws act`, and launching in the Terminal | JB-01, JB-03 |
| JB-05 | The review queue and diffs in the diff viewer | JB-04 |
| JB-06 | Health, notifications and the budget | JB-05 |
| JB-07 | Prove it in IntelliJ and Android Studio, and write down what's true | JB-06 |

- JB-01 (Python) and JB-02 (Gradle) share no files, so they can run at once.
- JB-03 to JB-06 all touch `plugin.xml` and the tool window, so they're chained.
- JB-07 runs in the foreground, because the owner has to see the plugin drawn in both IDEs.

## 5. End-to-end verification

1. `make jetbrains-zip` builds the plugin. It installs from disk into IntelliJ IDEA 2026.3 and Android Studio 2026.2, and loads in both. `make verify-jetbrains` reports it compatible with both local IDEs.
2. On a sample project built with the real CLI from an installed wheel, in IntelliJ:
   - every tab draws, and so does the status bar widget;
   - a pause commits through `ws act`;
   - a stale pause is refused, using a shell commit made while the dialog was open, and the refused write doesn't move HEAD;
   - a diff opens in the diff viewer for a branch task after main moved, and shows only the task's changes;
   - a health finding shows in the list, raises a notification, and its Unclaim lands;
   - Run starts the configured agent in a Terminal tab, and with no setting the prompt is copied.
3. In Android Studio, on the same sample: the tool window draws, and one write lands.
4. This repo is viewed read-only in IntelliJ, and its HEAD, status and refs are the same afterwards.
5. The owner sees it drawn in both IDEs.
6. `ui/jetbrains/README.md` and `docs/decisions/0018-jetbrains-plugin.md` are written, the latter with what was shown and what is not proven. The plan's M10 status row links them, and `README.md` names the plugin.

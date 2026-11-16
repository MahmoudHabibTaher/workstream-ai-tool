# 0018: The JetBrains plugin

Decided while building M10. The workstream's own `DECISIONS.md` has the smaller calls (D001 to D025, and JB-07's), and [the guide](../../ui/jetbrains/README.md) has how to use it. Why native UI rather than a JCEF panel over `ws serve`: [0016](0016-native-ide-ui.md). It follows the VS Code extension's rules ([0017](0017-vscode-extension.md)) wherever the platform allows.

**The plugin decides nothing.** Every fact comes from `ws snapshot`, `ws review` or `ws audit context`, and every write from `ws act`. The Kotlin only arranges what the CLI returns. When a view needed a fact the CLI didn't give, the fact went into Python first: each row's `launches`, with the prompt already filled in (JB-01, D002, D003).

**Writes are pinned to what was drawn.** The confirm is a modal that can't redraw, so whether the view is behind is judged as it opens, and `ws act` gets the revisions the node was drawn with (D017). A change made from a shell while the box is open is refused as stale.

**Launches start a process, not a shell line.** The agent command is an argv, and the prompt is its last argument. The Terminal tab is opened through the public `createNewSession(runner, TerminalTabState)`, not the internal five-argument overload (D014). Launch targets are an extension point, so the Terminal one loads only when the Terminal plugin is there; otherwise, or with no agent command, the prompt goes to the clipboard (D015).

**Tests run headless against the real platform.** `make test-jetbrains` runs JUnit tests for the `logic/` ports and `BasePlatformTestCase` tests on a sample the branch's CLI builds. Three things are swapped in tests and were checked by hand instead: the native file watcher (D009), the Terminal tab (D014) and the diff viewer (D019).

## Rules for changing it

- **One writer.** Only `Cli.kt` runs `ws`, off the UI thread, and the only write is `ws act`. A new kind of write starts in `ws act`.
- **Every argv is checked against the real CLI.** `tests/test_jetbrains_files.py` runs each command `Cli.kt` builds.
- **Repo text is never markup.** `Text.kt` builds every piece of HTML and escapes repo text; the same test scans `src/main` for markup sinks.
- **No internal API.** `make verify-jetbrains` must say Compatible on both IDEs with no internal-API usage.

## What was shown

On macOS, IntelliJ IDEA 2026.3 (IU-263.7307.200) and Android Studio 2026.2 (AI-262.10968.63), Python 3.14, on 2026-11-09. The owner drove the IDEs by hand; the coordinator ran the shell side and read git afterwards.

| Check | Result |
|---|---|
| Package and verify | `make jetbrains-zip` built `workstreams-jetbrains-0.1.0.zip` (282 KB). `make verify-jetbrains`: Android Studio "Compatible", IntelliJ IDEA "Compatible. 1 usage of deprecated API" (`FileEditorManager.openFile` in `ReviewOpen.openEvidence`) |
| Install | Installed from disk in both IDEs; the zip was also served from a local plugin repository (`dist/jetbrains/updatePlugins.xml`) |
| Sample project from an installed wheel | `ws` 0.1.0 from a wheel in a clean venv built `alpha` (S-1 claimed and backdated, S-2 on a branch editing `shared.txt` and adding `added.txt`, S-3 todo) and `beta`, then main moved (`3876b8d main moves`). The ws command setting pointed at the venv's `ws` |
| Views | Registry, Review, Health and Budget drew in IntelliJ, and so did the status bar widget |
| A pause landing | `39e44a2 alpha: pause (ws act)` |
| A stale pause refused | With the alpha Pause box open, a shell commit (`86c74e7 touch2`) changed the registry. OK was refused as stale, and HEAD stayed at `86c74e7` |
| Live refresh | After `touch2` paused beta from the shell, the tree showed beta paused without a Refresh click |
| A branch diff after main moved | Review → On a branch → S-2 listed only `shared.txt` and `added.txt`, not main's `main-only.txt`. `shared.txt` opened in the diff viewer as `one` → `one` / `two`, its old side titled with the merge base rather than main's tip |
| A notified finding's unclaim | The health notification's Show Health opened the Health tab, and the stale-claim finding's Unclaim landed as `42e6357 alpha: unclaim S-1 (ws act)` |
| Run in a Terminal tab | Run on alpha opened a Terminal tab running the agent command with the prompt as its argument, in IntelliJ and in Android Studio. With the agent command cleared, Run opened no tab and copied `Use the ws-run skill to run workstream alpha.` |
| Android Studio | The tool window drew on the sample, and `d91ad8a beta: resume (ws act)` landed |
| Alongside another `Workstreams` tool window | Android Studio here also has another plugin that registers a tool window with id `Workstreams`. It was disabled for the checks above; afterwards the owner installed both side by side and reported no conflicts (D030) |
| This repo, read-only | Viewed in IntelliJ with no writes; HEAD (`b8b63d0`), status and refs were the same afterwards |
| Automated | `make test` and `make test-jetbrains` pass |

## Not proven

- **A real agent started by Run.** The sample's agent command printed its argument and opened a shell instead of starting Claude Code.
- **The stale refusal's exact text.** The owner reported "refused"; the message wasn't copied from the screen.
- **PyCharm and other JetBrains IDEs, builds older than 262, and other OSes.** Out of scope.
- **Several active workstreams.** The status bar shows the first active one.
- **A write to a real project**, or a long session. Writes ran on the sample only, by design.

## Left open

Nothing. Closed after the milestone, on 2026-11-09:

- D031 closed D014: Terminal tabs keep the public `createNewSession(runner, TerminalTabState)`, which JB-07 saw start the agent on both IDEs.
- D032 closed D027: local installs stay on the gitignored `dist/jetbrains/`, copied by hand. No make target writes it yet.
- `ReviewOpen.openEvidence` now opens through `OpenFileDescriptor.navigate` instead of the deprecated `FileEditorManager.openFile`. `make test-jetbrains` passes, and `make verify-jetbrains` reports plain Compatible on 262 and 263 with no deprecated usages.

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

## D004 (2026-11-08, JB-02): the headless tests disable the IDE's `com.intellij.modules.ultimate` plugin

Against IntelliJ IDEA 2026.2.4 (the unified distribution), every `BasePlatformTestCase` failed with `Cannot create extension (class=Q.Q.Q.Q.V) [Plugin: com.intellij.modules.ultimate]`. That plugin's only extension is a `postStartupActivity` with no constructor a light test project can supply. `tasks.prepareTestSandbox { disabledPlugins.add("com.intellij.modules.ultimate") }` disables it in the test sandbox only. The plugin uses nothing from it, and `verifyPlugin` still checks against the full IDEs. Rejected: IntelliJ IDEA Community, which is no longer published for 2026.2 (`Could not find idea:ideaIC:2026.2.4`). Also rejected: compiling against the local Android Studio, which plan T1 rules out. **Closed.**

## D005 (2026-11-08, JB-02): the startup activity does nothing in unit-test mode, and tests call `Workstreams.open` themselves

A light test project's base dir is a temp folder that isn't a workstream project. If the startup activity ran there, it would fire the not-a-project notification before each test, and the "one notification" checks couldn't hold. So `OpenWorkstreams` returns early when `isUnitTestMode`, and the tests open the sample folder through the project service. Rejected: opening a second heavy project per test with `PlatformTestUtil.loadAndOpenProject`, which is slower and still races the activity. **Closed.**

## D006 (2026-11-08, JB-02): the Gradle `test` task declares the checkout's `src/workstream` as an input

Otherwise Gradle reuses the last test result after a CLI change. My first `ws verify` recorded `make test-jetbrains 1.2s` because of that. Rejected: `--rerun` in the make target, which reruns the tests even when nothing changed. **Closed.**

## D007 (2026-11-08, JB-02): settings take an argv split the way a run configuration's arguments are

The `ws command` and `Agent command` fields go through `ParametersListUtil.parse`/`join`, and are stored as string lists that default to `["ws"]` and `[]`. Rejected: a JSON array in a text field, which is harder to type and gives nothing more. **Closed.**

## D008 (2026-11-08, JB-02): the platform is IntelliJ IDEA 2026.2.4 (262.11879.100), with Kotlin 2.3.20 and Gradle 9.7.1

2026.2.4 is the latest 262 release in JetBrains' repository. Kotlin 2.3.20 and the 9.7.1 wrapper were already cached. I generated the wrapper with `--no-validate-url`, because services.gradle.org returned 504 at the time. `validateDistributionUrl` is back to `true` in the properties. Escaping uses `HtmlChunk.text`, the platform's escaper, where plan T2 names `XmlStringUtil.escapeString`. Both escape `<`, `>`, `&` and quotes. Rejected: the 2026.2 base release, which is older within the same branch and gives nothing more. **Closed.**

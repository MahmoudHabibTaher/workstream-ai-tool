# Session handoff

**State:** 7/7 done on `main` at `c9df99b`, as of 2026-11-09.

**Just landed:** JB-07 (`c9df99b28f`)

**Open decisions:**
- D014: the Terminal tab is opened with the public `createNewSession(runner, TerminalTabState)`, not the five-argument overload plan T7 names (no task waiting)
- D027: the zip was installed from a copy in `dist/jetbrains/`, also served by a local plugin repository (no task waiting)
- D029: Android Studio was checked with the other `Workstreams` plugin disabled (no task waiting)

**Next:** The queue is finished; `ws close` closes the workstream.

**Gotchas:**
- JB-07: - The tool window id `Workstreams` is generic and clashes with another plugin's (D029). A unique id such as `dev.workstream.jetbrains` would avoid it.
- `ReviewOpen.openEvidence` uses the deprecated `FileEditorManager.openFile` (D026); `OpenFileDescriptor.navigate`, as Documents use, would clear it.
- A `make` target that refreshes `dist/jetbrains/` and its `updatePlugins.xml` would make the local repository repeatable (D027). The version must rise for the IDE to offer an update.
- The sample's `.idea/` is untracked after IntelliJ opened it; harmless for a throwaway sample.

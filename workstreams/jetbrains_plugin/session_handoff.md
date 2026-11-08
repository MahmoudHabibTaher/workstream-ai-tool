# Session handoff

**State:** 3/7 done on `main` at `79881c6`, as of 2026-11-08.

**Just landed:** JB-03 (`79881c6091`)

**Next:** `ws claim --commit JB-04` (phase 2).

**Gotchas:**
- JB-03: - Opening a workstream project now runs `ws snapshot -w <id>` for the first active workstream after each top-level snapshot, so the status bar can show its wave line. OpenTest's expected calls were updated to `root`, `snapshot`, `snapshot -w alpha`. Each burst therefore costs two `ws` calls when a workstream is active.
- The light test project, and so the `Workstreams` service, outlives each test. `Workstreams.forget()` (`@TestOnly`) resets it in `SampleTestCase.setUp` and `tearDown`. OpenTest now shares `SampleTestCase` with RegistryViewTest.
- Temp dirs resolve to `/private/var/...`, which the test VFS doesn't allow by default (`VfsRootAccessNotAllowedError`). `SampleTestCase` calls `VfsRootAccess.allowRootAccess` for its temp dir.
- The tool window has only the Registry tab. Review, Health and Budget come with JB-05 and JB-06. Nodes carry no writes or launches yet, which JB-04 adds.

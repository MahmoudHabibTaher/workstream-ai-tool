# Session handoff

**State:** 9/10 done on `main` at `dc23088`, as of 2026-11-11.

**Just landed:** JX-09 (`dc23088203`)

**Open decisions:**
- D023: Run This Task… is left out of the Run group until JX-08 (waiting: JX-10)
- D033: the chat targets register in plugin.xml, not through optional `<depends>` config files (waiting: JX-10)
- D034: the fakes are stand-ins under their own names, not classes under the plugins' names (waiting: JX-10)

**Next:** `ws claim --commit JX-10` (phase 4).

**Gotchas:**
- JX-09: - On the local 2026.2 IDE, the installed Air plugin has no `AgentPromptPalettePopupService` (its `lib/modules` has no `intellij.air.frontend.prompt.ui.jar`). There, Air isn't offered. It is offered on 2026.3 (bundled Air 263.7307.200), where the classes and both anchor actions (`Air.Prompt.NewSession.Send`, `Air.Prompt.Pin`) exist. Copilot 1.20/1.21 has `CopilotChatService.query(DataContext, Function1)` and the `QueryOptionBuilder` methods used, registered as a project service, with `copilot.chat.show` in the same module.
- Neither target has been tried by hand against the real plugins in a running IDE. Only the signatures were checked, with `javap` against the installed jars.

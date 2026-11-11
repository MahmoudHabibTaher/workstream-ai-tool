// The launch dialog in a headless IDE, on the sample: a failed blocking check disables OK, the
// Terminal's argv is the one `ws launch argv` builds for the chosen preset and the edited prompt,
// a pinned task's prompt and checks are run-task's, and OK launches with the chosen target and
// remembers the choices.
package dev.workstream.jetbrains

import com.google.gson.JsonParser
import com.intellij.openapi.project.Project
import com.intellij.openapi.util.Disposer
import dev.workstream.jetbrains.logic.Loaded
import dev.workstream.jetbrains.logic.WorkstreamNode
import java.io.File
import java.util.concurrent.CopyOnWriteArrayList

class LaunchDialogTest : SampleTestCase() {
    private lateinit var panel: WorkstreamsPanel
    private lateinit var savedLast: WsSettings.LastLaunch
    private lateinit var savedAgent: List<String>
    private val opened = CopyOnWriteArrayList<List<String>>()

    override fun setUp() {
        super.setUp()
        panel = WorkstreamsPanel(project, Disposer.newDisposable(testRootDisposable, "workstreams"))
        savedLast = WsSettings.getInstance().lastLaunch
        savedAgent = WsSettings.getInstance().agentCommand
        WsSettings.getInstance().lastLaunch = WsSettings.LastLaunch(null, null, null, null)
        WsSettings.getInstance().agentCommand = listOf()
        TerminalTarget.opener = TerminalOpener { _: Project, cwd, tab, argv -> opened += listOf(cwd, tab) + argv }
    }

    override fun tearDown() {
        try {
            TerminalTarget.reset()
            LaunchDialog.reset()
            WsSettings.getInstance().lastLaunch = savedLast
            WsSettings.getInstance().agentCommand = savedAgent
        } finally {
            super.tearDown()
        }
    }

    private fun openSample(filled: Boolean): File {
        val root = sampleProject(filled = filled)
        WsSettings.getInstance().wsCommand = branchCli
        open(root)
        assertTrue(waitFor(30_000) { panel.idle && panel.view != null && panel.listModel.size == 1 })
        return root
    }

    private fun alpha(): WorkstreamNode = panel.listModel.items.single { it.row.id == "alpha" }

    private fun dialog(root: File, kind: String = "run"): LaunchDialog {
        val offer = alpha().row.launches.single { it.kind == kind }
        val d = LaunchDialog(project, LaunchSetup("alpha", kind, "Run alpha", offer.prompt, root.path, listOf("A-1", "A-2")))
        Disposer.register(testRootDisposable, d.disposable)
        assertTrue("the dialog loads", waitFor(30_000) { d.idle })
        return d
    }

    private fun settled(d: LaunchDialog) = assertTrue("the dialog reloads", waitFor(30_000) { d.idle })

    /** The argv the CLI itself prints for these arguments. */
    private fun cliArgv(root: File, vararg args: String): List<String> =
        JsonParser.parseString(ws(root, "launch", "argv", "-w", "alpha", "--json", *args)).asJsonObject
            .getAsJsonArray("argv").map { it.asString }

    fun testABlockingCheckDisablesOkAndTheArgvIsTheChosenPresets() {
        val root = openSample(filled = false)
        val d = dialog(root)
        // The sample's template placeholders are integrity errors: validate blocks.
        assertEquals(listOf("validate"), d.blocking())
        assertFalse(d.isOKActionEnabled)
        assertNull(d.accepted())
        // D037: what blocks is listed first and named by the buttons.
        assertEquals("validate", d.shownChecks().first().id)
        assertEquals("Blocked by validate: fix these checks to launch.", d.blockedText)

        val preset = d.agents().first()
        assertTrue(preset.effortLevels.size > 1 && preset.permissionChoices.isNotEmpty())
        val effort = preset.effortLevels[1]
        val permissions = preset.permissionChoices.first()
        d.pick(target = TERMINAL, agent = preset.agent, effort = effort, permissions = permissions)
        settled(d)
        val prompt = alpha().row.launches.single { it.kind == "run" }.prompt
        assertEquals(Loaded.Value(cliArgv(root, "--agent", preset.agent, "--prompt-kind", "run", "--effort", effort, "--permissions", permissions)),
                     d.argv)
        assertEquals(prompt, (d.argv as Loaded.Value).value.last())
        // With the agent chosen, its skills are checked too.
        assertTrue((d.checks as Loaded.Value).value.any { it.id == "skills" })
        assertFalse(d.isOKActionEnabled)

        // An edited prompt is what the argv carries, even one that starts with a dash.
        d.pick(prompt = "-edited text")
        settled(d)
        assertEquals("-edited text", (d.argv as Loaded.Value).value.last())

        // Pinning a task makes it run-task: its prompt comes from the CLI, and its checks are run-task's.
        d.pick(pin = "A-1")
        settled(d)
        val pinned = cliArgv(root, "--agent", preset.agent, "--prompt-kind", "run-task", "--task", "A-1", "--effort", effort,
                             "--permissions", permissions)
        assertEquals(Loaded.Value(pinned), d.argv)
        assertEquals(pinned.last(), d.prompt)
        assertEquals(listOf("validate", "claim", "dirty", "baseline", "skills"), (d.checks as Loaded.Value).value.map { it.id })
        d.pick(pin = "")
        settled(d)
        assertEquals(prompt, d.prompt)

        // Off the Terminal there is no argv to build.
        d.pick(target = CLIPBOARD)
        settled(d)
        assertNull(d.argv)
    }

    fun testOkLaunchesTheChosenTargetAndTheChoicesAreKept() {
        val root = openSample(filled = true)
        val first = dialog(root)
        val preset = first.agents().first()
        val effort = preset.effortLevels.last()
        first.pick(target = TERMINAL, agent = preset.agent, effort = effort)
        settled(first)
        assertEquals(listOf<String>(), first.blocking())
        assertNull(first.blockedText)
        assertTrue(first.isOKActionEnabled)
        val argv = (first.argv as Loaded.Value).value
        assertEquals(cliArgv(root, "--agent", preset.agent, "--prompt-kind", "run", "--effort", effort), argv)
        val choice = first.accepted()!!
        assertEquals(TERMINAL, choice.target)
        assertEquals(WsSettings.LastLaunch(TERMINAL, preset.agent, effort, null), WsSettings.getInstance().lastLaunch)
        assertEquals(TERMINAL, Launcher.launch(project, choice.request, choice.target).target)
        assertEquals(listOf(listOf(root.path, "Workstreams: Run alpha") + argv), opened.toList())

        // The next dialog opens on the kept choices.
        val second = dialog(root)
        assertEquals(TERMINAL, second.target)
        assertEquals(Loaded.Value(argv), second.argv)

        // The Run action opens it and launches what OK took.
        LaunchDialog.show = { d -> assertTrue(waitFor(30_000) { d.idle }); d.isOKActionEnabled }
        val action = com.intellij.openapi.actionSystem.ActionManager.getInstance().getAction("Workstreams.Run")
        val context = com.intellij.openapi.actionSystem.impl.SimpleDataContext.builder()
            .add(com.intellij.openapi.actionSystem.CommonDataKeys.PROJECT, project).add(WS_NODE, alpha()).build()
        action.actionPerformed(com.intellij.testFramework.TestActionEvent.createTestEvent(action, context))
        assertEquals(2, opened.size)
        assertEquals(opened.first(), opened.last())
    }
}

// The launch dialog (D-DIALOG), opened by each Run-group action before anything starts. It shows
// the pre-flight checks `ws launch check` prints (a failed blocking one disables OK), a task pin for
// Run, the target, and for the Terminal the agent preset with its effort and permissions and the
// argv `ws launch argv` builds from them, then the prompt, editable. Every fact in it comes from the
// CLI: the plugin judges no check and builds no flag. Its last choices are kept in WsSettings.
package dev.workstream.jetbrains

import com.google.gson.JsonElement
import com.google.gson.JsonObject
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.application.ModalityState
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.ComboBox
import com.intellij.openapi.ui.DialogWrapper
import com.intellij.openapi.util.Disposer
import com.intellij.ui.ColoredListCellRenderer
import com.intellij.ui.components.JBScrollPane
import com.intellij.ui.components.JBTextArea
import com.intellij.ui.dsl.builder.AlignX
import com.intellij.ui.dsl.builder.Row
import com.intellij.ui.dsl.builder.panel
import com.intellij.util.execution.ParametersListUtil
import dev.workstream.jetbrains.logic.Loaded
import dev.workstream.jetbrains.logic.terminalArgv
import java.util.concurrent.atomic.AtomicInteger
import javax.swing.JComponent
import javax.swing.JList
import javax.swing.Timer
import javax.swing.event.DocumentEvent
import javax.swing.event.DocumentListener

/** One check of `ws launch check`: whether it passed, and whether failing it stops the launch. */
data class LaunchCheck(val id: String, val ok: Boolean, val blocking: Boolean, val message: String)

/** One agent's preset from `ws launch agents`. */
data class AgentPreset(val agent: String, val label: String, val effortLevels: List<String>, val permissionChoices: List<String>)

/** What the dialog opens on: the row's launch, its finished prompt and the tasks Run can pin. */
data class LaunchSetup(val ws: String, val kind: String, val title: String, val prompt: String, val root: String,
                       val tasks: List<String> = listOf())

/** What the person chose: the target and the request it gets. */
data class LaunchChoice(val target: String, val request: LaunchRequest)

/** The launch JSON the dialog reads, parsed here: `ws launch check`, `agents` and `argv` (D013). */
object Launches {
    private fun JsonObject.text(key: String): String? = get(key)?.takeIf { it.isJsonPrimitive }?.asString
    private fun JsonObject.strings(key: String): List<String> =
        get(key)?.takeIf { it.isJsonArray }?.asJsonArray?.mapNotNull { it.takeIf { e -> e.isJsonPrimitive }?.asString } ?: listOf()
    private fun JsonElement.objects(key: String): List<JsonObject> =
        (this as? JsonObject)?.get(key)?.takeIf { it.isJsonArray }?.asJsonArray?.mapNotNull { it as? JsonObject } ?: listOf()

    fun checks(got: Loaded<JsonElement>): Loaded<List<LaunchCheck>> = when (got) {
        is Loaded.Error -> got
        is Loaded.Value -> Loaded.Value(got.value.objects("checks").map { c ->
            LaunchCheck(c.text("id") ?: "?", c.get("ok")?.asBoolean == true, c.get("blocking")?.asBoolean != false, c.text("message") ?: "")
        })
    }

    fun agents(got: Loaded<JsonElement>): Loaded<List<AgentPreset>> = when (got) {
        is Loaded.Error -> got
        is Loaded.Value -> Loaded.Value(got.value.objects("agents").mapNotNull { a ->
            val id = a.text("agent") ?: return@mapNotNull null
            AgentPreset(id, a.text("label") ?: id, a.strings("effortLevels"), a.strings("permissionChoices"))
        })
    }

    fun argv(got: Loaded<JsonElement>): Loaded<List<String>> = when (got) {
        is Loaded.Error -> got
        is Loaded.Value -> (got.value as? JsonObject)?.strings("argv")?.takeIf { it.isNotEmpty() }
            ?.let { Loaded.Value(it) } ?: Loaded.Error("launch argv printed no argv")
    }

    /** Whether a failed blocking check stops the launch. */
    fun blocked(checks: List<LaunchCheck>): Boolean = checks.any { it.blocking && !it.ok }

    /** A check as one line of the dialog: blocks, warning or ok, then its id and message. */
    fun line(c: LaunchCheck): String = "${if (c.ok) "ok" else if (c.blocking) "BLOCKS" else "warning"}  ${c.id}: ${c.message}"
}

/** An agent the Terminal can start: a preset of `ws launch agents`, or the Agent command setting. */
sealed interface AgentChoice {
    data class Preset(val preset: AgentPreset) : AgentChoice
    data class Command(val argv: List<String>) : AgentChoice
}

class LaunchDialog(
    private val project: Project,
    private val setup: LaunchSetup,
    private val cli: Cli = Cli.fromSettings(Workstreams.of(project).run),
    targets: List<Pair<String, String>> = Launcher.choices(),
) : DialogWrapper(project) {
    private val checksArea = JBTextArea(4, 60).apply { isEditable = false; lineWrap = true; wrapStyleWord = true }
    private val argvArea = JBTextArea(2, 60).apply { isEditable = false; lineWrap = true }
    private val promptArea = JBTextArea(setup.prompt, 4, 60).apply { lineWrap = true; wrapStyleWord = true }
    private val pinBox = ComboBox((listOf(NO_PIN) + setup.tasks).toTypedArray()).apply {
        renderer = rendered<String> { if (it == NO_PIN) "None: the queue's wave decides" else it }
    }
    private val targetBox = ComboBox(targets.toTypedArray()).apply { renderer = rendered<Pair<String, String>> { it.second } }
    private val agentBox = ComboBox<AgentChoice>().apply {
        renderer = rendered<AgentChoice> { if (it is AgentChoice.Preset) it.preset.label else "Agent command setting" }
    }
    private val effortBox = ComboBox<String>().apply { renderer = rendered<String> { it.ifEmpty { "The agent's default" } } }
    private val permissionsBox = ComboBox<String>().apply { renderer = rendered<String> { it.ifEmpty { "The agent's default" } } }
    private val terminalRows = mutableListOf<Row>()
    private var pinRow: Row? = null

    private val generation = AtomicInteger()
    private var quiet = false
    private val typed = Timer(300) { refresh(resetPrompt = false) }.apply { isRepeats = false }

    /** The last results, as shown. */
    @Volatile var checks: Loaded<List<LaunchCheck>>? = null
        private set
    @Volatile var argv: Loaded<List<String>>? = null
        private set
    @Volatile private var presets: List<AgentPreset> = listOf()

    /** True once the agents and the current choices' checks and argv are shown. */
    @Volatile var idle = false
        private set

    init {
        title = "Launch: ${setup.title}"
        isOKActionEnabled = false
        checksArea.text = "Checking…"
        init()
        pinRow?.visible(setup.kind == RUN && setup.tasks.isNotEmpty())
        val last = WsSettings.getInstance().lastLaunch
        targets.indexOfFirst { it.first == last.target }.takeIf { it >= 0 }?.let { targetBox.selectedIndex = it }
        showTerminalRows()
        targetBox.addActionListener { if (!quiet) { showTerminalRows(); refresh(resetPrompt = false) } }
        pinBox.addActionListener { if (!quiet) refresh(resetPrompt = true) }
        agentBox.addActionListener { if (!quiet) { fillPresetBoxes(null, null); refresh(resetPrompt = false) } }
        effortBox.addActionListener { if (!quiet) refresh(resetPrompt = false) }
        permissionsBox.addActionListener { if (!quiet) refresh(resetPrompt = false) }
        promptArea.document.addDocumentListener(object : DocumentListener {
            override fun insertUpdate(e: DocumentEvent) = edited()
            override fun removeUpdate(e: DocumentEvent) = edited()
            override fun changedUpdate(e: DocumentEvent) = edited()
        })
        Disposer.register(disposable) { typed.stop() }
        loadAgents(last)
    }

    override fun createCenterPanel(): JComponent = panel {
        row("Checks:") { cell(JBScrollPane(checksArea)).align(AlignX.FILL) }
        pinRow = row("Pin task:") { cell(pinBox) }
        row("Target:") { cell(targetBox) }
        terminalRows += row("Agent:") { cell(agentBox) }
        terminalRows += row("Effort:") { cell(effortBox) }
        terminalRows += row("Permissions:") { cell(permissionsBox) }
        terminalRows += row("Command:") { cell(JBScrollPane(argvArea)).align(AlignX.FILL) }
        row("Prompt:") { cell(JBScrollPane(promptArea)).align(AlignX.FILL) }
    }

    override fun getPreferredFocusedComponent(): JComponent = promptArea

    private fun edited() {
        if (quiet) return
        idle = false
        isOKActionEnabled = false
        typed.restart()
    }

    private fun <T> rendered(show: (T) -> String) = object : ColoredListCellRenderer<T>() {
        override fun customizeCellRenderer(list: JList<out T>, value: T?, index: Int, selected: Boolean, hasFocus: Boolean) {
            append(if (value == null) "" else show(value))
        }
    }

    val target: String get() = (targetBox.selectedItem as? Pair<*, *>)?.first as? String ?: CLIPBOARD
    val pinned: String? get() = (pinBox.selectedItem as? String)?.takeIf { it != NO_PIN && setup.kind == RUN }
    private val kind: String get() = if (pinned != null) RUN_TASK else setup.kind
    private val agent: AgentChoice? get() = agentBox.selectedItem as? AgentChoice
    private val effort: String? get() = (effortBox.selectedItem as? String)?.ifEmpty { null }
    private val permissions: String? get() = (permissionsBox.selectedItem as? String)?.ifEmpty { null }
    val prompt: String get() = promptArea.text

    /** The ids of the failed blocking checks: what keeps OK disabled. */
    fun blocking(): List<String> = (checks as? Loaded.Value)?.value?.filter { it.blocking && !it.ok }?.map { it.id } ?: listOf()

    private fun showTerminalRows() {
        terminalRows.forEach { it.visible(target == TERMINAL) }
    }

    /** Sets the agent's effort and permissions pickers to its own choices, keeping `effort` and `permissions` if it has them. */
    private fun fillPresetBoxes(effort: String?, permissions: String?) {
        val preset = (agent as? AgentChoice.Preset)?.preset
        quiet = true
        try {
            effortBox.removeAllItems()
            permissionsBox.removeAllItems()
            (listOf("") + (preset?.effortLevels ?: listOf())).forEach(effortBox::addItem)
            (listOf("") + (preset?.permissionChoices ?: listOf())).forEach(permissionsBox::addItem)
            effortBox.selectedItem = effort?.takeIf { preset?.effortLevels?.contains(it) == true } ?: ""
            permissionsBox.selectedItem = permissions?.takeIf { preset?.permissionChoices?.contains(it) == true } ?: ""
            effortBox.isEnabled = preset != null
            permissionsBox.isEnabled = preset != null
        } finally {
            quiet = false
        }
    }

    private fun onEdt(run: () -> Unit) = ApplicationManager.getApplication().invokeLater({ if (!isDisposed) run() }, ModalityState.any())

    private fun loadAgents(last: WsSettings.LastLaunch) {
        val command = WsSettings.getInstance().agentCommand
        ApplicationManager.getApplication().executeOnPooledThread {
            val got = Launches.agents(cli.launchAgents(setup.root))
            onEdt {
                presets = (got as? Loaded.Value)?.value ?: listOf()
                val choices = presets.map { AgentChoice.Preset(it) } + listOfNotNull(command.takeIf { terminalArgv(it, "") != null }?.let { AgentChoice.Command(it) })
                quiet = true
                try {
                    choices.forEach(agentBox::addItem)
                    val keep = choices.firstOrNull { it is AgentChoice.Preset && it.preset.agent == last.agent }
                        ?: choices.firstOrNull { it is AgentChoice.Command && last.agent == COMMAND }
                    if (keep != null) agentBox.selectedItem = keep
                } finally {
                    quiet = false
                }
                fillPresetBoxes(last.effort, last.permissions)
                if (got is Loaded.Error) argvArea.text = got.error
                refresh(resetPrompt = pinned != null)
            }
        }
    }

    /**
     * Reads the checks and argv for the current choices off the EDT, then shows them if nothing
     * changed meanwhile. `resetPrompt` replaces the prompt with the launch's own: a pinned task's
     * comes from `ws launch argv`, the plugin holding no prompt text.
     */
    fun refresh(resetPrompt: Boolean) {
        val at = generation.incrementAndGet()
        idle = false
        isOKActionEnabled = false
        typed.stop()
        if (resetPrompt && pinned == null) setPrompt(setup.prompt)
        val kind = kind
        val task = pinned
        val target = target
        val agent = agent
        val effort = effort
        val permissions = permissions
        val asked = if (resetPrompt && task != null) null else prompt
        ApplicationManager.getApplication().executeOnPooledThread {
            val preset = (agent as? AgentChoice.Preset)?.preset?.takeIf { target == TERMINAL }
            val checked = Launches.checks(cli.launchCheck(setup.root, setup.ws, kind, task, preset?.agent))
            // A pinned task's own prompt: the last argument of the argv the CLI builds for it.
            val promptAgent = preset?.agent ?: presets.firstOrNull()?.agent
            val shown: Loaded<String> = when {
                asked != null -> Loaded.Value(asked)
                promptAgent == null -> Loaded.Error("no agent preset gives this task's prompt")
                else -> when (val got = Launches.argv(cli.launchArgv(setup.root, setup.ws, promptAgent, kind, task))) {
                    is Loaded.Error -> got
                    is Loaded.Value -> Loaded.Value(got.value.last())
                }
            }
            val built: Loaded<List<String>>? = when {
                target != TERMINAL -> null
                shown is Loaded.Error -> shown
                agent is AgentChoice.Command -> Loaded.Value(terminalArgv(agent.argv, (shown as Loaded.Value).value)!!)
                preset == null -> Loaded.Error("no agent is set: pick a preset, or set the Agent command")
                else -> Launches.argv(cli.launchArgv(setup.root, setup.ws, preset.agent, kind, task, effort, permissions, (shown as Loaded.Value).value))
            }
            onEdt {
                if (generation.get() != at) return@onEdt
                checks = checked
                argv = built
                if (asked == null && shown is Loaded.Value) setPrompt(shown.value)
                checksArea.text = when (checked) {
                    is Loaded.Error -> checked.error
                    is Loaded.Value -> checked.value.joinToString("\n", transform = Launches::line)
                }
                argvArea.text = when (built) {
                    null -> ""
                    is Loaded.Error -> built.error
                    is Loaded.Value -> ParametersListUtil.join(built.value)
                }
                isOKActionEnabled = checked is Loaded.Value && !Launches.blocked(checked.value) && built !is Loaded.Error &&
                    shown is Loaded.Value && prompt.isNotBlank()
                idle = true
            }
        }
    }

    /** The presets `ws launch agents` listed. */
    fun agents(): List<AgentPreset> = presets

    /**
     * Sets the pickers as a person would, in the dialog's order; each change reloads. `agent` is a
     * preset's id or [COMMAND]; "" picks no pin, effort or permissions.
     */
    fun pick(target: String? = null, pin: String? = null, agent: String? = null, effort: String? = null,
             permissions: String? = null, prompt: String? = null) {
        if (target != null) targetBox.selectedIndex = (0 until targetBox.itemCount).first { (targetBox.getItemAt(it) as Pair<*, *>).first == target }
        if (pin != null) pinBox.selectedItem = pin
        if (agent != null) agentBox.selectedIndex = (0 until agentBox.itemCount).first {
            when (val a = agentBox.getItemAt(it)) {
                is AgentChoice.Preset -> a.preset.agent == agent
                is AgentChoice.Command -> agent == COMMAND
            }
        }
        if (effort != null) effortBox.selectedItem = effort
        if (permissions != null) permissionsBox.selectedItem = permissions
        if (prompt != null) promptArea.text = prompt
    }

    private fun setPrompt(text: String) {
        quiet = true
        try {
            promptArea.text = text
        } finally {
            quiet = false
        }
    }

    /** The choice OK took, remembered for the next dialog. Null while OK is disabled. */
    fun accepted(): LaunchChoice? {
        if (!isOKActionEnabled) return null
        val agentId = when (val a = agent) {
            is AgentChoice.Preset -> a.preset.agent
            is AgentChoice.Command -> COMMAND
            null -> null
        }
        WsSettings.getInstance().lastLaunch = WsSettings.LastLaunch(target, agentId, effort, permissions)
        val title = pinned?.let { "Run $it of ${setup.ws}" } ?: setup.title
        return LaunchChoice(target, LaunchRequest(title, prompt, setup.root, (argv as? Loaded.Value)?.value))
    }

    companion object {
        const val RUN = "run"
        const val RUN_TASK = "run-task"
        private const val NO_PIN = ""

        /** The Agent command setting's name in the remembered choices; no preset is called this. */
        const val COMMAND = ":command"

        /** Shows the dialog and says whether OK closed it; a test swaps it to drive the dialog. */
        @Volatile
        var show: (LaunchDialog) -> Boolean = { it.showAndGet() }

        @org.jetbrains.annotations.TestOnly
        fun reset() {
            show = { it.showAndGet() }
        }
    }
}

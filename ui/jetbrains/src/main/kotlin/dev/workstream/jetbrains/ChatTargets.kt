// The two chat launch targets (D-CHAT): a new agent-mode Copilot Chat session holding the prompt,
// and Air's new-session prompt popup holding the text, where the person picks the agent and sends
// it. Neither plugin is a dependency, so their classes are reached by reflection, through the
// classloader of an action each one registers (plan T5): both keep their classes in content
// modules whose loaders ours can't see. Air's popup is reached only through non-public classes, an
// owner-approved exception to 0018's "no internal API" rule (D001), so every reflective failure on
// either target copies the prompt to the clipboard with a line saying why.
//
// This is the only file that names an agent or its plugin's classes (plan T1); the tests and the
// plugin.xml refer to them through the constants here.
package dev.workstream.jetbrains

import com.intellij.ide.plugins.PluginManagerCore
import com.intellij.openapi.actionSystem.ActionManager
import com.intellij.openapi.actionSystem.DataContext
import com.intellij.openapi.actionSystem.impl.SimpleDataContext
import com.intellij.openapi.diagnostic.ControlFlowException
import com.intellij.openapi.extensions.PluginId
import com.intellij.openapi.ide.CopyPasteManager
import com.intellij.openapi.project.Project
import java.awt.datatransfer.StringSelection
import java.io.File
import java.lang.reflect.InvocationTargetException

/** Loads a class of another plugin by name, or null when it can't be found; a test swaps it for fakes. */
fun interface PluginClasses {
    fun load(name: String): Class<*>?
}

/**
 * The classes of plugin `pluginId`, loaded through the classloaders of the actions `anchors` that
 * it registers. None load while the plugin is missing or disabled.
 */
class ActionClasses(private val pluginId: String, private val anchors: List<String>) : PluginClasses {
    override fun load(name: String): Class<*>? {
        val id = PluginId.getId(pluginId)
        if (!PluginManagerCore.isPluginInstalled(id) || PluginManagerCore.isDisabled(id)) return null
        val actions = ActionManager.getInstance()
        return anchors.mapNotNull { actions.getAction(it)?.javaClass?.classLoader }
            .firstNotNullOfOrNull { loader -> runCatching { loader.loadClass(name) }.getOrNull() }
    }
}

/** Why a chat target couldn't take the prompt, in words the person reads. */
class ChatFailure(message: String) : Exception(message)

/**
 * The prompt a chat gets. A chat runs where the IDE's project folder is, so when the repository
 * root `root` isn't that folder (`base`), the prompt says where the root is.
 */
fun chatPrompt(prompt: String, root: String, base: String?): String {
    val same = base != null && runCatching { File(base).canonicalPath == File(root).canonicalPath }.getOrDefault(base == root)
    return if (same) prompt else "The repository root is $root.\n\n$prompt"
}

/**
 * A target that hands the prompt to another plugin's chat. It is offered only while `anchor`, its
 * plugin's entry class, loads. It always takes a launch: a failure copies the prompt and says why.
 */
abstract class ChatTarget : LaunchTarget {
    /** The class whose loading means the plugin is there. */
    protected abstract val anchor: String

    protected abstract fun classes(): PluginClasses

    /** Hands `prompt` to the plugin, or throws; on the EDT. */
    protected abstract fun send(project: Project, request: LaunchRequest, prompt: String, classes: PluginClasses)

    override val available: Boolean get() = runCatching { classes().load(anchor) != null }.getOrDefault(false)

    override fun start(project: Project, request: LaunchRequest): Started {
        val prompt = chatPrompt(request.prompt, request.root, project.basePath)
        val why = try {
            send(project, request, prompt, classes())
            null
        } catch (e: Throwable) {
            val cause = if (e is InvocationTargetException) e.targetException ?: e else e
            if (cause is ControlFlowException || (cause !is Exception && cause !is LinkageError)) throw cause
            reason(cause)
        }
        if (why == null) return Started(id, "Sent the ${request.title} prompt to $label.")
        CopyPasteManager.getInstance().setContents(StringSelection(prompt))
        return Started(CLIPBOARD, "Copied the ${request.title} prompt to the clipboard, because $why Prompt: $prompt")
    }

    private fun reason(cause: Throwable): String {
        if (cause is ChatFailure) return cause.message.orEmpty()
        val detail = cause.message?.let { "${cause.javaClass.simpleName}: $it" } ?: cause.javaClass.simpleName
        return "$label didn't take it ($detail)."
    }

    protected fun PluginClasses.need(name: String): Class<*> = load(name) ?: throw ChatFailure("$label isn't installed or enabled ($name not found).")

    protected fun <T> unwrapped(block: () -> T): T = try {
        block()
    } catch (e: InvocationTargetException) {
        throw e.targetException ?: e
    }
}

/** Copilot Chat: a new agent-mode session with the prompt sent, through its public chat service. */
class ChatSessionTarget : ChatTarget() {
    override val id: String = CHAT_SESSION
    override val label: String = "Copilot Chat"
    override val anchor: String = SERVICE

    override fun classes(): PluginClasses = classes

    override fun send(project: Project, request: LaunchRequest, prompt: String, classes: PluginClasses) {
        val serviceType = classes.need(SERVICE)
        val builderType = classes.need(BUILDER)
        val service = project.getService(serviceType) ?: throw ChatFailure("$label has no chat service in this project.")
        val steps = listOf(builderType.getMethod("withNewSession"), builderType.getMethod("withAgentMode"))
        val input = builderType.getMethod("withInput", String::class.java)
        val query = serviceType.getMethod("query", DataContext::class.java, Function1::class.java)
        val options: (Any?) -> Unit = { builder ->
            steps.forEach { it.invoke(builder) }
            input.invoke(builder, prompt)
        }
        unwrapped { query.invoke(service, SimpleDataContext.getProjectContext(project), options) }
    }

    companion object {
        const val PLUGIN = "com.github.copilot"
        const val SERVICE = "com.github.copilot.api.CopilotChatService"
        const val BUILDER = "com.github.copilot.api.QueryOptionBuilder"
        private val ACTIONS = ActionClasses(PLUGIN, listOf("copilot.chat.show"))

        @Volatile
        var classes: PluginClasses = ACTIONS

        @org.jetbrains.annotations.TestOnly
        fun reset() {
            classes = ACTIONS
        }
    }
}

/**
 * Air: its new-session prompt popup opens holding the text, replacing any draft. Air's public
 * submission service isn't used: it adds to the project's open session when there is one.
 */
class PromptPopupTarget : ChatTarget() {
    override val id: String = PROMPT_POPUP
    override val label: String = "Air"
    override val anchor: String = SERVICE

    override fun classes(): PluginClasses = classes

    override fun send(project: Project, request: LaunchRequest, prompt: String, classes: PluginClasses) {
        val serviceType = classes.need(SERVICE)
        val textType = classes.need(TEXT)
        val modeType = classes.need(MODE)
        val requestType = classes.need(REQUEST)
        val invocationType = classes.need(INVOCATION)
        val candidateType = classes.need(CANDIDATE)
        val addType = classes.need(ADD_CONTEXT)
        val convert = classes.need(CONVERSIONS).getMethod("toInvocationData", requestType, Project::class.java)
        val show = serviceType.getMethod("showAddContextOnEdt", invocationType, addType)
        val service = project.getService(serviceType) ?: throw ChatFailure("$label has no prompt popup in this project.")
        val replace = modeType.enumConstants?.firstOrNull { (it as Enum<*>).name == "REPLACE" }
            ?: throw ChatFailure("$label's prompt has no REPLACE mode.")
        unwrapped {
            val text = textType.getConstructor(String::class.java, modeType).newInstance(prompt, replace)
            val submission = requestType.getConstructor(
                textType, List::class.java, String::class.java, String::class.java, String::class.java, String::class.java,
                Long::class.javaPrimitiveType,
            ).newInstance(text, emptyList<Any>(), request.root, ACTION_ID, request.title, PLACE, System.currentTimeMillis())
            val invocation = convert.invoke(null, submission, project)
            val add = addType.getConstructor(List::class.java, candidateType, textType).newInstance(emptyList<Any>(), null, text)
            show.invoke(service, invocation, add)
        }
    }

    companion object {
        const val PLUGIN = "com.intellij.air"
        private const val SHARED = "com.intellij.air.shared.prompt"
        private const val API = "com.intellij.air.frontend.prompt.api"
        private const val UI = "com.intellij.air.frontend.prompt.ui"
        const val SERVICE = "$UI.AgentPromptPalettePopupService"
        const val TEXT = "$SHARED.AgentPromptSubmittedText"
        const val MODE = "$SHARED.AgentPromptTextMode"
        const val REQUEST = "$SHARED.AgentPromptSubmissionRequest"
        const val INVOCATION = "$API.AgentPromptInvocationData"
        const val CANDIDATE = "$API.AgentPromptAddContextTargetCandidate"
        const val ADD_CONTEXT = "$UI.AgentPromptAddContextRequest"
        const val CONVERSIONS = "$UI.AgentPromptContextSubmissionRemoteTopicListenerKt"
        const val ACTION_ID = "Workstreams.Launch"
        const val PLACE = "Workstreams"
        private val ACTIONS = ActionClasses(PLUGIN, listOf("Air.Prompt.NewSession.Send", "Air.Prompt.Pin"))

        @Volatile
        var classes: PluginClasses = ACTIONS

        @org.jetbrains.annotations.TestOnly
        fun reset() {
            classes = ACTIONS
        }
    }
}

const val CHAT_SESSION = "copilot-chat"
const val PROMPT_POPUP = "air"

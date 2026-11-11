// The chat targets with fake plugin classes: each fake stands in for the class ChatTargets.kt
// names, so each target is seen receiving the prompt, and a class that doesn't load sends the
// prompt to the clipboard with the reason. The fakes have their own names, so no agent is named
// outside ChatTargets.kt (plan T1); the services are registered in the test project.
package dev.workstream.jetbrains

import com.intellij.openapi.actionSystem.DataContext
import com.intellij.openapi.ide.CopyPasteManager
import com.intellij.openapi.project.Project
import com.intellij.testFramework.fixtures.BasePlatformTestCase
import com.intellij.testFramework.registerOrReplaceServiceInstance
import java.awt.datatransfer.DataFlavor

class FakeOptions {
    val steps = mutableListOf<String>()
    fun withNewSession() { steps += "new session" }
    fun withAgentMode() { steps += "agent mode" }
    fun withInput(text: String) { steps += "input:$text" }
}

/** The chat service: its query hands a fresh builder to the options, as the real one does. */
open class FakeChatService {
    val queries = mutableListOf<List<String>>()
    open fun query(context: DataContext, options: (FakeOptions) -> Unit) {
        queries += FakeOptions().also(options).steps
    }
}

class FailingChatService : FakeChatService() {
    override fun query(context: DataContext, options: (FakeOptions) -> Unit) = throw IllegalStateException("not signed in")
}

enum class FakeTextMode { REPLACE, APPEND }
class FakeText(val text: String, val mode: FakeTextMode)
class FakeSubmission(val text: FakeText, val items: List<*>, val path: String?, val actionId: String?, val actionText: String?,
                     val place: String?, val at: Long)
class FakeInvocation(val project: Project, val submission: FakeSubmission)
class FakeCandidate
class FakeAddContext(val items: List<*>, val target: FakeCandidate?, val text: FakeText)

object FakeConversions {
    @JvmStatic
    fun toInvocationData(submission: FakeSubmission, project: Project): FakeInvocation = FakeInvocation(project, submission)
}

class FakePopupService {
    val shown = mutableListOf<Pair<FakeInvocation, FakeAddContext>>()
    fun showAddContextOnEdt(invocation: FakeInvocation, add: FakeAddContext) {
        shown += invocation to add
    }
}

class ChatTargetsTest : BasePlatformTestCase() {
    private val request get() = LaunchRequest("Run alpha", "-run alpha", project.basePath!!)

    override fun tearDown() {
        try {
            ChatSessionTarget.reset()
            PromptPopupTarget.reset()
        } finally {
            super.tearDown()
        }
    }

    private fun clipboard(): String = CopyPasteManager.getInstance().getContents<String>(DataFlavor.stringFlavor).orEmpty()

    private fun chat(service: FakeChatService, builder: Boolean = true): ChatSessionTarget {
        project.registerOrReplaceServiceInstance(FakeChatService::class.java, service, testRootDisposable)
        val fakes = mapOf(ChatSessionTarget.SERVICE to FakeChatService::class.java, ChatSessionTarget.BUILDER to FakeOptions::class.java)
            .filterKeys { builder || it != ChatSessionTarget.BUILDER }
        ChatSessionTarget.classes = PluginClasses { fakes[it] }
        return Launcher.TARGETS.findExtension(ChatSessionTarget::class.java)!!
    }

    private fun popup(service: FakePopupService): PromptPopupTarget {
        project.registerOrReplaceServiceInstance(FakePopupService::class.java, service, testRootDisposable)
        val fakes = mapOf(
            PromptPopupTarget.SERVICE to FakePopupService::class.java, PromptPopupTarget.TEXT to FakeText::class.java,
            PromptPopupTarget.MODE to FakeTextMode::class.java, PromptPopupTarget.REQUEST to FakeSubmission::class.java,
            PromptPopupTarget.INVOCATION to FakeInvocation::class.java, PromptPopupTarget.CANDIDATE to FakeCandidate::class.java,
            PromptPopupTarget.ADD_CONTEXT to FakeAddContext::class.java, PromptPopupTarget.CONVERSIONS to FakeConversions::class.java,
        )
        PromptPopupTarget.classes = PluginClasses { fakes[it] }
        return Launcher.TARGETS.findExtension(PromptPopupTarget::class.java)!!
    }

    fun testWithoutTheirPluginsTheChatTargetsAreNotOffered() {
        val ids = Launcher.choices().map { it.first }
        assertFalse(ids.contains(CHAT_SESSION))
        assertFalse(ids.contains(PROMPT_POPUP))
        assertEquals(CLIPBOARD, ids.last())
    }

    fun testANamedChatTargetWithoutItsPluginCopiesThePromptAndSaysWhy() {
        val started = Launcher.launch(project, request, CHAT_SESSION)
        val label = Launcher.TARGETS.findExtension(ChatSessionTarget::class.java)!!.label
        assertEquals(CLIPBOARD, started.target)
        assertEquals("Copied the Run alpha prompt to the clipboard, because $label isn't installed or enabled " +
            "(${ChatSessionTarget.SERVICE} not found). Prompt: -run alpha", started.said)
        assertEquals("-run alpha", clipboard())
    }

    fun testTheChatSessionTargetStartsANewAgentModeSessionWithThePrompt() {
        val service = FakeChatService()
        val target = chat(service)
        assertTrue(Launcher.choices().map { it.first }.contains(CHAT_SESSION))
        val started = Launcher.launch(project, request, CHAT_SESSION)
        assertEquals(CHAT_SESSION, started.target)
        assertEquals("Sent the Run alpha prompt to ${target.label}.", started.said)
        assertEquals(listOf(listOf("new session", "agent mode", "input:-run alpha")), service.queries)
    }

    fun testAMissingClassSendsTheChatPromptToTheClipboard() {
        val service = FakeChatService()
        val target = chat(service, builder = false)
        val started = Launcher.launch(project, request, CHAT_SESSION)
        assertEquals(CLIPBOARD, started.target)
        assertEquals("Copied the Run alpha prompt to the clipboard, because ${target.label} isn't installed or enabled " +
            "(${ChatSessionTarget.BUILDER} not found). Prompt: -run alpha", started.said)
        assertEquals("-run alpha", clipboard())
        assertEquals(emptyList<List<String>>(), service.queries)
    }

    fun testAChatThatThrowsSendsThePromptToTheClipboardWithItsMessage() {
        val target = chat(FailingChatService())
        val started = Launcher.launch(project, request, CHAT_SESSION)
        assertEquals(CLIPBOARD, started.target)
        assertEquals("Copied the Run alpha prompt to the clipboard, because ${target.label} didn't take it " +
            "(IllegalStateException: not signed in). Prompt: -run alpha", started.said)
    }

    fun testThePromptPopupTargetOpensTheNewSessionPromptHoldingTheText() {
        val service = FakePopupService()
        val target = popup(service)
        val started = Launcher.launch(project, request, PROMPT_POPUP)
        assertEquals(PROMPT_POPUP, started.target)
        assertEquals("Sent the Run alpha prompt to ${target.label}.", started.said)
        val (invocation, add) = service.shown.single()
        assertEquals("-run alpha", add.text.text)
        assertEquals(FakeTextMode.REPLACE, add.text.mode)
        assertNull(add.target)
        assertSame(project, invocation.project)
        assertSame(add.text, invocation.submission.text)
        assertEquals(request.root, invocation.submission.path)
        assertEquals("Run alpha", invocation.submission.actionText)
    }

    fun testAMissingPopupClassSendsThePromptToTheClipboard() {
        val service = FakePopupService()
        val target = popup(service)
        val fakes = PromptPopupTarget.classes
        PromptPopupTarget.classes = PluginClasses { if (it == PromptPopupTarget.CONVERSIONS) null else fakes.load(it) }
        val started = Launcher.launch(project, request, PROMPT_POPUP)
        assertEquals(CLIPBOARD, started.target)
        assertEquals("Copied the Run alpha prompt to the clipboard, because ${target.label} isn't installed or enabled " +
            "(${PromptPopupTarget.CONVERSIONS} not found). Prompt: -run alpha", started.said)
        assertEquals(emptyList<Any>(), service.shown)
    }

    fun testAChatPromptNamesTheRepositoryRootWhenTheProjectFolderIsntIt() {
        val service = FakeChatService()
        chat(service)
        Launcher.launch(project, request.copy(root = "/elsewhere/repo"), CHAT_SESSION)
        assertEquals("input:The repository root is /elsewhere/repo.\n\n-run alpha", service.queries.single().last())
        assertEquals("-run alpha", chatPrompt("-run alpha", "/r", "/r"))
        assertEquals("The repository root is /r.\n\n-run alpha", chatPrompt("-run alpha", "/r", null))
    }

    fun testTheRealClassesLoadNothingWithoutThePlugin() {
        assertNull(ActionClasses(ChatSessionTarget.PLUGIN, listOf("Workstreams.Run")).load(ChatSessionTarget.SERVICE))
    }
}

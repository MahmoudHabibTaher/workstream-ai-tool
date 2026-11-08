// The plugin's two settings, for the whole IDE: the argv that runs `ws`, and the agent argv the
// launcher starts. Both are argv lists, never a shell line.
package dev.workstream.jetbrains

import com.intellij.openapi.components.PersistentStateComponent
import com.intellij.openapi.components.Service
import com.intellij.openapi.components.State
import com.intellij.openapi.components.Storage
import com.intellij.openapi.components.service
import com.intellij.openapi.options.BoundConfigurable
import com.intellij.openapi.ui.DialogPanel
import com.intellij.ui.dsl.builder.AlignX
import com.intellij.ui.dsl.builder.bindText
import com.intellij.ui.dsl.builder.panel
import com.intellij.util.execution.ParametersListUtil

@Service(Service.Level.APP)
@State(name = "WorkstreamsSettings", storages = [Storage("workstreams.xml")])
class WsSettings : PersistentStateComponent<WsSettings.Values> {
    class Values {
        var wsCommand: MutableList<String> = mutableListOf("ws")
        var agentCommand: MutableList<String> = mutableListOf()
    }

    private var values = Values()

    override fun getState(): Values = values

    override fun loadState(state: Values) {
        values = state
    }

    var wsCommand: List<String>
        get() = values.wsCommand.ifEmpty { listOf("ws") }
        set(argv) {
            values.wsCommand = argv.toMutableList()
        }

    var agentCommand: List<String>
        get() = values.agentCommand
        set(argv) {
            values.agentCommand = argv.toMutableList()
        }

    companion object {
        fun getInstance(): WsSettings = service()
    }
}

/** Settings | Tools | Workstreams. Each field is an argv, split the way a run configuration's is. */
class WsConfigurable : BoundConfigurable("Workstreams") {
    override fun createPanel(): DialogPanel {
        val settings = WsSettings.getInstance()
        return panel {
            row("ws command:") {
                textField()
                    .align(AlignX.FILL)
                    .bindText({ ParametersListUtil.join(settings.wsCommand) }, { settings.wsCommand = ParametersListUtil.parse(it) })
            }
            row("Agent command:") {
                textField()
                    .align(AlignX.FILL)
                    .bindText({ ParametersListUtil.join(settings.agentCommand) }, { settings.agentCommand = ParametersListUtil.parse(it) })
            }
        }
    }
}

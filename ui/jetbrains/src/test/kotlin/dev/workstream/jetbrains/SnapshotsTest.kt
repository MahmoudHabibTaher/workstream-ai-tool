// Reading `ws snapshot -w`'s paths: the tasks file comes from paths.tasks, never from a guess at watch.
package dev.workstream.jetbrains

import com.google.gson.JsonObject
import com.google.gson.JsonParser
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class SnapshotsTest {
    private fun snap(json: String): JsonObject = JsonParser.parseString(json).asJsonObject

    // watch lists the handoff where the old guess looked, so only paths.tasks can give the right file.
    private val withTasks = snap("""{
        "paths": {"plan": "/p/ws/alpha/PLAN.md", "handoff": "/p/ws/alpha/session_handoff.md",
                  "tasks": "/p/ws/alpha/tasks_list.json", "evidence": {}},
        "watch": ["/p/ws/registry.json", "/p/ws/alpha/session_handoff.md", "/p/ws/alpha/PLAN.md"]
    }""")

    @Test
    fun tasksFileReadsPathsTasks() {
        assertEquals("/p/ws/alpha/tasks_list.json", Snapshots.tasksFile(withTasks))
        assertEquals("/p/ws/alpha/tasks_list.json", Snapshots.view(withTasks).tasksFile)
    }

    @Test
    fun theDocsHoldNoTasksEntry() {
        assertEquals(mapOf("plan" to "/p/ws/alpha/PLAN.md", "handoff" to "/p/ws/alpha/session_handoff.md"),
                     Snapshots.view(withTasks).docs)
    }

    @Test
    fun tasksFileIsNullWithoutPathsTasks() {
        val without = snap("""{
            "paths": {"plan": "/p/ws/alpha/PLAN.md", "evidence": {}},
            "watch": ["/p/ws/registry.json", "/p/ws/alpha/tasks_list.json", "/p/ws/alpha/PLAN.md"]
        }""")
        assertNull(Snapshots.tasksFile(without))
        assertNull(Snapshots.view(without).tasksFile)
        assertNull(Snapshots.tasksFile(snap("{}")))
    }
}

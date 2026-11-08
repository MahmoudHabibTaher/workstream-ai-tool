// Reads the snapshot JSON the CLI printed into logic/'s shapes. It reads leniently: a field the
// CLI left out is empty, never an error, since the snapshot's schema is the CLI's to change.
package dev.workstream.jetbrains

import com.google.gson.JsonArray
import com.google.gson.JsonElement
import com.google.gson.JsonObject
import dev.workstream.jetbrains.logic.Finding
import dev.workstream.jetbrains.logic.Progress
import dev.workstream.jetbrains.logic.Row
import dev.workstream.jetbrains.logic.Task
import dev.workstream.jetbrains.logic.VerifyCommand
import dev.workstream.jetbrains.logic.Watch
import dev.workstream.jetbrains.logic.Wave
import dev.workstream.jetbrains.logic.WsView

object Snapshots {
    private fun JsonObject.obj(name: String): JsonObject? = get(name)?.takeIf { it.isJsonObject }?.asJsonObject
    private fun JsonObject.arr(name: String): JsonArray = get(name)?.takeIf { it.isJsonArray }?.asJsonArray ?: JsonArray()
    private fun JsonObject.str(name: String): String? = get(name)?.takeIf { it.isJsonPrimitive }?.asString
    private fun JsonObject.int(name: String): Int? = get(name)?.takeIf { it.isJsonPrimitive && it.asJsonPrimitive.isNumber }?.asInt
    private fun JsonObject.bool(name: String): Boolean = get(name)?.takeIf { it.isJsonPrimitive && it.asJsonPrimitive.isBoolean }?.asBoolean ?: false
    private fun JsonObject.strings(name: String): List<String> = arr(name).mapNotNull { it.takeIf(JsonElement::isJsonPrimitive)?.asString }
    private fun JsonArray.objects(): List<JsonObject> = mapNotNull { it.takeIf(JsonElement::isJsonObject)?.asJsonObject }

    fun rows(snap: JsonObject): List<Row> = snap.arr("registry").objects().mapNotNull { r ->
        val id = r.str("id") ?: return@mapNotNull null
        Row(
            id = id,
            status = r.str("status") ?: "",
            title = r.str("title"),
            summary = r.str("summary"),
            progress = r.obj("progress")?.let { Progress(it.int("done") ?: 0, it.int("total") ?: 0) },
            dependsOn = r.strings("dependsOn"),
            actions = r.strings("actions"),
        )
    }

    fun health(snap: JsonObject): List<Finding> = snap.arr("health").objects().map {
        Finding(it.str("level") ?: "", it.str("workstream"), it.str("task"), it.str("message"))
    }

    fun refresh(snap: JsonObject): List<Watch> = snap.arr("refresh").objects().mapNotNull { w ->
        w.str("path")?.let { Watch(it, w.bool("recursive")) }
    }

    fun wave(snap: JsonObject): Wave? = snap.obj("wave")?.let {
        Wave(it.str("state") ?: "", it.int("phase"), it.strings("ids"), it.strings("open"), it.strings("leftovers"))
    }

    fun tasks(snap: JsonObject): List<Task> = snap.arr("tasks").objects().mapNotNull { t ->
        val id = t.str("id") ?: return@mapNotNull null
        Task(
            id = id,
            phase = t.int("phase") ?: 1,
            priority = t.int("priority") ?: 0,
            status = t.str("status") ?: "",
            blockedBy = t.strings("blockedBy"),
            title = t.str("title"),
            summary = t.str("summary"),
            mode = t.str("mode"),
            needsUserDecision = t.bool("needsUserDecision"),
            startedAt = t.str("startedAt"),
            blockedReason = t.str("blockedReason"),
            acceptanceText = t.strings("acceptanceText"),
            verifyCommands = t.arr("verifyCommands").objects().mapNotNull { v ->
                val command = v.str("command") ?: return@mapNotNull null
                VerifyCommand(v.str("label") ?: command, command)
            },
        )
    }

    fun view(snap: JsonObject): WsView {
        val paths = snap.obj("paths")
        val docs = paths?.entrySet()?.filter { it.value.isJsonPrimitive }?.associate { it.key to it.value.asString } ?: mapOf()
        return WsView(tasks(snap), wave(snap), docs)
    }
}

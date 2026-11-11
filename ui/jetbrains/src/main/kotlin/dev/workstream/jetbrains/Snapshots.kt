// Reads the snapshot JSON the CLI printed into logic/'s shapes. It reads leniently: a field the
// CLI left out is empty, never an error, since the snapshot's schema is the CLI's to change.
package dev.workstream.jetbrains

import com.google.gson.JsonArray
import com.google.gson.JsonElement
import com.google.gson.JsonObject
import dev.workstream.jetbrains.logic.Baseline
import dev.workstream.jetbrains.logic.BaselineKey
import dev.workstream.jetbrains.logic.BudgetRow
import dev.workstream.jetbrains.logic.Scope
import dev.workstream.jetbrains.logic.Finding
import dev.workstream.jetbrains.logic.Loaded
import dev.workstream.jetbrains.logic.LaunchOffer
import dev.workstream.jetbrains.logic.Offer
import dev.workstream.jetbrains.logic.Progress
import dev.workstream.jetbrains.logic.Revisions
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
            progress = r.obj("progress")?.let { Progress(it.int("done") ?: 0, it.int("total") ?: 0, it.int("in-progress") ?: 0) },
            dependsOn = r.strings("dependsOn"),
            actions = r.strings("actions"),
            launches = r.arr("launches").objects().mapNotNull { l ->
                val kind = l.str("kind") ?: return@mapNotNull null
                LaunchOffer(kind, l.str("prompt") ?: return@mapNotNull null, l.str("ask"))
            },
            tier = r.str("tier"),
            created = r.str("created"),
            startedAt = r.str("startedAt"),
            completedAt = r.str("completedAt"),
            baseCommit = r.str("baseCommit"),
            notes = r.str("notes"),
        )
    }

    fun health(snap: JsonObject): List<Finding> = snap.arr("health").objects().map {
        Finding(it.str("level") ?: "", it.str("workstream"), it.str("task"), it.str("message"),
                it.arr("actions").objects().mapNotNull { a ->
                    Offer(a.str("action") ?: return@mapNotNull null, a.str("workstream") ?: return@mapNotNull null, a.str("task"))
                }, it.str("kind"))
    }

    /** The snapshot's git error, when git couldn't be read. */
    fun gitError(snap: JsonObject): String? = snap.obj("git")?.str("error")

    /** `ws audit context --json`'s rows; a row without a role is skipped. */
    fun budget(got: Loaded<JsonElement>): Loaded<List<BudgetRow>> = when (got) {
        is Loaded.Error -> got
        is Loaded.Value -> (got.value as? JsonArray)?.let { rows ->
            Loaded.Value(rows.objects().mapNotNull { r ->
                BudgetRow(r.str("role") ?: return@mapNotNull null, r.int("tokens") ?: 0, r.int("budget") ?: 0, r.bool("ok"))
            })
        } ?: Loaded.Error("audit context printed no rows")
    }

    /** The revisions a write against this snapshot expects; null when the CLI printed none. */
    fun revisions(snap: JsonObject): Revisions? = snap.obj("revisions")?.let { r ->
        val registry = r.str("registry") ?: return@let null
        val tasks = r.obj("tasks")?.entrySet()?.filter { it.value.isJsonPrimitive }?.associate { it.key to it.value.asString } ?: mapOf()
        Revisions(registry, tasks)
    }

    fun integrationBranch(snap: JsonObject): String? = snap.str("integrationBranch")

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
            unblocks = t.strings("unblocks"),
            waitingOn = t.strings("waitingOn"),
            files = t.strings("files"),
            notes = t.str("notes"),
            claimedBy = t.str("claimedBy"),
        )
    }

    /**
     * The workstream's tasks file. `ws snapshot -w` names no such path, but its `watch` lists the
     * registry first, then the tasks file, then narrative files `paths` also gives when they exist.
     */
    fun tasksFile(snap: JsonObject, docs: Map<String, String>): String? =
        snap.strings("watch").drop(1).firstOrNull { it !in docs.values }

    fun scope(snap: JsonObject): Scope? = snap.obj("scope")?.let { Scope(it.strings("inScope"), it.strings("outOfScope"), it.str("rule")) }

    fun baseline(snap: JsonObject): Baseline? = snap.obj("baseline")?.let { b ->
        Baseline(b.arr("keys").objects().mapNotNull { k ->
            BaselineKey(k.str("key") ?: return@mapNotNull null, k.str("source") ?: "", k.str("command"), k.int("exit"),
                        k.int("findings") ?: 0, k.str("recordedAt"), k.str("commit"))
        }, b.strings("errors"))
    }

    fun view(snap: JsonObject): WsView {
        val paths = snap.obj("paths")
        val docs = paths?.entrySet()?.filter { it.value.isJsonPrimitive }?.associate { it.key to it.value.asString } ?: mapOf()
        return WsView(tasks(snap), wave(snap), docs, revisions(snap), health(snap), snap.str("repoRoot"), tasksFile(snap, docs),
                      scope(snap), baseline(snap))
    }
}

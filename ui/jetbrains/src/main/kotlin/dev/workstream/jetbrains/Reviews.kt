// Reads the JSON `ws review` printed into logic/'s shapes, as leniently as Snapshots.kt: a field
// the CLI left out is empty, never an error.
package dev.workstream.jetbrains

import com.google.gson.JsonArray
import com.google.gson.JsonElement
import com.google.gson.JsonObject
import dev.workstream.jetbrains.logic.Checks
import dev.workstream.jetbrains.logic.Entry
import dev.workstream.jetbrains.logic.FileStat
import dev.workstream.jetbrains.logic.Gate
import dev.workstream.jetbrains.logic.Item
import dev.workstream.jetbrains.logic.Loaded
import dev.workstream.jetbrains.logic.Range
import dev.workstream.jetbrains.logic.Review
import dev.workstream.jetbrains.logic.ShowSide

object Reviews {
    private fun JsonObject.obj(name: String): JsonObject? = get(name)?.takeIf { it.isJsonObject }?.asJsonObject
    private fun JsonObject.arr(name: String): JsonArray = get(name)?.takeIf { it.isJsonArray }?.asJsonArray ?: JsonArray()
    private fun JsonObject.str(name: String): String? = get(name)?.takeIf { it.isJsonPrimitive }?.asString
    private fun JsonObject.int(name: String): Int? = get(name)?.takeIf { it.isJsonPrimitive && it.asJsonPrimitive.isNumber }?.asInt
    private fun JsonObject.bool(name: String): Boolean = get(name)?.takeIf { it.isJsonPrimitive && it.asJsonPrimitive.isBoolean }?.asBoolean ?: false
    private fun JsonArray.objects(): List<JsonObject> = mapNotNull { it.takeIf(JsonElement::isJsonObject)?.asJsonObject }

    private fun <T> read(got: Loaded<JsonElement>, what: String, parse: (JsonObject) -> T?): Loaded<T> = when (got) {
        is Loaded.Error -> got
        is Loaded.Value -> (got.value as? JsonObject)?.let(parse)?.let { Loaded.Value(it) } ?: Loaded.Error("$what printed no object")
    }

    fun queue(got: Loaded<JsonElement>): Loaded<List<Entry>> = read(got, "review queue") { q ->
        q.arr("tasks").objects().mapNotNull { e ->
            Entry(
                workstream = e.str("workstream") ?: return@mapNotNull null,
                task = e.str("task") ?: return@mapNotNull null,
                state = e.str("state") ?: "",
                title = e.str("title"),
                status = e.str("status"),
                revision = e.str("revision"),
                files = e.int("files") ?: 0,
                added = e.int("added") ?: 0,
                removed = e.int("removed") ?: 0,
                hasEvidence = e.bool("hasEvidence"),
            )
        }
    }

    fun review(got: Loaded<JsonElement>): Loaded<Review> = read(got, "review") { r ->
        val range = r.obj("range")?.let { Range(it.str("kind") ?: "none", it.str("from"), it.str("to")) } ?: Range("none")
        Review(
            task = r.str("task") ?: "",
            evidence = r.str("evidence"),
            range = range,
            files = r.arr("files").objects().mapNotNull { f -> FileStat(f.str("path") ?: return@mapNotNull null, f.int("added"), f.int("removed")) },
            checks = r.obj("checks")?.let { c ->
                Checks(
                    state = c.str("state") ?: "",
                    commit = c.str("commit"),
                    gates = c.arr("gates").objects().mapNotNull { g ->
                        Gate(g.str("name") ?: return@mapNotNull null, g.bool("ok"), g.bool("blocking"), g.str("detail"))
                    },
                    evidenceText = c.str("evidenceText"),
                    evidenceStatus = c.str("evidenceStatus"),
                    reason = c.str("reason"),
                    items = c.arr("items").objects().mapNotNull { i ->
                        Item(i.int("n") ?: return@mapNotNull null, i.str("item") ?: "", i.str("proof") ?: "")
                    },
                )
            },
            error = r.str("error"),
        )
    }

    fun show(got: Loaded<JsonElement>): Loaded<ShowSide> = read(got, "review --show") { s ->
        ShowSide(s.str("path") ?: "", s.str("side") ?: "", s.str("rev") ?: return@read null, s.str("text"), s.bool("binary"))
    }
}

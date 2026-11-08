// The Review tab in a headless IDE, on a project with one task on a branch and one landed, as
// ui/vscode's integration suite builds it: the queue, a task's checks, diffs from `ws review
// --show` after main moved, a binary file, and both kinds of evidence.
package dev.workstream.jetbrains

import com.google.gson.JsonObject
import com.google.gson.JsonParser
import com.intellij.diff.contents.DocumentContent
import com.intellij.diff.requests.DiffRequest
import com.intellij.openapi.fileEditor.FileEditorManager
import com.intellij.openapi.fileEditor.ex.FileEditorManagerEx
import com.intellij.openapi.util.Disposer
import com.intellij.testFramework.LightVirtualFile
import com.intellij.testFramework.PlatformTestUtil
import com.intellij.util.ui.tree.TreeUtil
import dev.workstream.jetbrains.logic.EvidenceNode
import dev.workstream.jetbrains.logic.FileNode
import dev.workstream.jetbrains.logic.ReviewNode
import java.io.File
import java.util.concurrent.CompletableFuture

class ReviewViewTest : SampleTestCase() {
    private lateinit var panel: ReviewPanel
    private val shownDiffs = mutableListOf<DiffRequest>()
    private lateinit var savedShow: (com.intellij.openapi.project.Project, DiffRequest) -> Unit

    override fun setUp() {
        super.setUp()
        panel = ReviewPanel(project, Disposer.newDisposable(testRootDisposable, "review"))
        savedShow = ReviewOpen.showDiff
        ReviewOpen.showDiff = { _, request -> shownDiffs += request }
    }

    override fun tearDown() {
        try {
            ReviewOpen.showDiff = savedShow
            FileEditorManagerEx.getInstanceEx(project).closeAllFiles()
        } finally {
            super.tearDown()
        }
    }

    private fun evidence(id: String, items: List<String>) = (listOf("# $id evidence", "", "- **Status:** done", "", "## Acceptance", "") + items +
        listOf("", "## Proposed decisions", "", "None.", "", "## Gotchas and follow-ups", "", "None.", "", "## Text to apply", "", "None.", "")).joinToString("\n")

    /**
     * R-1's branch edits shared.txt, adds added.txt and blob.bin, and writes its evidence; main then
     * moves, editing shared.txt too, so the merge base and main's tip disagree. R-2 landed on main.
     */
    private fun reviewProject(): File {
        val root = tmp.resolve("review").toFile().apply { mkdirs() }
        fun write(path: String, text: String) = File(root, path).apply { parentFile.mkdirs() }.writeText(text)
        sh(root, "git", "init", "-q", "-b", "main")
        ws(root, "init", "--integration", "main")
        write("shared.txt", "one\ntwo\nthree\n")
        sh(root, "git", "add", "-A")
        sh(root, "git", "commit", "-qm", "init")
        val base = sh(root, "git", "rev-parse", "--short", "HEAD").trim()
        ws(root, "new", "alpha", "--title", "Alpha", "--summary", "review", "--base", base)
        val seed = tmp.resolve("review-seed.json").toFile()
        seed.writeText("""[{"id": "R-1", "phase": 1, "priority": 10, "title": "On a branch", "acceptance": ["the sides match", "a binary file says so"]},
            {"id": "R-2", "phase": 1, "priority": 20, "title": "Landed", "acceptance": ["it landed"]}]""")
        ws(root, "seed", "-w", "alpha", seed.path)
        ws(root, "set-status", "-w", "alpha", "active")
        sh(root, "git", "add", "-A")
        sh(root, "git", "commit", "-qm", "seeded")
        ws(root, "claim", "R-1", "R-2", "-w", "alpha")
        sh(root, "git", "commit", "-qam", "claim R-1 and R-2")
        val folder = File(File(root, "workstreams"), "alpha")
        val queue = JsonParser.parseString(File(folder, "tasks_list.json").readText()).asJsonObject
        val branch = queue.getAsJsonArray("tasks").map { it.asJsonObject }.first { it.get("id").asString == "R-1" }.get("branch").asString
        val rel = folder.relativeTo(root).path
        sh(root, "git", "checkout", "-qb", branch)
        write("shared.txt", "one\nTWO\nthree\n")
        write("added.txt", "a new file\n")
        File(root, "blob.bin").writeBytes(byteArrayOf(0, 1, 2, 3, 0xff.toByte()))
        write("$rel/evidence/R-1.md", evidence("R-1", listOf(
            "1. the sides match -> `diff` printed \"same\" <b>bold</b> <html><a href=\"x\">link</a>",
            "2. a binary file says so ->",
        )))
        sh(root, "git", "add", "-A")
        sh(root, "git", "commit", "-qm", "R-1 work")
        sh(root, "git", "checkout", "-q", "main")
        write("shared.txt", "zero\none\ntwo\nthree\n")
        write("landed.txt", "landed\n")
        write("$rel/evidence/R-2.md", evidence("R-2", listOf("1. it landed -> `git log` shows it")))
        sh(root, "git", "add", "-A")
        sh(root, "git", "commit", "-qm", "R-2 work")
        ws(root, "update", "R-2", "-w", "alpha", "--status", "done", "--commit", sh(root, "git", "rev-parse", "HEAD").trim())
        sh(root, "git", "commit", "-qam", "R-2 done")
        return root
    }

    private fun openReview(): File {
        val root = reviewProject()
        WsSettings.getInstance().wsCommand = branchCli
        open(root)
        PlatformTestUtil.waitForFuture(panel.model.invalidateAsync())
        PlatformTestUtil.expandAll(panel.tree)
        PlatformTestUtil.waitWhileBusy(panel.tree)
        return root
    }

    private data class Drawn(val depth: Int, val text: String, val tip: String?, val node: ReviewNode)

    private fun drawn(): List<Drawn> = (0 until panel.tree.rowCount).map { i ->
        val path = panel.tree.getPathForRow(i)
        val value = path.lastPathComponent
        val renderer = panel.tree.cellRenderer.getTreeCellRendererComponent(panel.tree, value, false, true, panel.tree.model.isLeaf(value), i, false) as ReviewRenderer
        Drawn(path.pathCount - 2, renderer.getCharSequence(false).toString(), renderer.toolTipText, (TreeUtil.getUserObject(value) as ReviewDescriptor).node!!)
    }

    private fun show(root: File, path: String, side: String): JsonObject =
        JsonParser.parseString(ws(root, "review", "R-1", "-w", "alpha", "--show", path, "--side", side)).asJsonObject

    private fun file(name: String, task: String = "R-1"): FileNode = drawn().map { it.node }.filterIsInstance<FileNode>().first { it.task == task && it.file.path == name }

    private fun <T> done(future: CompletableFuture<T>): T {
        assertTrue("the open finished", waitFor(60_000) { future.isDone })
        return future.get()
    }

    fun testTheQueueShowsBranchWorkFirstWithEachTasksChecks() {
        openReview()
        val rows = drawn()
        val outline = rows.map { "  ".repeat(it.depth) + it.text }
        println("review outline: $outline")
        assertEquals("On a branch  1", outline[0])
        assertTrue(outline[1], outline[1].startsWith("  R-1 On a branch  alpha · 4 files +"))
        assertTrue(outline[2], Regex("^    branch: [0-9a-f]{10}\\.\\.\\.task/r-1$").matches(outline[2]))
        assertTrue(outline[3], Regex("would stop this landing|Would land|Every check passes").containsMatchIn(outline[3]))
        val proof = rows.first { it.text.startsWith("1. the sides match") }
        // The proof is drawn as the text it is, and its tooltip escapes it.
        assertEquals("1. the sides match  `diff` printed \"same\" <b>bold</b> <html><a href=\"x\">link</a>", proof.text)
        assertFalse(proof.tip!!, proof.tip.contains("<b>bold") || proof.tip.contains("<a href"))
        assertTrue(proof.tip, proof.tip.contains("&lt;b&gt;bold"))
        assertTrue(outline.contains("      2. a binary file says so  Nothing quoted."))
        val landedAt = outline.indexOf("Landed  1")
        assertTrue(outline.toString(), landedAt > 2)
        assertTrue(outline[landedAt + 1], outline[landedAt + 1].startsWith("  R-2 Landed  alpha · "))
        assertTrue(outline[landedAt + 3], Regex("^    Landed as [0-9a-f]{10}\\. Its gates ran when it landed\\.$").matches(outline[landedAt + 3]))
        assertEquals(listOf("added.txt  +1 −0", "blob.bin  binary", "shared.txt  +1 −1"),
                     rows.filter { it.node is FileNode && (it.node as FileNode).task == "R-1" }.map { it.text }.filter { !it.contains("evidence") })
    }

    fun testABranchFileAfterMainMovedDiffsTheShowSidesTitledWithTheirRevs() {
        val root = openReview()
        val opened = done(ReviewOpen.openFile(project, file("shared.txt")))
        assertTrue(opened.toString(), opened is Opened.Diff)
        val request = (opened as Opened.Diff).request
        assertEquals(listOf<DiffRequest>(request), shownDiffs)
        val (left, right) = request.contents.map { (it as DocumentContent).document.text }
        val old = show(root, "shared.txt", "old")
        val now = show(root, "shared.txt", "new")
        assertEquals(old.get("text").asString, left)
        assertEquals(now.get("text").asString, right)
        assertEquals("one\ntwo\nthree\n", left)
        assertEquals("one\nTWO\nthree\n", right)
        val mainTip = sh(root, "git", "show", "main:shared.txt")
        assertFalse(left == mainTip)
        val oldRev = old.get("rev").asString
        val newRev = now.get("rev").asString
        assertEquals(sh(root, "git", "merge-base", "main", "task/r-1").trim(), oldRev)
        assertEquals(listOf("old ${oldRev.take(10)}", "new ${newRev.take(10)}"), request.contentTitles)
        assertEquals("shared.txt (R-1: ${oldRev.take(10)} ↔ ${newRev.take(10)})", request.title)
        println("shared.txt: titles ${request.contentTitles}, title ${request.title}; left ${left.trim().lines()} = --show old at $oldRev; right ${right.trim().lines()}; main's tip ${mainTip.trim().lines()}")

        val added = done(ReviewOpen.openFile(project, file("added.txt"))) as Opened.Diff
        assertTrue(show(root, "added.txt", "old").get("text").isJsonNull)
        assertEquals(listOf("", "a new file\n"), added.request.contents.map { (it as DocumentContent).document.text })
    }

    fun testABinaryFileOpensNoDiffAndSaysSo() {
        val root = openReview()
        val opened = done(ReviewOpen.openFile(project, file("blob.bin")))
        assertEquals(Opened.Said("blob.bin is binary, so no diff opens.", false), opened)
        assertEquals(listOf<DiffRequest>(), shownDiffs)
        assertEquals(listOf("blob.bin is binary, so no diff opens."), notes.map { it.content })
        assertTrue(show(root, "blob.bin", "new").get("binary").asBoolean)
        println("blob.bin: said ${notes.map { it.content }}, diffs shown ${shownDiffs.size}")
    }

    fun testBranchEvidenceOpensReadOnlyAndLandedEvidenceOpensAsItsFile() {
        val root = openReview()
        val nodes = drawn().map { it.node }.filterIsInstance<EvidenceNode>()
        val branch = nodes.first { it.task == "R-1" }
        val opened = ReviewOpen.openEvidence(project, branch) as Opened.Evidence
        assertTrue(opened.file.toString(), opened.file is LightVirtualFile)
        assertFalse(opened.file.isWritable)
        assertEquals("R-1.md", opened.file.name)
        val rel = File(File("workstreams"), "alpha").path
        val onBranch = sh(root, "git", "show", "task/r-1:$rel/evidence/R-1.md")
        assertEquals(onBranch.trimEnd(), (opened.file as LightVirtualFile).content.toString().trimEnd())
        assertTrue(FileEditorManager.getInstance(project).isFileOpen(opened.file))
        println("R-1 evidence: ${opened.file.javaClass.simpleName} ${opened.file.name}, writable ${opened.file.isWritable}, ${onBranch.length} chars as on the branch")

        val landed = ReviewOpen.openEvidence(project, nodes.first { it.task == "R-2" }) as Opened.Evidence
        assertFalse(landed.file is LightVirtualFile)
        assertEquals(File(root, "$rel/evidence/R-2.md").canonicalPath, File(landed.file.path).canonicalPath)
        assertTrue(landed.file.isWritable)
        assertTrue(FileEditorManager.getInstance(project).isFileOpen(landed.file))
        println("R-2 evidence: ${landed.file.path}")
    }
}

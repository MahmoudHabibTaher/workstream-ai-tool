"""The web UI's files. There's no build step, so what's checked here is what ships. These hold
what would otherwise rest on someone's care: nothing is fetched from another host, repo text
can't become markup, the page writes in one place, and the files are package data."""

from __future__ import annotations

import re
import shutil
import subprocess
import tomllib
import unittest
from pathlib import Path

from workstream import serve

REPO = Path(__file__).resolve().parent.parent
WEB = serve.WEB_DIR
TESTS = REPO / "ui" / "web" / "tests"
SCRIPTS = sorted(WEB.glob("*.js"))
NODE = shutil.which("node")


def script_text(name: str) -> str:
    return (WEB / name).read_text()


class ShippedFilesTests(unittest.TestCase):
    def test_every_file_is_something_the_server_serves(self) -> None:
        for path in WEB.iterdir():
            self.assertIn(path.suffix, serve.CONTENT_TYPES, path.name)
            self.assertTrue(path.is_file(), f"{path.name}: the server's listing is flat")

    def test_the_files_are_package_data(self) -> None:
        config = tomllib.loads((REPO / "pyproject.toml").read_text())
        self.assertIn("assets/web/*", config["tool"]["setuptools"]["package-data"]["workstream"])

    def test_nothing_is_fetched_from_another_host(self) -> None:
        outside = re.compile(r"""(?:src|href)=["'](?:https?:)?//|url\(\s*["']?(?:https?:)?//|@import""")
        for path in WEB.iterdir():
            self.assertIsNone(outside.search(path.read_text()), path.name)

    def test_the_page_names_only_files_that_exist(self) -> None:
        index = (WEB / "index.html").read_text()
        for name in re.findall(r"/static/([\w.-]+)", index):
            self.assertTrue((WEB / name).is_file(), name)

    def test_every_import_resolves(self) -> None:
        for path in SCRIPTS:
            for name in re.findall(r"""from '\./([\w.-]+)'""", path.read_text()):
                self.assertTrue((WEB / name).is_file(), f"{path.name} imports {name}")


class RepoTextStaysTextTests(unittest.TestCase):
    def test_no_script_can_parse_a_string_as_markup_or_code(self) -> None:
        forbidden = re.compile(
            r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|\beval\b|new Function"
            r"|DOMParser|createContextualFragment|srcdoc|setHTML")
        for path in SCRIPTS:
            self.assertIsNone(forbidden.search(path.read_text()), path.name)

    def test_only_markdown_links_come_from_repo_text(self) -> None:
        # A href built from a repo value elsewhere must go through the hrefs table.
        for path in SCRIPTS:
            if path.name in ("dom.js", "mdview.js", "markdown.js", "logic.js"):
                continue
            for match in re.findall(r"href: ([^,}\n]+)", path.read_text()):
                self.assertIn("hrefs.", match, f"{path.name}: {match}")

    def test_the_policy_allows_no_inline_script_or_style(self) -> None:
        policy = serve.SECURITY_HEADERS["Content-Security-Policy"]
        self.assertNotIn("unsafe", policy)
        index = (WEB / "index.html").read_text()
        self.assertEqual(re.findall(r"<script(?![^>]*\bsrc=)", index), [])
        self.assertNotIn("<style", index)
        self.assertNotIn(" style=", index)


class TheUiDecidesNothingTests(unittest.TestCase):
    def test_one_place_writes_and_it_sends_the_hashes(self) -> None:
        writers = [p.name for p in SCRIPTS if re.search(r"method:\s*'(POST|PUT|PATCH|DELETE)'", p.read_text())]
        self.assertEqual(writers, ["api.js"])
        api = script_text("api.js")
        self.assertIn("'/api/act'", api)
        self.assertIn("expectRegistry: revisions.registry", api)
        self.assertIn("expectTasks: revisions.tasks[ws]", api)

    def test_the_guards_hashes_are_taken_when_the_box_opens(self) -> None:
        app = script_text("app.js")
        ask = app[app.index("function ask("):app.index("function drawnRevisions")]
        self.assertIn("revisions: drawnRevisions()", ask)
        confirm = app[app.index("async function confirmWrite"):app.index("// --- fetching")]
        self.assertIn("revisions } = state.confirm", confirm)
        self.assertNotIn("state.snapshot", confirm)

    def test_closing_and_abandoning_are_never_writes(self) -> None:
        for path in SCRIPTS:
            self.assertNotRegex(path.read_text(), r"action: '(close|abandon|settle)'", path.name)


class ReviewScreensTests(unittest.TestCase):
    def test_a_review_fetches_only_its_review(self) -> None:
        # The queue comes with every screen, from the shell.
        source = script_text("review.js")
        fetches = source[source.index("export const fetches"):source.index("\n\n", source.index("export const fetches"))]
        self.assertIn("urls.review(", fetches)
        self.assertNotRegex(source, r"urls\.(snapshot|doc|budget)|\bfetch\(|getJson")

    def test_the_queue_screen_fetches_nothing_of_its_own(self) -> None:
        source = script_text("queue.js")
        self.assertIn("export const fetches = () => ({})", source)
        self.assertNotRegex(source, r"urls\.|\bfetch\(|getJson")

    def test_the_shell_always_fetches_the_queue(self) -> None:
        self.assertIn("getJson(urls.queue())", script_text("app.js"))
        self.assertEqual(script_text("api.js").count("'/api/queue'"), 1)

    def test_review_screens_never_write(self) -> None:
        for name in ("review.js", "queue.js"):
            self.assertNotRegex(script_text(name), r"\bact\b|ctx\.ask")


class HealthScreenTests(unittest.TestCase):
    def test_a_findings_buttons_come_only_from_its_actions(self) -> None:
        source = script_text("health.js")
        self.assertIn("f.actions.map(a =>", source)
        self.assertIn("ctx.ask({ ws: a.workstream, action: a.action, task: a.task })", source)
        self.assertEqual(re.findall(r"action: '(\w+)'", source), ["sync"])

    def test_sync_shows_only_on_a_stale_row(self) -> None:
        source = script_text("health.js")
        self.assertIn("registry.filter(row => row.progressStale)", source)
        self.assertIn("stale.map(row =>", source)
        lanes = script_text("lanes.js")
        self.assertIn("row?.progressStale && button('Sync progress'", lanes)

    def test_the_budget_is_read_not_worked_out(self) -> None:
        source = script_text("budget.js")
        self.assertIn("urls.budget()", source)
        self.assertNotRegex(source, r"\b(150|2500|3000)\b")


@unittest.skipUnless(NODE, "no node here; the page's helpers are checked where there is one")
class PageLogicTests(unittest.TestCase):
    def test_the_pure_helpers(self) -> None:
        tests = sorted(str(p) for p in TESTS.glob("*.test.mjs"))
        self.assertTrue(tests)
        done = subprocess.run([NODE, "--test", *tests], cwd=REPO, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout[-3000:] + done.stderr[-1000:])


if __name__ == "__main__":
    unittest.main()

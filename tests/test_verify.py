"""`ws verify` and `ws baseline`: commands really run, against a real repository."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from tests.helpers import WsTestCase, task
from tests.test_schema import load_schema, problems
from tests.test_settle import SettleTestCase
from workstream import gates, registry, tasks, verify
from workstream.gitutil import common_dir


class VerifyTestCase(WsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.new_ws()

    def arrange(self, *keys: str, **commands: str) -> None:
        self.set_commands(**commands)
        self.seed_ok([task("T1", 10, verify=list(keys or commands))])
        self.commit_all("seeded")

    def script(self, name: str, body: str) -> str:
        """A command that runs this Python, written outside the repository."""
        path = self.root.parent / f"{name}.py"
        path.write_text(body)
        return f"{sys.executable} {path}"


class RunTests(VerifyTestCase):
    def test_a_pass_records_the_exit_and_the_tree(self) -> None:
        self.arrange(test="true")
        out = self.ok("verify", "T1")
        self.assertIn("PASS test", out)
        run = verify.load_run(self.project(), "alpha", "T1")
        self.assertEqual(run["results"][0]["exit"], 0)
        self.assertEqual(run["tree"], verify.code_tree(self.project()))
        self.assertEqual(run["problems"], [])

    def test_a_failure_exits_1_and_says_where_the_log_is(self) -> None:
        self.arrange(test="echo boom; exit 3")
        out = self.fails("verify", "T1")
        self.assertIn("FAIL test", out)
        self.assertIn("| boom", out)
        self.assertIn("full log:", out)

    def test_every_key_runs_even_after_one_fails(self) -> None:
        self.arrange(lint="exit 1", test="true")
        out = self.fails("verify", "T1")
        self.assertIn("FAIL lint", out)
        self.assertIn("PASS test", out)

    def test_a_raw_command_runs_as_written(self) -> None:
        self.seed_ok([task("T1", 10, verify=["echo hello world"])])
        self.commit_all("seeded")
        self.assertIn("PASS echo hello world", self.ok("verify", "T1"))

    def test_a_key_the_config_lacks_fails_without_running(self) -> None:
        self.seed_ok([task("T1", 10, verify=["nope"])])
        self.assertIn("not in [commands]", self.fails("verify", "T1"))

    def test_no_commands_is_not_a_failure(self) -> None:
        self.seed_ok([task("T1", 10)])
        self.assertIn("no verify commands", self.ok("verify", "T1"))

    def test_a_key_this_task_does_not_use_is_refused(self) -> None:
        self.arrange("test", test="true", lint="true")
        self.assertIn("does not verify with lint", self.fails("verify", "T1", "--key", "lint"))

    def test_a_command_gets_no_stdin_to_hang_on(self) -> None:
        self.arrange(test="cat")
        self.ok("verify", "T1")

    def test_json_output(self) -> None:
        self.arrange(test="true")
        data = json.loads(self.ok("verify", "T1", "--json"))
        self.assertEqual(data["results"][0]["verdict"], "pass")


class BoundedOutputTests(VerifyTestCase):
    def test_a_huge_log_reaches_the_agent_as_a_few_lines(self) -> None:
        noisy = self.script("noisy", "for n in range(200000):\n"
                                     "    print('line', n, 'x' * 100)\n"
                                     "raise SystemExit(1)\n")
        self.arrange(test=noisy)
        out = self.fails("verify", "T1")
        self.assertLess(len(out), 6000)
        run = verify.load_run(self.project(), "alpha", "T1")
        self.assertGreater(Path(run["results"][0]["log"]).stat().st_size, 10_000_000)

    def test_one_enormous_line_is_cut(self) -> None:
        wide = self.script("wide", "print('x' * 1000000)\nraise SystemExit(1)\n")
        self.arrange(test=wide)
        self.assertLess(len(self.fails("verify", "T1")), 2000)

    def test_a_flood_of_new_findings_is_capped(self) -> None:
        flood = self.script("flood", "for n in range(5000):\n    print(f'a.py:{n}: bad{n}')\n")
        self.arrange(lint=flood)
        self.append_config('[baseline.lint]\nparser = "regex"\n'
                           r"pattern = '^(?P<file>\S+):\d+: (?P<m>.*)$'")
        out = self.fails("verify", "T1")
        self.assertLess(len(out), 6000)
        self.assertIn("...and 4980 more", out)


class TimeoutTests(VerifyTestCase):
    def test_a_command_past_its_time_is_killed_with_its_children(self) -> None:
        self.append_config("[verify]\ntimeout_seconds = 1")
        marker = self.root.parent / "survived"
        self.arrange(test=f"(sleep 3; touch {marker}) & wait")
        out = self.fails("verify", "T1")
        self.assertIn("timed out", out)
        subprocess.run(["sleep", "3.5"])
        self.assertFalse(marker.exists())


class RecordTests(VerifyTestCase):
    def test_records_are_shared_by_worktrees_and_never_in_the_tree(self) -> None:
        self.arrange(test="true")
        self.ok("verify", "T1")
        self.assertTrue(verify.runs_dir(self.project(), "alpha", "T1")
                        .is_relative_to(common_dir(self.root)))
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_a_partial_run_keeps_earlier_results_on_the_same_tree(self) -> None:
        self.arrange(lint="true", test="true")
        self.ok("verify", "T1")
        self.ok("verify", "T1", "--key", "test")
        run = verify.load_run(self.project(), "alpha", "T1")
        self.assertEqual([r["key"] for r in run["results"]], ["lint", "test"])
        self.assertEqual(run["problems"], [])

    def test_a_partial_run_on_changed_code_drops_earlier_results(self) -> None:
        self.arrange(lint="true", test="true")
        self.ok("verify", "T1")
        (self.root / "new.txt").write_text("x")
        code, out, _ = self.ws("verify", "T1", "--key", "test")
        self.assertEqual(code, 1, out)
        self.assertEqual(verify.load_run(self.project(), "alpha", "T1")["problems"],
                         ["lint: not run"])

    def test_a_command_that_rewrites_code_does_not_vouch_for_it(self) -> None:
        self.arrange(fmt="echo changed >> formatted.txt")
        out = self.fails("verify", "T1")
        self.assertIn("changed the code", out)

    def test_an_interrupted_record_reads_as_not_verified(self) -> None:
        self.arrange(test="true")
        self.ok("verify", "T1")
        path = verify.runs_dir(self.project(), "alpha", "T1") / "latest.json"
        path.write_text('{"tree": ')
        self.assertIsNone(verify.load_run(self.project(), "alpha", "T1"))


class CodeTreeTests(VerifyTestCase):
    def tree(self, rev: str | None = None) -> str:
        return verify.code_tree(self.project(), rev)

    def racy_edit(self) -> Path:
        """A committed file, edited to the same size in the same second as its index entry,
        which only git's racy check can catch. No sleeping: the file and the real index are put
        at one old time, and without ctime the stat data then says nothing changed."""
        self.git("config", "core.trustctime", "false")
        path = self.root / "code.txt"
        path.write_text("before\n")
        old = int(time.time()) - 3600
        os.utime(path, (old, old))
        self.commit_all("the code")
        path.write_text("after!\n")
        os.utime(path, (old, old))
        os.utime(self.root / ".git" / "index", (old, old))
        # No optional locks: a plain status would rewrite the index and spoil the setup.
        self.assertIn(" M code.txt", self.git("--no-optional-locks", "status", "--porcelain"))
        return path

    def test_a_racy_same_size_edit_changes_the_hash(self) -> None:
        self.racy_edit()
        first = self.tree()
        self.assertNotEqual(first, self.tree("HEAD"))
        self.assertEqual(self.tree(), first)
        self.commit_all("the edit")
        self.assertEqual(self.tree("HEAD"), first)

    def test_a_discarded_racy_edit_leaves_a_record_the_gate_refuses(self) -> None:
        seen = self.root.parent / "seen.txt"
        self.arrange(test=f"cat code.txt > {seen}")
        path = self.racy_edit()
        self.assertIn("PASS test", self.ok("verify", "T1"))
        self.assertEqual(seen.read_text(), "after!\n")
        self.git("checkout", "--", "code.txt")
        self.assertEqual(path.read_text(), "before\n")
        project = self.project()
        ws = registry.find(registry.load(project), "alpha")
        task_ = tasks.find_task(tasks.load(project.tasks_path(ws), project.config), "T1")
        found = gates.verification_gates(project, ws, task_, {self.tree("HEAD")})
        same = next(g for g in found if g["name"] == "the verified code is what would land")
        self.assertFalse(same["ok"], found)

    def test_the_working_tree_matches_its_commit(self) -> None:
        self.commit_all("x")
        self.assertEqual(self.tree(), self.tree("HEAD"))

    def test_uncommitted_and_untracked_changes_count(self) -> None:
        self.commit_all("x")
        before = self.tree()
        (self.root / "new.txt").write_text("x")
        self.assertNotEqual(self.tree(), before)
        committed = self.tree()
        self.commit_all("y")
        self.assertEqual(self.tree("HEAD"), committed)

    def test_tracking_files_do_not_count(self) -> None:
        self.commit_all("x")
        before = self.tree()
        evidence = self.ws_dir / "alpha" / "evidence"
        evidence.mkdir()
        (evidence / "T1.md").write_text("x")
        self.registry.write_text(self.registry.read_text() + " ")
        self.assertEqual(self.tree(), before)

    def test_ignored_files_do_not_count(self) -> None:
        (self.root / ".gitignore").write_text("build/\n")
        self.commit_all("x")
        before = self.tree()
        (self.root / "build").mkdir()
        (self.root / "build" / "out").write_text("x")
        self.assertEqual(self.tree(), before)

    def test_the_real_index_is_untouched(self) -> None:
        self.commit_all("x")
        (self.root / "new.txt").write_text("x")
        self.tree()
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "")
        self.assertIn("?? new.txt", self.git("status", "--porcelain"))

    def test_a_bad_revision_is_empty_not_an_error(self) -> None:
        self.assertEqual(self.tree("no-such-rev"), "")


LINT_PATTERN = r"^(?P<file>\S+):\d+: (?P<m>.*)$"


class BaselineTests(VerifyTestCase):
    def lint_prints(self, *lines: str) -> None:
        (self.root.parent / "findings.txt").write_text("\n".join(lines) + "\n")

    def arrange_lint(self) -> None:
        self.lint_prints("a.py:1: old")
        lint = f"cat {self.root.parent / 'findings.txt'}; exit 1"
        self.set_commands(lint=lint)
        self.append_config(f"[baseline.lint]\nparser = \"regex\"\npattern = '{LINT_PATTERN}'")
        self.seed_ok([task("T1", 10, verify=["lint"])])
        self.commit_all("seeded")

    def test_known_findings_pass_and_new_ones_fail(self) -> None:
        self.arrange_lint()
        self.fails("verify", "T1")
        self.ok("baseline", "record")
        self.commit_all("baseline")
        self.assertIn("PASS lint", self.ok("verify", "T1"))
        self.lint_prints("a.py:7: old", "b.py:2: new one")
        out = self.fails("verify", "T1")
        self.assertIn("new: b.py | new one", out)

    def test_a_dirty_tree_is_refused(self) -> None:
        self.arrange_lint()
        (self.root / "README").write_text("x")
        self.commit_all("x")
        (self.root / "README").write_text("y")
        self.assertIn("clean tree", self.fails("baseline", "record"))

    def test_show(self) -> None:
        self.arrange_lint()
        self.assertIn("no baseline", self.ok("baseline", "show"))
        self.ok("baseline", "record")
        self.assertIn("lint: exit 1, 1 known", self.ok("baseline", "show"))

    def test_recording_warns_about_a_red_exit_code_command(self) -> None:
        self.set_commands(test="exit 1")
        self.seed_ok([task("T1", 10, verify=["test"])])
        self.commit_all("seeded")
        self.assertIn("can't pass", self.ok("baseline", "record"))

    def test_only_named_keys_are_recorded(self) -> None:
        self.arrange_lint()
        self.assertIn("not in [commands]", self.fails("baseline", "record", "nope"))


ASKED = "75/2/16"
ITEM = {"text": "the counts match", "expect": ASKED}


class ExpectTests(VerifyTestCase):
    def arrange_item(self, item: object, **commands: str) -> None:
        self.set_commands(**commands)
        self.seed_ok([task("T1", 10, verify=list(commands), acceptance=[item])])
        self.commit_all("seeded")

    def test_a_string_missing_from_the_log_fails(self) -> None:
        self.arrange_item(ITEM, test="echo 72/5/16")
        out = self.fails("verify", "T1")
        self.assertIn("PASS test", out)
        self.assertIn(f"acceptance 1: expected output not in the logs: {ASKED}", out)
        run = verify.load_run(self.project(), "alpha", "T1")
        self.assertEqual(run["missingOutput"], [{"item": 1, "expect": ASKED}])
        self.assertEqual(verify.run_problems(run, ["test"]),
                         [f"acceptance 1: expected output not in the logs: {ASKED}"])

    def test_a_string_split_by_ansi_codes_is_found(self) -> None:
        colored = self.script("colored", "print('\\x1b[32m75/\\x1b[0m2/\\x1b[1;31m16\\x1b[0m')\n")
        self.arrange_item(ITEM, test=colored)
        self.ok("verify", "T1")
        run = verify.load_run(self.project(), "alpha", "T1")
        self.assertIn(b"\x1b[", Path(run["results"][0]["log"]).read_bytes())
        self.assertEqual(run["problems"], [])

    def test_no_expect_behaves_as_before(self) -> None:
        self.set_commands(test="true")
        self.seed_ok([task("T1", 10, verify=["test"], acceptance=[
            "plain", {"text": "object"}, {"text": "a person", "kind": "manual"}])])
        self.commit_all("seeded")
        self.ok("verify", "T1")
        run = verify.load_run(self.project(), "alpha", "T1")
        self.assertEqual((run["problems"], run["missingOutput"]), ([], []))

    def test_a_record_from_before_the_field_still_reads(self) -> None:
        self.assertEqual(verify.run_problems({"results": []}, []), [])

    def test_a_manual_item_with_expect_is_refused(self) -> None:
        code, out, err = self.seed([task("T1", 10, verify=["true x"], acceptance=[
            {"text": "a person", "kind": "manual", "expect": ASKED}])])
        self.assertEqual(code, 1, out + err)
        self.assertIn("acceptance 1: a manual item has no command output", out + err)

    def test_an_expect_nothing_could_check_is_refused(self) -> None:
        for fields, reason in (({"expect": " "}, "non-empty string"),
                               ({"expect": 7}, "non-empty string")):
            code, out, err = self.seed([task("T1", 10, verify=["true x"],
                                             acceptance=[{"text": "x", **fields}])])
            self.assertEqual(code, 1, out + err)
            self.assertIn(reason, out + err)
        code, out, err = self.seed([task("T1", 10, acceptance=[ITEM])])
        self.assertEqual(code, 1, out + err)
        self.assertIn("needs a verify command", out + err)

    def test_a_subset_does_not_fail_until_every_key_ran_on_one_tree(self) -> None:
        self.arrange_item(ITEM, lint=f"echo {ASKED}", test="echo other")
        self.fails("verify", "T1", "--key", "test")
        self.assertEqual(verify.load_run(self.project(), "alpha", "T1")["problems"],
                         ["lint: not run"])
        self.ok("verify", "T1", "--key", "lint")
        self.ok("verify", "T1", "--key", "test")

    def test_a_string_no_key_printed_fails_once_all_have_run(self) -> None:
        self.arrange_item(ITEM, lint="echo a", test="echo b")
        out = self.fails("verify", "T1", "--key", "lint")
        self.assertNotIn("expected output", out)
        self.assertIn("expected output", self.fails("verify", "T1", "--key", "test"))

    def test_a_subset_does_not_count_logs_from_another_tree(self) -> None:
        self.arrange_item(ITEM, lint=f"echo {ASKED}", test="echo b")
        self.ok("verify", "T1")
        (self.root / "new.txt").write_text("x")
        out = self.fails("verify", "T1", "--key", "test")
        self.assertNotIn("expected output", out)
        self.assertEqual(verify.load_run(self.project(), "alpha", "T1")["problems"],
                         ["lint: not run"])

    def test_a_key_missing_from_the_config_has_no_log_to_read(self) -> None:
        self.seed_ok([task("T1", 10, verify=["nope"], acceptance=[ITEM])])
        out = self.fails("verify", "T1")
        self.assertIn("not in [commands]", out)
        self.assertIn("expected output", out)

    def test_the_brief_says_what_the_output_must_hold(self) -> None:
        self.arrange_item(ITEM, test="true")
        self.assertIn(f"must contain `{ASKED}`", self.ok("brief", "T1", "-w", "alpha"))

    def test_a_corrected_item_drops_the_old_literal(self) -> None:
        self.arrange_item(ITEM, test="echo 72/5/16")
        self.ok("decide", "Moved", "--why", "the counts moved", "--by", "user", "-w", "alpha")
        self.ok("update", "-w", "alpha", "T1", "--acceptance", "1", "they are 72/5/16",
                "--because", "D001")
        self.assertEqual(self.by_id("T1")["acceptance"],
                         [{"text": "they are 72/5/16 (changed by D001)"}])

    def test_the_schema_matches_the_rules(self) -> None:
        schema = load_schema("tasks")
        items = schema["$defs"]["task"]["properties"]["acceptance"]["items"]
        for good in ("x", {"text": "x"}, {"text": "x", "kind": "manual"}, ITEM,
                     {**ITEM, "kind": "command"}):
            self.assertEqual(problems(good, items, schema), [], good)
        for bad in ({**ITEM, "kind": "manual"}, {"text": "x", "expect": 7}, {"text": "x", "kind": "y"}):
            self.assertTrue(problems(bad, items, schema), bad)

    def test_the_protocol_and_ws_plan_name_it(self) -> None:
        self.assertIn('"expect"', self.ok("protocol", "task-schema"))
        skill = Path(verify.__file__).parent / "assets" / "skills" / "ws-plan" / "SKILL.md"
        self.assertIn("`expect`", skill.read_text())


class ExpectGateTests(SettleTestCase):
    def worked(self) -> Path:
        self.set_commands(check="echo 72/5/16")
        self.arrange(task("T1", 10, verify=["check"], acceptance=[ITEM]))
        where = self.claim("T1")[0]
        (where / "T1.txt").write_text("x\n")
        code, out, err = self.ws_at(where, "verify", "T1", "-w", "alpha")
        self.assertEqual(code, 1, out + err)
        self.finish(where, "T1", run_verify=False)
        return where

    def test_the_evidence_check_and_settle_see_the_missing_string(self) -> None:
        where = self.worked()
        code, out, err = self.ws_at(where, "evidence", "check", "T1", "-w", "alpha")
        self.assertEqual(code, 1, out + err)
        self.assertIn(f"expected output not in the logs: {ASKED}", out + err)
        out = self.fails("settle", "T1")
        self.assertIn(f"expected output not in the logs: {ASKED}", out)
        self.assertNotEqual(self.by_id("T1")["status"], "done")

    def test_a_present_string_settles(self) -> None:
        self.set_commands(check=f"echo {ASKED}")
        self.arrange(task("T1", 10, verify=["check"], acceptance=[ITEM]))
        where = self.claim("T1")[0]
        self.finish(where, "T1")
        code, out, err = self.ws_at(where, "evidence", "check", "T1", "-w", "alpha")
        self.assertEqual(code, 0, out + err)
        self.ok("settle", "T1")
        self.assertEqual(self.by_id("T1")["status"], "done")

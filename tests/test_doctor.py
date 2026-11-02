"""`ws doctor`: the checks, and that running them changes nothing."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest import mock

from tests.helpers import WsTestCase, task
from workstream import doctor
from workstream.cli import main


class DoctorCase(WsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.set_commands(test="true")
        self.commit_all("config")

    def gates(self, *argv: str) -> dict[str, dict]:
        data = json.loads(self.ws("doctor", "--json", *argv)[1])
        return {g["name"]: g for g in data}

    def failed(self, **kw) -> list[str]:
        return [g["name"] for g in doctor.doctor(self.root, **kw) if not g["ok"] and g["blocking"]]

    def warned(self) -> list[str]:
        return [g["name"] for g in doctor.doctor(self.root) if not g["ok"] and not g["blocking"]]

    def tree_bytes(self) -> dict[str, bytes]:
        return {str(p): p.read_bytes() for p in self.root.rglob("*")
                if p.is_file() and ".git" not in p.parts}


class GoodRepoTests(DoctorCase):
    def test_a_good_repo_passes(self) -> None:
        out = self.ok("doctor")
        self.assertEqual(out.splitlines()[-1], "OK")
        self.assertNotIn("FAIL", out)

    def test_it_writes_nothing(self) -> None:
        self.new_ws()
        self.seed_ok([task("T1", 10, verify=["test"])])
        self.commit_all("planned")
        before = self.tree_bytes()
        self.ok("doctor")
        self.ok("doctor", "--run")
        self.assertEqual(self.tree_bytes(), before)
        self.assertEqual(self.git("status", "--porcelain"), "")


class FailureTests(DoctorCase):
    def test_a_broken_config_fails_without_a_traceback(self) -> None:
        (self.root / ".workstream" / "config.toml").write_text("not toml =\n")
        found = doctor.doctor(self.root)
        self.assertIn("the config parses", [g["name"] for g in found if not g["ok"]])

    def test_a_config_with_an_unknown_section_fails(self) -> None:
        self.append_config("[nope]\nx = 1")
        self.assertEqual(self.failed(), ["the config parses"])

    def test_a_missing_integration_branch_fails(self) -> None:
        self.edit_config('integration = "main"', 'integration = "gone"')
        self.assertIn("the integration branch gone exists", self.failed())

    def test_an_invalid_queue_fails(self) -> None:
        self.new_ws()
        self.write_queue([task("T1", 10, status="done")])
        self.assertTrue([n for n in self.failed() if "valid" in n])
        self.assertIn("done without a commit", self.gates()["1 workstream(s) are valid"]["detail"])

    def test_a_broken_registry_fails(self) -> None:
        self.registry.write_text("{broken")
        self.assertTrue(self.failed())


class WarningTests(DoctorCase):
    def test_a_missing_tool_warns(self) -> None:
        self.edit_config('test = "true"', 'test = "no-such-tool-here --go"')
        self.assertIn("each command's tool is here", self.warned())
        self.assertEqual(self.failed(), [])

    def test_a_relative_tool_is_looked_for_in_the_repo(self) -> None:
        self.edit_config('test = "true"', 'test = "./gradlew test"')
        self.assertIn("each command's tool is here", self.warned())
        (self.root / "gradlew").write_text("")
        self.assertNotIn("each command's tool is here", self.warned())

    def test_an_uncommitted_config_warns(self) -> None:
        self.git("rm", "-q", "--cached", ".workstream/config.toml")
        self.git("commit", "-q", "-m", "untrack")
        self.assertIn("the config is committed", self.warned())

    def test_a_stray_adequacy_key_warns(self) -> None:
        self.edit_config("[adequacy]\n", '[adequacy]\nbehaviour = ["nope"]\n')
        self.assertIn("[adequacy] names only real commands", self.warned())

    def test_a_stray_baseline_key_warns(self) -> None:
        self.append_config('[baseline.gone]\nparser = "exit-code"')
        self.assertIn("[baseline] names only real commands", self.warned())

    def test_no_commands_warns(self) -> None:
        self.edit_config('test = "true"\n', "")
        self.assertIn("there are commands to verify with", self.warned())

    def test_a_missing_production_branch_warns(self) -> None:
        self.edit_config('production = "main"', 'production = "live"')
        self.assertIn("the production branch live exists", self.warned())

    def test_a_file_a_task_will_create_is_not_noise(self) -> None:
        self.new_ws()
        self.seed_ok([task("T1", 10, files=["later.py"])])
        self.commit_all("planned")
        self.assertEqual(self.warned(), [])

    def test_a_stale_claim_shows_up(self) -> None:
        self.new_ws()
        self.write_queue([task("T1", 10, status="in-progress", branch="task/t1",
                               startedAt="2020-01-01T00:00:00Z")])
        self.commit_all("claimed long ago")
        self.assertIn("nothing is left over", self.warned())

    def test_warnings_do_not_fail_it(self) -> None:
        self.edit_config('test = "true"', 'test = "no-such-tool-here"')
        code, out, err = self.ws("doctor")
        self.assertEqual(code, 0, out + err)
        self.assertIn("warn each command's tool is here: test:", out)


class IdentityTests(DoctorCase):
    def test_no_identity_warns(self) -> None:
        without = {k: v for k, v in os.environ.items() if k != "GIT_AUTHOR_EMAIL"}
        with mock.patch.dict(os.environ, without, clear=True):
            self.assertIn("git knows who you are", self.warned())

    def test_a_configured_identity_counts(self) -> None:
        self.git("config", "user.email", "me@example.invalid")
        without = {k: v for k, v in os.environ.items() if k != "GIT_AUTHOR_EMAIL"}
        with mock.patch.dict(os.environ, without, clear=True):
            self.assertNotIn("git knows who you are", self.warned())


class RunTests(DoctorCase):
    def findings(self, *lines: str) -> None:
        (self.root.parent / "findings.txt").write_text("\n".join(lines) + "\n")

    def with_lint(self) -> None:
        self.findings("a.py:1: old")
        self.set_commands(lint=f"cat {self.root.parent / 'findings.txt'}; exit 1")
        self.append_config("[baseline.lint]\nparser = \"regex\"\n"
                           r"pattern = '^(?P<file>\S+):\d+: (?P<m>.*)$'")
        (self.root / ".workstream" / "baseline.json").write_text(json.dumps(
            {"schemaVersion": 1, "keys": {"lint": {"findings": ["a.py | old"]}}}))
        self.commit_all("lint")

    def test_known_findings_pass(self) -> None:
        self.with_lint()
        self.assertEqual(self.failed(run=True), [])

    def test_a_new_finding_fails(self) -> None:
        self.with_lint()
        self.findings("a.py:1: old", "b.py:2: new")
        self.assertEqual(self.failed(run=True), ["lint passes against the baseline"])

    def test_a_failing_command_fails_and_names_its_log(self) -> None:
        self.edit_config('test = "true"', 'test = "exit 3"')
        out = self.fails("doctor", "--run")
        self.assertIn("FAIL test passes against the baseline: exit 3; log:", out)

    def test_nothing_runs_without_the_flag(self) -> None:
        marker = self.root.parent / "ran"
        self.edit_config('test = "true"', f'test = "touch {marker}"')
        self.ok("doctor")
        self.assertFalse(marker.exists())
        self.ok("doctor", "--run")
        self.assertTrue(marker.exists())

    def test_a_workstreams_own_baseline_is_used(self) -> None:
        self.with_lint()
        self.findings("c.py:1: later")
        self.new_ws()
        (self.ws_dir / "alpha" / "baseline.json").write_text(json.dumps(
            {"schemaVersion": 1, "keys": {"lint": {"findings": ["c.py | later"]}}}))
        self.assertEqual(self.failed(run=True), ["lint passes against the baseline"])
        self.assertEqual(self.failed(run=True, ws_id="alpha"), [])


class OutsideAProjectTests(WsTestCase):
    def test_it_says_to_run_init(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            found = doctor.doctor(Path(tmp))
        self.assertEqual([g["detail"] for g in found if not g["ok"]],
                         ["no .workstream/config.toml: run `ws init`"])

    def test_the_command_works_from_the_working_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = os.getcwd()
            os.chdir(tmp)
            self.addCleanup(os.chdir, cwd)
            with mock.patch("builtins.print") as printed:
                self.assertEqual(main(["doctor"]), 1)
        self.assertIn("run `ws init`", str(printed.call_args_list))

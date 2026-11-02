"""The read model. health_findings is tested on in-memory fixtures; git_facts and
build_snapshot run against a throwaway repository."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from tests.helpers import WsTestCase, task
from workstream import snapshot, tasks
from workstream.config import Config
from workstream.fsutil import sha256
from workstream.project import Project

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
CONFIG = Config(integration="trunk")


def full(tid: str, priority: int = 10, status: str = "todo", **extra) -> dict:
    return tasks.normalize_task(task(tid, priority, status=status, **extra), CONFIG)


def clean_inputs() -> tuple[dict, dict, dict]:
    """A registry, queues and git facts that should produce no finding at all."""
    reg = {"workstreams": [{"id": "alpha", "status": "active"}, {"id": "old", "status": "done"}]}
    queues = {
        "alpha": {
            "tasks": [
                full("AL-01", status="done", commit="abc", branch="task/al-one"),
                full("AL-02", 20, status="in-progress", branch="task/al-two",
                     startedAt="2026-10-31T10:00:00Z", claimedBy="worker"),
                full("AL-03", 30, branch="task/al-three"),
            ],
            "evidence": ["AL-01"], "errors": [], "warnings": [],
        },
        # A closed workstream's done tasks are history: never a finding.
        "old": {"tasks": [full("OL-01", status="done", commit="def")], "evidence": [],
                "errors": [], "warnings": []},
    }
    facts = {
        "branch": "trunk",
        "taskBranches": ["task/al-two", "task/al-three"],
        "worktrees": [
            {"path": "/repo", "head": "1", "branch": "trunk", "main": True},
            {"path": "/repo/.wt/two", "head": "2", "branch": "task/al-two", "main": False},
        ],
        "dirtyTracking": [],
    }
    return reg, queues, facts


def kinds(findings: list[dict]) -> list[str]:
    return [f["kind"] for f in findings]


class HealthFindingsTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.project = Project(root=Path(tmp.name).resolve(), config=CONFIG)

    def findings(self, reg, queues, facts, stale_hours: float = 24) -> list[dict]:
        return snapshot.health_findings(self.project, reg, queues, facts, NOW, stale_hours)

    def test_a_clean_fixture_fires_nothing(self) -> None:
        self.assertEqual(self.findings(*clean_inputs()), [])

    def test_invalid_carries_validate_errors_and_warnings_with_their_levels(self) -> None:
        reg, queues, facts = clean_inputs()
        queues["alpha"]["errors"] = ["alpha: AL-02: done without a commit"]
        queues["alpha"]["warnings"] = ["alpha: AL-02 and AL-03 both list 'a'"]
        found = self.findings(reg, queues, facts)
        self.assertEqual([(f["kind"], f["level"], f["workstream"]) for f in found],
                         [("invalid", "error", "alpha"), ("invalid", "warning", "alpha")])
        self.assertEqual(found[0]["message"], "alpha: AL-02: done without a commit")

    def test_stale_claim_fires_past_stale_hours_only(self) -> None:
        reg, queues, facts = clean_inputs()
        self.assertEqual(self.findings(reg, queues, facts, stale_hours=3), [])
        found = self.findings(reg, queues, facts, stale_hours=1)
        self.assertEqual(kinds(found), ["stale-claim"])
        self.assertEqual((found[0]["workstream"], found[0]["task"]), ("alpha", "AL-02"))
        self.assertIn("2h", found[0]["message"])

    def test_unclaim_is_offered_only_when_no_worktree_has_the_branch(self) -> None:
        reg, queues, facts = clean_inputs()
        live = self.findings(reg, queues, facts, stale_hours=0)
        self.assertEqual(kinds(live), ["stale-claim"])
        self.assertEqual(live[0]["actions"], [])
        self.assertIn("a worktree has task/al-two checked out", live[0]["message"])

        facts["worktrees"] = facts["worktrees"][:1]
        gone = self.findings(reg, queues, facts, stale_hours=0)
        self.assertEqual(gone[0]["actions"],
                         [{"action": "unclaim", "workstream": "alpha", "task": "AL-02"}])

    def test_unclaim_is_not_offered_where_act_would_refuse(self) -> None:
        reg, queues, facts = clean_inputs()
        facts["worktrees"] = facts["worktrees"][:1]
        for change in ({"branch": "elsewhere"},
                       {"dirtyTracking": ["workstreams/alpha/tasks_list.json"]},
                       {"dirtyTracking": ["workstreams/workstreams.json"]}):
            found = self.findings(reg, queues, {**facts, **change}, stale_hours=0)
            stale = [f for f in found if f["kind"] == "stale-claim"]
            self.assertEqual(stale[0]["actions"], [], change)

    def test_orphan_branch_fires_for_a_done_task_and_an_unnamed_branch(self) -> None:
        reg, queues, facts = clean_inputs()
        facts["taskBranches"] += ["task/al-one", "task/stray"]
        found = self.findings(reg, queues, facts)
        self.assertEqual(kinds(found), ["orphan-branch", "orphan-branch"])
        self.assertEqual((found[0]["task"], found[0]["message"]),
                         ("AL-01", "branch task/al-one: its task AL-01 is done"))
        self.assertEqual((found[1]["task"], found[1]["message"]),
                         (None, "branch task/stray: no open task names it"))

    def test_orphan_worktree_fires_off_any_in_progress_branch(self) -> None:
        reg, queues, facts = clean_inputs()
        facts["worktrees"] += [
            {"path": "/repo/.wt/three", "head": "3", "branch": "task/al-three", "main": False},
            {"path": "/repo/.wt/detached", "head": "4", "branch": None, "main": False},
        ]
        found = self.findings(reg, queues, facts)
        self.assertEqual(kinds(found), ["orphan-worktree", "orphan-worktree"])
        self.assertIn("/repo/.wt/three on task/al-three", found[0]["message"])
        self.assertIn("a detached HEAD", found[1]["message"])

    def test_missing_evidence_fires_for_a_done_task_in_an_open_workstream(self) -> None:
        reg, queues, facts = clean_inputs()
        queues["alpha"]["evidence"] = []
        found = self.findings(reg, queues, facts)
        self.assertEqual([(f["kind"], f["task"]) for f in found],
                         [("missing-evidence", "AL-01")])

    def test_dirty_tracking_groups_tracking_paths_and_ignores_the_rest(self) -> None:
        reg, queues, facts = clean_inputs()
        facts["dirtyTracking"] = ["workstreams/alpha/PROGRESS.md", "workstreams/tools/x.py",
                                  "workstreams/workstreams.json"]
        found = self.findings(reg, queues, facts)
        self.assertEqual([(f["kind"], f["workstream"]) for f in found],
                         [("dirty-tracking", None), ("dirty-tracking", "alpha")])
        self.assertIn("workstreams/workstreams.json", found[0]["message"])
        self.assertNotIn("tools", found[1]["message"])

    def test_a_workstream_folder_anywhere_owns_its_dirty_paths(self) -> None:
        reg, queues, facts = clean_inputs()
        reg["workstreams"][0]["path"] = "lib/workstreams/alpha"
        facts["dirtyTracking"] = ["lib/workstreams/alpha/PROGRESS.md"]
        found = self.findings(reg, queues, facts)
        self.assertEqual([(f["kind"], f["workstream"]) for f in found],
                         [("dirty-tracking", "alpha")])

    def test_wrong_branch_names_the_configured_integration_branch(self) -> None:
        reg, queues, facts = clean_inputs()
        found = self.findings(reg, queues, {**facts, "branch": "task/al-two"})
        self.assertEqual([(f["kind"], f["level"]) for f in found], [("wrong-branch", "warning")])
        self.assertIn("not trunk", found[0]["message"])

    def test_errors_sort_before_warnings(self) -> None:
        reg, queues, facts = clean_inputs()
        queues["alpha"]["errors"] = ["alpha: broken"]
        found = self.findings(reg, queues, {**facts, "branch": "elsewhere"})
        self.assertEqual([f["level"] for f in found], ["error", "warning"])

    def test_a_git_error_skips_the_git_kinds(self) -> None:
        reg, queues, _ = clean_inputs()
        queues["alpha"]["evidence"] = []
        found = self.findings(reg, queues, {"error": "git: not a repository"}, stale_hours=0)
        self.assertEqual(kinds(found), ["stale-claim", "missing-evidence"])
        self.assertEqual(found[0]["actions"], [])


class RepoTestCase(WsTestCase):
    integration = "trunk"

    def setUp(self) -> None:
        super().setUp()
        self.new_ws("alpha", "AL")
        self.folder = self.ws_dir / "alpha"
        (self.folder / "evidence").mkdir()
        (self.folder / "evidence" / "AL-01.md").write_text("# AL-01 evidence\n")
        self.write_queue([
            task("AL-01", 10, status="done", commit=self.git("rev-parse", "HEAD").strip()),
            task("AL-02", 20, status="in-progress", branch="task/al-two",
                 startedAt="2026-10-01T00:00:00Z"),
            task("AL-03", 30, status="todo", branch="task/al-three"),
        ])
        self.commit_all("alpha: create")


class GitFactsTests(RepoTestCase):
    def facts(self) -> dict:
        return snapshot.git_facts(self.project(), [{"id": "alpha"}])

    def test_finds_task_branches_worktrees_and_dirty_tracking_paths(self) -> None:
        self.git("branch", "task/al-three")
        worktree = self.root.parent / "wt-two"
        self.git("worktree", "add", "-q", "-b", "task/al-two", str(worktree))
        (self.folder / "PROGRESS.md").write_text("# edited\n")
        (self.root / "unrelated.txt").write_text("not tracking\n")
        facts = self.facts()
        self.assertEqual(facts["branch"], "trunk")
        self.assertEqual(facts["taskBranches"], ["task/al-three", "task/al-two"])
        self.assertEqual(
            [(Path(w["path"]).resolve(), w["branch"], w["main"]) for w in facts["worktrees"]],
            [(self.root, "trunk", True), (worktree.resolve(), "task/al-two", False)],
        )
        self.assertEqual(facts["dirtyTracking"], ["workstreams/alpha/PROGRESS.md"])

    def test_task_branches_follow_the_configured_pattern(self) -> None:
        self.edit_config('task = "task/{slug}"', 'task = "feature/{slug}"')
        self.git("branch", "task/al-three")
        self.git("branch", "feature/al-four")
        self.assertEqual(self.facts()["taskBranches"], ["feature/al-four"])

    def test_a_git_failure_is_data_not_an_exception(self) -> None:
        outside = self.root.parent / "not-a-repo"
        outside.mkdir()
        project = Project(root=outside, config=CONFIG)
        with mock.patch.dict(os.environ, {"GIT_CEILING_DIRECTORIES": str(self.root.parent)}):
            facts = snapshot.git_facts(project, [])
        self.assertEqual(list(facts), ["error"])
        self.assertIn("rev-parse", facts["error"])
        missing = Project(root=self.root / "missing", config=CONFIG)
        self.assertEqual(list(snapshot.git_facts(missing, [])), ["error"])

    def test_parse_worktrees_marks_the_first_main_and_a_detached_head(self) -> None:
        porcelain = ("worktree /a\nHEAD 1\nbranch refs/heads/trunk\n\n"
                     "worktree /b\nHEAD 2\ndetached\n")
        self.assertEqual(snapshot.parse_worktrees(porcelain), [
            {"path": "/a", "head": "1", "branch": "trunk", "main": True},
            {"path": "/b", "head": "2", "branch": None, "main": False},
        ])


class BuildSnapshotTests(RepoTestCase):
    def build(self, ws_id: str | None = None, **kwargs) -> dict:
        return snapshot.build_snapshot(self.project(), ws_id, now=NOW, **kwargs)

    def test_the_read_model_round_trips_through_json(self) -> None:
        data = self.build("alpha")
        self.assertEqual(json.loads(json.dumps(data)), data)
        self.assertEqual(data["snapshotVersion"], 1)
        self.assertEqual(data["repoRoot"], str(self.root))
        self.assertEqual(data["integrationBranch"], "trunk")
        self.assertEqual([t["id"] for t in data["tasks"]], ["AL-01", "AL-02", "AL-03"])
        self.assertEqual((data["wave"]["state"], data["wave"]["ids"]), ("ready", ["AL-03"]))
        self.assertEqual(data["wave"]["leftovers"], ["AL-02"])
        self.assertEqual(data["git"]["branch"], "trunk")

    def test_revisions_are_sha256_of_the_bytes_on_disk(self) -> None:
        data = self.build()
        self.assertEqual(data["revisions"], {
            "registry": sha256(self.registry.read_bytes()),
            "tasks": {"alpha": sha256((self.folder / "tasks_list.json").read_bytes())},
        })
        self.assertNotIn("tasks", data)

    def test_registry_rows_carry_live_progress(self) -> None:
        row = self.build()["registry"][0]
        self.assertEqual(row["progress"], {"total": 3, "todo": 1, "in-progress": 1,
                                           "blocked": 0, "done": 1, "deferred": 0})
        self.assertTrue(row["progressStale"])

    def test_paths_name_only_files_that_exist(self) -> None:
        (self.folder / "PROGRESS.md").unlink()
        paths = self.build("alpha")["paths"]
        self.assertEqual(paths["plan"], str(self.folder / "PLAN.md"))
        self.assertNotIn("progress", paths)
        self.assertEqual(paths["evidence"], {"AL-01": str(self.folder / "evidence" / "AL-01.md")})

    def test_health_sees_the_stale_claim_and_offers_unclaim(self) -> None:
        self.assertEqual([(f["kind"], f["task"], f["actions"]) for f in self.build()["health"]], [(
            "stale-claim", "AL-02",
            [{"action": "unclaim", "workstream": "alpha", "task": "AL-02"}],
        )])

    def test_validate_problems_become_findings_without_missing_files_noise(self) -> None:
        data = self.queue()
        data["tasks"][2]["files"] = ["src/not-yet.rs"]
        data["tasks"][2]["docs"] = ["docs/missing.md"]
        (self.folder / "tasks_list.json").write_text(json.dumps(data))
        self.git("commit", "-q", "-am", "alpha: break AL-03")
        health = self.build(stale_hours=10_000)["health"]
        self.assertEqual([(f["kind"], f["level"], f["message"]) for f in health], [(
            "invalid", "error", "alpha: AL-03: docs path 'docs/missing.md' does not exist",
        )])

    def test_a_broken_queue_is_a_finding_and_the_rest_still_draws(self) -> None:
        self.new_ws("beta", "BE")
        (self.ws_dir / "beta" / "tasks_list.json").write_text("{broken")
        data = self.build(stale_hours=10_000)
        self.assertIn("not valid JSON", " ".join(f["message"] for f in data["health"]))
        self.assertEqual([r["id"] for r in data["registry"]], ["alpha", "beta"])

    def test_a_malformed_task_is_a_finding_and_the_others_still_draw(self) -> None:
        self.write_queue([task("AL-01", 10, status="todo"),
                          {"title": "no id", "phase": 1, "priority": 20, "status": "todo"}])
        data = self.build("alpha", stale_hours=10_000)
        self.assertEqual([t["id"] for t in data["tasks"]], ["AL-01"])
        self.assertIn("task #2: missing id", " ".join(f["message"] for f in data["health"]))

    def test_a_purged_workstream_keeps_its_recorded_progress(self) -> None:
        self.write_queue([task("AL-01", 10, status="done", commit="abc")])
        self.ok("close", "-w", "alpha", "--purge", "--yes")
        self.commit_all("close")
        row = self.build()["registry"][0]
        self.assertEqual(row["progress"]["done"], 1)
        self.assertFalse(row["progressStale"])

    def test_an_unknown_id_is_refused(self) -> None:
        self.assertIn("no workstream with id 'nope'", self.fails("snapshot", "-w", "nope"))

    def test_the_cli_prints_the_snapshot_as_json(self) -> None:
        data = json.loads(self.ok("snapshot", "-w", "alpha", "--stale-hours", "100000"))
        self.assertEqual((data["snapshotVersion"], data["wave"]["ids"]), (1, ["AL-03"]))
        self.assertEqual(data["health"], [])


if __name__ == "__main__":
    unittest.main()

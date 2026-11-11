"""The published JSON Schemas match what the CLI writes and what the code validates. Any tool
building on `ws` trusts these files, so a drift between them and the code is a broken contract.

The checker below covers the subset of JSON Schema those files use, so the suite stays stdlib
only."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from tests.helpers import WsTestCase, task
from workstream import graph, registry, snapshot, tasks

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schema"
JSON_TYPES = {"string": str, "integer": int, "boolean": bool, "array": list, "object": dict,
              "null": type(None)}


def load_schema(name: str) -> dict:
    return json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text())


def problems(value: object, schema: dict, root: dict, where: str = "$") -> list[str]:
    if "$ref" in schema:
        target = root
        for part in schema["$ref"].removeprefix("#/").split("/"):
            target = target[part]
        return problems(value, target, root, where)
    if "const" in schema and value != schema["const"]:
        return [f"{where}: {value!r} is not {schema['const']!r}"]
    if "enum" in schema and value not in schema["enum"]:
        return [f"{where}: {value!r} not in {schema['enum']}"]
    if "oneOf" in schema:
        if sum(not problems(value, s, root, where) for s in schema["oneOf"]) != 1:
            return [f"{where}: matches no single oneOf branch: {value!r}"]
        return []
    out: list[str] = []
    if "type" in schema:
        kinds = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_is(value, k) for k in kinds):
            return [f"{where}: {value!r} is not {kinds}"]
    if isinstance(value, dict):
        out += [f"{where}: missing {k}" for k in schema.get("required", []) if k not in value]
        props = schema.get("properties", {})
        for key, item in value.items():
            if key in props:
                out += problems(item, props[key], root, f"{where}.{key}")
            elif schema.get("additionalProperties") is False:
                out.append(f"{where}: unexpected key {key}")
    if isinstance(value, list) and "items" in schema:
        for n, item in enumerate(value):
            out += problems(item, schema["items"], root, f"{where}[{n}]")
    return out


def _is(value: object, kind: str) -> bool:
    if kind == "integer" and isinstance(value, bool):
        return False
    return isinstance(value, JSON_TYPES[kind])


class SchemaAgainstCodeTests(unittest.TestCase):
    def test_the_task_schema_names_every_field_the_code_knows(self) -> None:
        props = load_schema("tasks")["$defs"]["task"]["properties"]
        self.assertEqual(set(props), set(tasks.FIELD_TYPES))

    def test_enums_match_the_code(self) -> None:
        schema = load_schema("tasks")
        props = schema["$defs"]["task"]["properties"]
        self.assertEqual(props["status"]["enum"], list(tasks.STATUS_VALUES))
        self.assertEqual(props["mode"]["enum"], list(tasks.MODE_VALUES))
        self.assertEqual(props["releaseImpact"]["enum"][:-1], list(tasks.RELEASE_IMPACT_VALUES))
        self.assertEqual(schema["properties"]["tier"]["enum"], list(tasks.TIERS))
        self.assertEqual(schema["properties"]["schemaVersion"]["const"], tasks.SCHEMA_VERSION)
        reg = load_schema("registry")
        self.assertEqual(reg["$defs"]["workstream"]["properties"]["status"]["enum"],
                         list(registry.STATUS_VALUES))
        snap = load_schema("snapshot")
        self.assertEqual(snap["properties"]["snapshotVersion"]["const"],
                         snapshot.SNAPSHOT_VERSION)
        row = snap["properties"]["registry"]["items"]
        self.assertEqual(row["properties"]["actions"]["items"]["enum"],
                         [*snapshot.ROW_ACTIONS, "sync"])
        self.assertIn("actions", row["required"])
        launch = row["properties"]["launches"]["items"]
        self.assertEqual(launch["properties"]["kind"]["enum"], list(snapshot.LAUNCH_PROMPTS))
        self.assertEqual(launch["properties"]["ask"]["enum"],
                         sorted(set(snapshot.LAUNCH_ASKS.values())))
        self.assertIn("launches", row["required"])
        self.assertEqual(set(snap["properties"]["refresh"]["items"]["properties"]),
                         {"path", "recursive"})
        self.assertIn("refresh", snap["required"])


class LaunchesSchemaTests(unittest.TestCase):
    def snapshot_with(self, launches: list[dict]) -> dict:
        return {"snapshotVersion": snapshot.SNAPSHOT_VERSION, "repoRoot": "/r",
                "integrationBranch": "main",
                "registry": [{"id": "alpha", "status": "active", "progress": {},
                              "progressStale": False, "actions": ["pause"],
                              "launches": launches}],
                "revisions": {"registry": "x", "tasks": {}}, "watch": [], "refresh": [],
                "health": [], "git": {}}

    def test_a_snapshot_with_launches_passes(self) -> None:
        schema = load_schema("snapshot")
        data = self.snapshot_with(snapshot.row_launches("alpha", "active"))
        self.assertEqual(len(data["registry"][0]["launches"]), 4)
        self.assertEqual(problems(data, schema, schema), [])
        self.assertEqual(problems(self.snapshot_with([]), schema, schema), [])

    def test_an_unknown_launch_kind_is_rejected(self) -> None:
        schema = load_schema("snapshot")
        found = problems(self.snapshot_with([{"kind": "chat", "prompt": "hi"}]), schema, schema)
        self.assertTrue(any("'chat' not in" in p for p in found), found)

    def test_a_launch_with_an_extra_key_or_no_prompt_is_rejected(self) -> None:
        schema = load_schema("snapshot")
        self.assertTrue(problems(self.snapshot_with([{"kind": "run", "prompt": "p", "x": 1}]),
                                 schema, schema))
        self.assertTrue(problems(self.snapshot_with([{"kind": "run"}]), schema, schema))


class DetailFactsSchemaTests(unittest.TestCase):
    """unblocks and waitingOn on each task, and scope and baseline under -w."""

    def snapshot_with(self, **extra) -> dict:
        return {"snapshotVersion": snapshot.SNAPSHOT_VERSION, "repoRoot": "/r",
                "integrationBranch": "main", "registry": [],
                "revisions": {"registry": "x", "tasks": {}}, "watch": [], "refresh": [],
                "health": [], "git": {}, **extra}

    @staticmethod
    def a_task(**fields) -> dict:
        return {"id": "AL-01", "phase": 1, "priority": 10, "title": "t", "status": "todo",
                "mode": "background", "unblocks": ["AL-02"], "waitingOn": [], **fields}

    @staticmethod
    def a_key(**fields) -> dict:
        return {"key": "lint", "source": "project", "parser": "regex", "command": "ruff",
                "exit": 1, "findings": 2, "recordedAt": "2026-10-01T00:00:00Z",
                "commit": "c0", **fields}

    def check(self, **extra) -> list[str]:
        schema = load_schema("snapshot")
        return problems(self.snapshot_with(**extra), schema, schema)

    def test_the_new_fields_pass(self) -> None:
        self.assertEqual(self.check(
            tasks=[self.a_task()],
            scope={"inScope": ["src/"], "outOfScope": [], "rule": "r"},
            baseline={"keys": [self.a_key(), self.a_key(key="test", source="workstream",
                                                       exit=None, parser=None)],
                      "errors": []}), [])
        self.assertEqual(self.check(scope=None, baseline={"keys": [], "errors": ["bad"]}), [])

    def test_a_task_needs_both_graph_facts_as_id_lists(self) -> None:
        task_ = self.a_task()
        del task_["waitingOn"]
        self.assertTrue(any("missing waitingOn" in p for p in self.check(tasks=[task_])))
        self.assertTrue(self.check(tasks=[self.a_task(unblocks="AL-02")]))
        self.assertTrue(self.check(tasks=[self.a_task(waitingOn=[1])]))

    def test_scope_and_baseline_are_closed(self) -> None:
        self.assertTrue(self.check(scope={"inScope": [], "extra": 1}))
        self.assertTrue(self.check(scope="src/"))
        self.assertTrue(self.check(baseline={"keys": []}))
        self.assertTrue(self.check(baseline={"keys": [self.a_key(x=1)], "errors": []}))
        self.assertTrue(self.check(baseline={"keys": [self.a_key(source="elsewhere")],
                                             "errors": []}))
        self.assertTrue(self.check(baseline={"keys": [self.a_key(findings=["a"])],
                                             "errors": []}))

    def test_the_schema_requires_what_the_code_always_writes(self) -> None:
        snap = load_schema("snapshot")["properties"]
        self.assertTrue({"unblocks", "waitingOn"} <= set(snap["tasks"]["items"]["required"]))
        self.assertEqual(snap["baseline"]["required"], ["keys", "errors"])
        key = snapshot._baseline_key("lint", {}, "project", {})
        self.assertEqual(set(snap["baseline"]["properties"]["keys"]["items"]["required"]),
                         set(key))


class ChecksTheCheckerTests(unittest.TestCase):
    def test_it_catches_what_it_should(self) -> None:
        schema = {"type": "object", "required": ["a"], "additionalProperties": False,
                  "properties": {"a": {"type": "integer"}}}
        self.assertEqual(problems({"a": 1}, schema, schema), [])
        self.assertTrue(problems({"a": True}, schema, schema))
        self.assertTrue(problems({}, schema, schema))
        self.assertTrue(problems({"a": 1, "b": 2}, schema, schema))


class WrittenFilesTests(WsTestCase):
    """A workstream taken through its whole life; every file and document along the way."""

    def setUp(self) -> None:
        super().setUp()
        self.new_ws("alpha", "AL")
        self.seed_ok([
            task("AL-01", 10, files=["a.py"], acceptance=["x", {"text": "y", "kind": "manual"}]),
            task("AL-02", 20, files=["a.py"], requires=["browser"], blockedBy=["AL-01"]),
            task("AL-03", 30, files=["a.py"]),
        ])
        self.commit_all("alpha: create")

    def assert_valid(self, name: str, value: object) -> None:
        schema = load_schema(name)
        self.assertEqual(problems(value, schema, schema), [], json.dumps(value, indent=1)[:600])

    def assert_all_valid(self) -> None:
        self.assert_valid("tasks", self.queue())
        self.assert_valid("registry", json.loads(self.registry.read_text()))
        self.assert_valid("snapshot", json.loads(self.ok("snapshot")))
        self.assert_valid("snapshot", json.loads(self.ok("snapshot", "-w", "alpha")))

    def test_every_stage_matches_the_published_schemas(self) -> None:
        self.assert_all_valid()
        self.ok("claim", "-w", "alpha", "--by", "me", "AL-01", "AL-03")
        self.ok("sync")
        self.assert_all_valid()
        self.git("branch", "stray-branch")
        self.git("branch", "task/stray")
        self.git("worktree", "add", "-q", str(self.root.parent / "wt"), "task/stray")
        self.assert_all_valid()
        (self.root / "src.txt").write_text("x\n")
        merge = self.commit_all("work")
        self.assert_valid("review", json.loads(self.ok("review", "-w", "alpha", "AL-01")))
        self.assert_valid("review", json.loads(self.ok("review", "-w", "alpha", "AL-01", "--checks")))
        self.assert_valid("review-queue", json.loads(self.ok("review", "--queue")))
        for tid in ("AL-01", "AL-02", "AL-03"):
            self.ok("update", "-w", "alpha", tid, "--status", "done", "--commit", merge)
        self.ok("sync")
        self.assert_all_valid()
        self.assert_valid("review", json.loads(
            self.ok("review", "-w", "alpha", "AL-01", "--file", "src.txt", "--checks")))
        self.assert_valid("review-queue", json.loads(self.ok("review", "--queue")))
        self.ok("close", "-w", "alpha", "--prune", "--yes")
        self.assert_valid("registry", json.loads(self.registry.read_text()))
        self.assert_valid("snapshot", json.loads(self.ok("snapshot")))

    def test_health_findings_stay_inside_the_kinds_the_schema_lists(self) -> None:
        kinds = load_schema("snapshot")["properties"]["health"]["items"]["properties"]["kind"]
        source = (Path(snapshot.__file__)).read_text()
        for kind in kinds["enum"]:
            self.assertIn(f'"{kind}"', source)

    def test_the_wave_exit_codes_stay_documented(self) -> None:
        self.assertEqual((graph.WAVE_READY, graph.WAVE_FINISHED, graph.WAVE_STUCK), (0, 2, 3))


if __name__ == "__main__":
    unittest.main()

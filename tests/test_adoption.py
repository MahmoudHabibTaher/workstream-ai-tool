"""M4's definition of done: `ws init` works on a repository of each stack, including one whose lint
already fails, and a repository can go from nothing to a closed workstream.

Fixture repos use stub tools, so this runs on any machine. Set WS_REAL_TOOLS=1 (`make test-real`)
to also adopt small real projects with whichever toolchains are installed: a stub proves the logic,
and only the real tool proves a profile's commands and patterns.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from tests.test_init import AdoptCase
from workstream.config import parse_config

REPO = Path(__file__).resolve().parent.parent
REAL = os.environ.get("WS_REAL_TOOLS") == "1"

# Markers and stubs for each stack, with the keys adoption should make active.
FIXTURES = {
    "cargo": ({"Cargo.toml": "[package]\n"}, ["cargo"], {"compile", "test", "lint"}),
    "go": ({"go.mod": "module x\n"}, ["go"], {"compile", "test", "lint"}),
    "gradle-kmp": ({"gradlew": "#!/bin/sh\nexit 0\n",
                    "build.gradle.kts": 'plugins { kotlin("multiplatform"); id("detekt") }\n'},
                   [], {"compile", "test", "lint"}),
    "node": ({"package.json": '{"scripts": {"build": "x", "test": "x", "lint": "x"}}',
              "package-lock.json": "{}"}, ["npm"], {"compile", "test", "lint"}),
    "python": ({"pyproject.toml": "[tool.ruff]\n",
                "test_x.py": "import unittest\n\nclass T(unittest.TestCase):\n"
                             "    def test_ok(self):\n        pass\n"}, ["ruff"], {"test", "lint"}),
    "generic": ({"Makefile": "build:\n\ttrue\ntest:\n\ttrue\nlint:\n\ttrue\n"}, [],
                {"compile", "test", "lint"}),
}


class EveryProfileTests(AdoptCase):
    def arrange(self, name: str) -> set[str]:
        files, stubs, expected = FIXTURES[name]
        for filename, text in files.items():
            self.file(filename, text)
        if "gradlew" in files:
            (self.root / "gradlew").chmod(0o755)
        for stub in stubs:
            self.stub(stub, "exit 0")
        self.commit("the project")
        return expected


def _add_profile_tests() -> None:
    def make(name: str):
        def test(self: EveryProfileTests) -> None:
            expected = self.arrange(name)
            out = self.init()
            self.assertIn(f"profile: {name}", out)
            self.assertEqual(set(self.config().commands), expected, out)
            self.commit("adopted")
            self.assertEqual(self.ws("validate")[0], 0)
            code, doctor = self.ws("doctor")
            self.assertEqual(code, 0, doctor)
        return test
    for name in FIXTURES:
        setattr(EveryProfileTests, f"test_{name.replace('-', '_')}_adopts", make(name))


_add_profile_tests()


LINT_DEBT = "src/a.py:1:8: F401 `os` imported but unused"


class FailingLintRepoTests(AdoptCase):
    """The case the plan names: a real repository usually has debt on day one."""

    def adopt(self) -> None:
        self.findings = self.root.parent / "ruff-says.txt"
        self.findings.write_text(LINT_DEBT + "\n")
        self.file("pyproject.toml", "[tool.ruff]\n")
        self.stub("ruff", f"cat {self.findings}; exit 1")
        self.commit("the project")
        self.init()

    def test_it_adopts_with_the_debt_recorded(self) -> None:
        self.adopt()
        self.assertIn("lint", self.config().commands)
        self.assertEqual(self.known()["lint"]["findings"], ["src/a.py | F401 | `os` imported but unused"])

    def test_doctor_run_is_happy_until_something_new_appears(self) -> None:
        self.adopt()
        self.commit("adopted")
        self.assertEqual(self.ws("doctor", "--run")[0], 0)
        self.findings.write_text(LINT_DEBT + "\nsrc/b.py:2:1: E999 mine\n")
        code, out = self.ws("doctor", "--run")
        self.assertEqual(code, 1, out)
        self.assertIn("1 new finding", out)


class FromNothingToClosedTests(AdoptCase):
    """Everything together, as separate processes, with the agent knowing only what it is told."""

    def cli(self, *argv: str, code: int = 0) -> str:
        env = {**os.environ, "PYTHONPATH": f"{REPO}/src:{REPO}"}
        proc = subprocess.run([sys.executable, "-B", "-m", "workstream", *argv], cwd=self.root,
                              capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, code, f"ws {' '.join(argv)}:\n{proc.stdout}{proc.stderr}")
        return proc.stdout

    def agent(self, task_id: str) -> None:
        env = {**os.environ, "PYTHONPATH": f"{REPO}/src:{REPO}"}
        proc = subprocess.run([sys.executable, "-B", "-m", "tests.fake_agent", str(self.root), "demo",
                               task_id], cwd=REPO, capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_a_cargo_repo_with_lint_debt_from_init_to_close(self) -> None:
        self.file("Cargo.toml", "[package]\n")
        self.stub("cargo", 'case "$1" in\nclippy) echo "src/a.rs:1:1: warning: old debt"; exit 1;;\n'
                           "*) exit 0;;\nesac")
        (self.root / ".gitignore").write_text("target/\n")
        self.commit("the project")

        out = self.cli("init")
        self.assertIn("(1 known finding(s) recorded)", out)
        self.commit("adopt ws")
        self.cli("doctor")

        plan = self.root.parent / "plan.md"
        plan.write_text("# Demo: plan\n\n## Context\n\nA demo.\n\n```json ws-tasks\n" + json.dumps({
            "scope": {"rule": "Only src/."},
            "tasks": [{"id": "D-1", "phase": 1, "priority": 10, "title": "first", "kind": "behaviour",
                       "files": ["src/one.txt"], "acceptance": ["it exists"],
                       "verify": ["compile", "test", "lint"]},
                      {"id": "D-2", "phase": 2, "priority": 20, "title": "second", "kind": "behaviour",
                       "files": ["src/two.txt"], "acceptance": ["it exists"], "blockedBy": ["D-1"],
                       "verify": ["compile", "test", "lint"]}]}) + "\n```\n")
        self.cli("new", "demo", "--title", "Demo", "--summary", "A demo.", "--prefix", "D")
        self.cli("seed", "-w", "demo", "--from-plan", str(plan))
        self.cli("validate")
        self.commit("demo: plan")

        for task_id in ("D-1", "D-2"):
            self.cli("claim", "--commit", "-w", "demo", task_id)
            self.cli("worktree", "create", "-w", "demo", task_id)
            self.agent(task_id)
            self.cli("settle", "-w", "demo", task_id)

        self.cli("wave", code=2)
        self.cli("close")
        self.commit("demo: close")
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertEqual(self.ws("doctor", "--run")[0], 0)
        self.assertEqual(self.git("branch", "--list", "task/*"), "")
        rows = json.loads((self.root / "workstreams" / "workstreams.json").read_text())["workstreams"]
        self.assertEqual((rows[0]["status"], rows[0]["progress"]["done"]), ("done", 2))


@unittest.skipUnless(REAL, "set WS_REAL_TOOLS=1 to run real toolchains")
class RealToolTests(AdoptCase):
    def setUp(self) -> None:
        super().setUp()
        self.ignore()

    def ignore(self) -> None:
        self.file(".gitignore", "target/\nbuild/\n.gradle/\nnode_modules/\n__pycache__/\n")

    def active(self, out: str) -> dict:
        return parse_config(tomllib.loads(self.config_text())).commands

    def test_real_cargo_with_a_real_clippy_finding(self) -> None:
        if not shutil.which("cargo"):
            self.skipTest("no cargo")
        self.file("Cargo.toml", '[package]\nname = "x"\nversion = "0.1.0"\nedition = "2021"\n')
        (self.root / "src").mkdir()
        self.file("src/main.rs", "fn main() {\n    let unused = 1;\n}\n")
        self.commit("the project")
        out = self.init()
        print("\n" + out)
        self.assertEqual(self.active(out)["compile"], "cargo check --all-targets")
        self.assertIn("test", self.active(out))
        self.assertIn("the commands left new files: Cargo.lock", out)
        if "lint" in self.active(out):
            findings = self.known()["lint"]["findings"]
            self.assertTrue(any("src/main.rs" in f and "unused" in f for f in findings), findings)
            self.assertFalse([f for f in findings if ":2:" in f], "a line number got in")

    def test_real_npm(self) -> None:
        if not shutil.which("npm"):
            self.skipTest("no npm")
        self.file("package.json", json.dumps({
            "name": "x", "version": "1.0.0",
            "scripts": {"test": "node -e \"process.exit(0)\"",
                        "lint": "node -e \"console.log('src/a.js:3:5: bad [Error/x]');process.exit(1)\""}}))
        self.commit("the project")
        out = self.init()
        print("\n" + out)
        self.assertEqual(self.active(out)["test"], "npm test")
        self.assertEqual(self.active(out)["lint"], "npm run lint")
        self.assertEqual(self.known()["lint"]["findings"], ["src/a.js | bad [Error/x]"])

    def test_a_real_default_npm_test_script_stays_off(self) -> None:
        if not shutil.which("npm"):
            self.skipTest("no npm")
        self.file("package.json", json.dumps({
            "name": "x", "version": "1.0.0",
            "scripts": {"test": "echo \"Error: no test specified\" && exit 1"}}))
        self.commit("the project")
        out = self.init()
        print("\n" + out)
        self.assertNotIn("test", self.active(out))
        self.assertIn('# test = "npm test"', self.config_text())

    def test_real_gradle(self) -> None:
        if not shutil.which("gradle"):
            self.skipTest("no gradle")
        self.file("settings.gradle.kts", 'rootProject.name = "x"\n')
        self.file("build.gradle.kts", 'plugins { base }\n')
        self.commit("the project")
        with mock.patch.dict(os.environ, {"GRADLE_USER_HOME": str(Path.home() / ".gradle")}):
            out = self.init()
        print("\n" + out)
        self.assertEqual(self.active(out)["compile"], "gradle assemble --console=plain")
        # `base` has no test task, so the real gradle refuses it and it stays off.
        self.assertIn("gradle test --console=plain", self.config_text())

    def test_real_python_unittest(self) -> None:
        self.file("pyproject.toml", "[project]\nname = \"x\"\n")
        self.file("test_x.py", "import unittest\n\nclass T(unittest.TestCase):\n"
                               "    def test_ok(self):\n        pass\n")
        self.commit("the project")
        out = self.init()
        print("\n" + out)
        self.assertEqual(self.active(out)["test"], "python3 -m unittest discover")


if __name__ == "__main__":
    unittest.main()

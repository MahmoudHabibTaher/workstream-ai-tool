"""What every test shares: a throwaway git repository with no global or system git config,
and the CLI run in-process so exit codes and printed output are what a shell sees."""

from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from workstream import tasks
from workstream.cli import main
from workstream.config import CONFIG_REL
from workstream.project import open_project

GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "ws test",
    "GIT_AUTHOR_EMAIL": "ws@example.invalid",
    "GIT_COMMITTER_NAME": "ws test",
    "GIT_COMMITTER_EMAIL": "ws@example.invalid",
}


def task(task_id: str, priority: int, **fields) -> dict:
    """A minimal seedable task; every other field reads as its default."""
    return {"id": task_id, "phase": fields.pop("phase", 1), "priority": priority,
            "title": f"title of {task_id}", **fields}


class WsTestCase(unittest.TestCase):
    """A temp repository on `integration`, set up with `ws init` and one first commit."""

    integration = "main"

    def setUp(self) -> None:
        env = mock.patch.dict(os.environ, GIT_ENV)
        env.start()
        self.addCleanup(env.stop)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve() / "repo"
        self.root.mkdir()
        self.git("init", "-q", "-b", self.integration)
        code, out, err = self.ws("init", "--integration", self.integration)
        self.assertEqual(code, 0, err)
        self.ws_dir = self.root / "workstreams"
        self.registry = self.ws_dir / "workstreams.json"
        self.commit_all("init")

    # --- running things -------------------------------------------------------------------

    def ws(self, *argv: str) -> tuple[int, str, str]:
        """`ws <argv>` at this repo, in-process: (exit code, stdout, stderr)."""
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                code = main(["--root", str(self.root), *argv])
            except SystemExit as e:  # argparse rejecting the arguments
                code = e.code if isinstance(e.code, int) else 1
        return code, out.getvalue(), err.getvalue()

    def ok(self, *argv: str) -> str:
        code, out, err = self.ws(*argv)
        self.assertEqual(code, 0, out + err)
        return out

    def fails(self, *argv: str) -> str:
        """Runs a command that must exit 1; returns everything it printed."""
        code, out, err = self.ws(*argv)
        self.assertEqual(code, 1, out + err)
        return out + err

    def git(self, *argv: str, check: bool = True) -> str:
        proc = subprocess.run(["git", *argv], cwd=self.root, capture_output=True, text=True,
                              check=check)
        return proc.stdout

    def commit_all(self, message: str) -> str:
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", message)
        return self.git("rev-parse", "--short", "HEAD").strip()

    # --- arranging the tree ---------------------------------------------------------------

    def project(self):
        return open_project(self.root)

    def append_config(self, toml: str) -> None:
        path = self.root / CONFIG_REL
        path.write_text(path.read_text() + "\n" + toml + "\n")

    def edit_config(self, old: str, new: str) -> None:
        """Replace text in the default config, whose tables already exist."""
        path = self.root / CONFIG_REL
        self.assertIn(old, path.read_text())
        path.write_text(path.read_text().replace(old, new))

    def set_commands(self, **commands: str) -> None:
        lines = "".join(f'{k} = "{v}"\n' for k, v in commands.items())
        self.edit_config("[commands]\n", f"[commands]\n{lines}")

    def new_ws(self, ws_id: str = "alpha", prefix: str | None = None, *extra: str) -> Path:
        """A registered workstream with its templates filled in, so `validate` only reports
        what a test arranged. Returns its queue path."""
        argv = ["new", ws_id, "--title", f"{ws_id} title", "--summary", "s", "--base", "abc1234"]
        self.ok(*argv, *(["--prefix", prefix] if prefix else []), *extra)
        folder = self.ws_dir / ws_id
        for path in folder.glob("*.md"):
            path.write_text(f"# {path.name}\n")
        return folder / "tasks_list.json"

    def seed(self, tasks_: list[dict], ws_id: str = "alpha") -> tuple[int, str, str]:
        seed_file = self.root.parent / "seed.json"
        seed_file.write_text(json.dumps(tasks_))
        return self.ws("seed", "-w", ws_id, str(seed_file))

    def seed_ok(self, tasks_: list[dict], ws_id: str = "alpha") -> None:
        code, out, err = self.seed(tasks_, ws_id)
        self.assertEqual(code, 0, out + err)

    def write_queue(self, tasks_: list[dict], ws_id: str = "alpha") -> Path:
        """Put tasks straight on disk, past the CLI's checks: what `validate` is there for."""
        path = self.ws_dir / ws_id / "tasks_list.json"
        data = json.loads(path.read_text())
        data["tasks"] = tasks_
        tasks.save(path, data)
        return path

    def queue(self, ws_id: str = "alpha") -> dict:
        return json.loads((self.ws_dir / ws_id / "tasks_list.json").read_text())

    def by_id(self, task_id: str, ws_id: str = "alpha") -> dict:
        return next(t for t in self.queue(ws_id)["tasks"] if t["id"] == task_id)

    def entry(self, ws_id: str = "alpha") -> dict:
        rows = json.loads(self.registry.read_text())["workstreams"]
        return next(w for w in rows if w["id"] == ws_id)

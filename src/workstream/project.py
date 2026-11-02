"""Where a project's files are. Every module takes a Project rather than reading a global,
so the code under test and the code in production can't disagree about the paths."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from workstream import gitutil
from workstream.config import CONFIG_REL, Config, load_config, render_default
from workstream.errors import WsError

REGISTRY_NAME = "workstreams.json"
TASKS_NAME = "tasks_list.json"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


@dataclass(frozen=True)
class Project:
    root: Path
    config: Config

    @property
    def workstreams_dir(self) -> Path:
        return self.root / self.config.workstreams_dir

    @property
    def registry_path(self) -> Path:
        return self.workstreams_dir / REGISTRY_NAME

    def folder(self, entry: dict) -> Path:
        """A workstream's folder: its registry `path`, or the default one under workstreams/.

        The registry is a file in the repo, and `close --purge` deletes this folder, so a path
        that leaves the repository is refused rather than trusted.
        """
        if entry.get("path"):
            return self.inside(entry["path"])
        return self.workstreams_dir / entry["id"]

    def inside(self, rel: str) -> Path:
        """root/rel, or a WsError if that isn't strictly inside the repository."""
        path = self.root / rel
        resolved = path.resolve()
        root = self.root.resolve()
        if resolved == root or root not in resolved.parents:
            raise WsError(f"path {rel!r} is outside the repository")
        return path

    def tasks_path(self, entry: dict) -> Path:
        return self.folder(entry) / TASKS_NAME

    def rel(self, path: Path) -> str:
        return str(Path(path).resolve().relative_to(self.root.resolve()))


def find_root(start: Path) -> Path | None:
    """The nearest ancestor of start holding a config, or None."""
    start = start.resolve()
    for candidate in (start, *start.parents):
        if (candidate / CONFIG_REL).is_file():
            return candidate
    return None


def open_project(root: Path | None = None, start: Path | None = None) -> Project:
    """The Project at root, or found by walking up from start (default: the working dir)."""
    if root is not None:
        root = Path(root).resolve()
        if not (root / CONFIG_REL).is_file():
            raise WsError(f"{root} has no {CONFIG_REL} (run `ws init` there)")
    else:
        start = Path(start) if start else Path.cwd()
        root = find_root(start)
        if root is None:
            raise WsError(f"no {CONFIG_REL} here or in any parent (run `ws init`)")
    return Project(root=root, config=load_config(root / CONFIG_REL))


def init_project(root: Path, integration: str | None = None) -> tuple[Project, list[str]]:
    """Write a default config and an empty registry where they don't exist yet.

    Returns the project and what was created. Existing files are left alone, so running it
    twice is safe.
    """
    root = Path(root).resolve()
    created = []
    config_path = root / CONFIG_REL
    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        branch = integration or gitutil.default_branch(root)
        config_path.write_text(render_default(branch))
        created.append(CONFIG_REL)
    project = Project(root=root, config=load_config(config_path))
    if not project.registry_path.exists():
        from workstream import registry  # registry imports this module

        project.workstreams_dir.mkdir(parents=True, exist_ok=True)
        registry.save(project, registry.new_registry())
        created.append(project.rel(project.registry_path))
    return project, created

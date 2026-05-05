from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import tomllib

from psk.setup import SetupConfig, parse_setup_config

CONFIG_DIR = Path.home() / ".config" / "psk" / "projects"


@dataclass(frozen=True)
class ProjectConfig:
    name: str
    code_repo: Path
    notes_repo: Path
    github_repo: str
    linear_workspace_url: str
    branch_owner: str = "pablo"
    journals_dir: str = "journals"
    workspace_code_label: str | None = None
    workspace_notes_label: str | None = None
    worktrees_dir: Path | None = None
    match_paths: tuple[Path, ...] = field(default_factory=tuple)
    setup: SetupConfig = field(default_factory=SetupConfig)

    def get_worktrees_dir(self) -> Path:
        """Return the configured worktrees directory, or derive it from code_repo."""
        if self.worktrees_dir is not None:
            return self.worktrees_dir
        return self.code_repo.parent / f"{self.code_repo.name}-worktrees"

    @property
    def project_yaml(self) -> Path:
        return self.notes_repo / "project.yaml"

    @property
    def code_label(self) -> str:
        return self.workspace_code_label or f"⚙️ {self.code_repo.name}"

    @property
    def notes_label(self) -> str:
        return self.workspace_notes_label or f"📓 {self.notes_repo.name}"

    def matches_path(self, path: Path) -> bool:
        target = path if path.is_dir() else path.parent
        candidates = (self.code_repo, self.notes_repo, self.get_worktrees_dir(), *self.match_paths)
        return any(target == c or target.is_relative_to(c) for c in candidates)


def _expand_path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def _load_project_file(path: Path) -> ProjectConfig:
    data = tomllib.loads(path.read_text())
    name = data.get("name", path.stem)
    raw_worktrees_dir = data.get("worktrees_dir")
    raw_match_paths = data.get("match_paths", [])
    return ProjectConfig(
        name=name,
        code_repo=_expand_path(data["code_repo"]),
        notes_repo=_expand_path(data["notes_repo"]),
        github_repo=data["github_repo"],
        linear_workspace_url=data["linear_workspace_url"].rstrip("/"),
        branch_owner=data.get("branch_owner", "pablo"),
        journals_dir=data.get("journals_dir", "journals"),
        workspace_code_label=data.get("workspace_code_label"),
        workspace_notes_label=data.get("workspace_notes_label"),
        worktrees_dir=_expand_path(raw_worktrees_dir) if raw_worktrees_dir else None,
        match_paths=tuple(_expand_path(p) for p in raw_match_paths),
        setup=parse_setup_config(data),
    )


def list_projects() -> dict[str, ProjectConfig]:
    projects: dict[str, ProjectConfig] = {}
    if CONFIG_DIR.is_dir():
        for path in sorted(CONFIG_DIR.glob("*.toml")):
            project = _load_project_file(path)
            projects[project.name] = project
    return projects


def resolve_project(
    project_name: str | None = None, cwd: Path | None = None
) -> ProjectConfig:
    projects = list_projects()

    if not projects:
        raise ValueError(
            f"No projects configured. Create a TOML file under {CONFIG_DIR}."
        )

    if project_name:
        try:
            return projects[project_name]
        except KeyError as exc:
            known = ", ".join(sorted(projects))
            raise ValueError(
                f"Unknown project '{project_name}'. Known: {known}"
            ) from exc

    target = (cwd or Path.cwd()).resolve()
    matches = [project for project in projects.values() if project.matches_path(target)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        names = ", ".join(sorted(project.name for project in matches))
        raise ValueError(
            f"Ambiguous project for {target}. Matches: {names}. Use --project."
        )

    current = target if target.is_dir() else target.parent
    for parent in (current, *current.parents):
        project_yaml = parent / "project.yaml"
        if not project_yaml.is_file():
            continue
        yaml_matches = [
            project
            for project in projects.values()
            if project.project_yaml == project_yaml
        ]
        if len(yaml_matches) == 1:
            return yaml_matches[0]
        break

    raise ValueError(f"Could not infer project from {target}. Use --project.")

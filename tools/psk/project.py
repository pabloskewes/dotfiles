from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

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
    backend_setup_command: tuple[str, ...] | None = ("uv", "sync")
    frontend_setup_command: tuple[str, ...] | None = ("pnpm", "install")
    frontend_dirname: str = "frontend"
    frontend_env_source_candidates: tuple[Path, ...] = ()
    local_cursor_rule_source: Path | None = None

    @property
    def worktrees_dir(self) -> Path:
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
        for candidate in (self.code_repo, self.notes_repo, self.worktrees_dir):
            if target == candidate or target.is_relative_to(candidate):
                return True
        return False

def _expand_path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def _optional_command(value: object) -> tuple[str, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("setup commands must be string arrays")
    return tuple(value)


def _optional_paths(value: object) -> tuple[Path, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("path candidates must be string arrays")
    return tuple(_expand_path(item) for item in value)


def _load_project_file(path: Path) -> ProjectConfig:
    data = tomllib.loads(path.read_text())
    name = data.get("name", path.stem)
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
        backend_setup_command=_optional_command(data.get("backend_setup_command", ["uv", "sync"])),
        frontend_setup_command=_optional_command(data.get("frontend_setup_command", ["pnpm", "install"])),
        frontend_dirname=data.get("frontend_dirname", "frontend"),
        frontend_env_source_candidates=_optional_paths(data.get("frontend_env_source_candidates")),
        local_cursor_rule_source=(
            _expand_path(data["local_cursor_rule_source"])
            if data.get("local_cursor_rule_source")
            else None
        ),
    )


def list_projects() -> dict[str, ProjectConfig]:
    projects: dict[str, ProjectConfig] = {}
    if CONFIG_DIR.is_dir():
        for path in sorted(CONFIG_DIR.glob("*.toml")):
            project = _load_project_file(path)
            projects[project.name] = project
    return projects


def resolve_project(project_name: str | None = None, cwd: Path | None = None) -> ProjectConfig:
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
            raise ValueError(f"Unknown project '{project_name}'. Known: {known}") from exc

    target = (cwd or Path.cwd()).resolve()
    matches = [project for project in projects.values() if project.matches_path(target)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        names = ", ".join(sorted(project.name for project in matches))
        raise ValueError(f"Ambiguous project for {target}. Matches: {names}. Use --project.")

    current = target if target.is_dir() else target.parent
    for parent in (current, *current.parents):
        project_yaml = parent / "project.yaml"
        if not project_yaml.is_file():
            continue
        yaml_matches = [
            project for project in projects.values() if project.project_yaml == project_yaml
        ]
        if len(yaml_matches) == 1:
            return yaml_matches[0]
        break

    raise ValueError(f"Could not infer project from {target}. Use --project.")

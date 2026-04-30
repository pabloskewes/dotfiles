from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Iterable
from contextlib import chdir
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from psk.project import ProjectConfig
from psk.worktree import ENV_FILES, create_worktree, symlink_env_files


@dataclass
class TicketParts:
    project: str
    number: int
    slug: str
    ticket_id: str


@dataclass
class InitPlan:
    ticket_id: str
    branch: str
    journal_folder: str
    repo: Path
    worktree: Path
    notes_repo: Path
    journal_dir: Path
    workspace_file: Path
    project: ProjectConfig | None = None


@dataclass
class ActiveTicket:
    ticket_id: str
    slug: str


def parse_ticket(ticket_or_url: str) -> tuple[str, int]:
    match = re.search(r"([A-Za-z]+)-(\d+)", ticket_or_url)
    if not match:
        raise ValueError("Ticket must look like DRA-1049 or contain it in the URL")
    return match.group(1).upper(), int(match.group(2))


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    if not cleaned:
        raise ValueError("Slug cannot be empty")
    return cleaned


def build_ticket_parts(ticket_or_url: str, slug: str) -> TicketParts:
    project, number = parse_ticket(ticket_or_url)
    normalized_slug = slugify(slug)
    return TicketParts(
        project=project,
        number=number,
        slug=normalized_slug,
        ticket_id=f"{project}-{number}",
    )


def build_branch_name(parts: TicketParts, owner: str = "pablo") -> str:
    return f"{owner}/{parts.project.lower()}-{parts.number}-{parts.slug}"


def build_journal_folder(parts: TicketParts) -> str:
    return f"{parts.number:04d}-{parts.slug}"


def resolve_worktree_path_for_repo(repo_root: Path, branch: str) -> Path:
    return repo_root.parent / f"{repo_root.name}-worktrees" / branch.replace("/", "-")


def build_init_plan(
    project: ProjectConfig,
    ticket_or_url: str,
    slug: str,
    *,
    branch: str | None = None,
    journal_folder: str | None = None,
    workspace_file: str | None = None,
) -> InitPlan:
    parts = build_ticket_parts(ticket_or_url, slug)
    resolved_branch = branch or build_branch_name(parts, owner=project.branch_owner)
    resolved_journal_folder = journal_folder or build_journal_folder(parts)
    journal_dir = project.notes_repo / project.journals_dir / resolved_journal_folder
    worktree = resolve_worktree_path_for_repo(project.code_repo, resolved_branch)
    resolved_workspace_file = (
        Path(workspace_file)
        if workspace_file
        else journal_dir / f"{resolved_journal_folder}.code-workspace"
    )

    return InitPlan(
        ticket_id=parts.ticket_id,
        branch=resolved_branch,
        journal_folder=resolved_journal_folder,
        repo=project.code_repo,
        worktree=worktree,
        notes_repo=project.notes_repo,
        journal_dir=journal_dir,
        workspace_file=resolved_workspace_file,
        project=project,
    )


def render_summary(plan: InitPlan) -> str:
    rows = [
        ("ticket_id", plan.ticket_id),
        ("branch", plan.branch),
        ("repo", str(plan.repo)),
        ("worktree", str(plan.worktree)),
        ("journal_folder", plan.journal_folder),
        ("workspace_file", str(plan.workspace_file)),
    ]
    width = max(len(label) for label, _ in rows)
    return "\n".join(f"  {label:<{width}} : {value}" for label, value in rows)


def _project_for_plan(plan: InitPlan) -> ProjectConfig:
    if plan.project is None:
        raise ValueError("InitPlan.project is required for generic ticket operations")
    return plan.project


def _build_readme_content(plan: InitPlan) -> str:
    started = date.today().isoformat()
    project = _project_for_plan(plan)
    linear_url = project.linear_workspace_url.rstrip("/")
    lines = [
        "---",
        "type: journal",
        'ai: "AI Assisted"',
        "linear:",
        f'  id: "{plan.ticket_id}"',
        f'  url: "{linear_url}/issue/{plan.ticket_id}"',
        '  status: "in_progress"',
        f"started: {started}",
        'status: "active"',
        "repos:",
        f'  - repo: "{project.github_repo}"',
        "    branches:",
        f"      - {plan.branch}",
        "prs: []",
        "tags: []",
        f"updated: {started}",
        "---",
        "",
        f"# {plan.ticket_id} — {plan.journal_folder}",
        "",
    ]
    return "\n".join(lines)


def _build_workspace_payload(plan: InitPlan) -> dict:
    project = _project_for_plan(plan)
    folders = [
        {"path": str(plan.worktree), "name": project.code_label},
        {"path": str(plan.notes_repo), "name": project.notes_label},
    ]
    return {
        "folders": folders,
        "settings": {
            "task.allowAutomaticTasks": "off",
        },
    }


def _ensure_parent_dirs(paths: Iterable[Path]) -> None:
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)


def _write_text_if_missing(path: Path, content: str) -> None:
    if not path.exists():
        path.write_text(content)


def list_active_tickets(repo: Path) -> list[ActiveTicket]:
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
        cwd=repo,
    )
    names = {
        Path(line[len("worktree ") :]).name
        for line in result.stdout.splitlines()
        if line.startswith("worktree ")
    }

    tickets = []
    for name in names:
        match = re.search(r"-([a-z]+)-(\d+)-(.+)", name)
        if not match:
            continue
        ticket_id = f"{match.group(1).upper()}-{match.group(2)}"
        tickets.append(ActiveTicket(ticket_id=ticket_id, slug=match.group(3)))

    tickets.sort(key=lambda ticket: ticket.ticket_id)
    return tickets


def find_workspace_for_ticket(
    worktree_path: Path,
    notes_repo: Path,
    journals_dir: str = "journals",
) -> Path | None:
    match = re.search(r"-([a-z]+)-(\d+)-(.+)", worktree_path.name)
    if not match:
        return None
    number = int(match.group(2))
    slug = match.group(3)
    journal_folder = f"{number:04d}-{slug}"
    workspace = notes_repo / journals_dir / journal_folder / f"{journal_folder}.code-workspace"
    return workspace if workspace.exists() else None


def find_worktree_for_ticket(repo: Path, ticket_id: str) -> Path | None:
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
        cwd=repo,
    )
    number = ticket_id.split("-")[-1]
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            path = Path(line[len("worktree ") :])
            if f"-{number}-" in path.name or path.name.endswith(f"-{number}"):
                return path
    return None


def _branch_exists(repo: Path, branch: str) -> bool:
    result = subprocess.run(
        ["git", "branch", "--list", branch],
        capture_output=True,
        text=True,
        cwd=repo,
    )
    return bool(result.stdout.strip())


def _run_setup(worktree: Path, cmd: list[str]) -> None:
    print(f"running {' '.join(cmd)} in {worktree.name}...")
    result = subprocess.run(cmd, cwd=worktree)
    if result.returncode != 0:
        print(f"⚠️  {cmd[0]} exited with code {result.returncode} — continuing anyway")


def _frontend_has_env(frontend_dir: Path) -> bool:
    return any((frontend_dir / filename).exists() or (frontend_dir / filename).is_symlink() for filename in ENV_FILES)


def _prepare_frontend_env(project: ProjectConfig, worktree: Path) -> None:
    frontend_dir = worktree / project.frontend_dirname
    if not frontend_dir.is_dir() or _frontend_has_env(frontend_dir):
        return

    candidates = project.frontend_env_source_candidates or (
        project.code_repo / project.frontend_dirname,
    )

    for source_dir in candidates:
        if not source_dir.is_dir():
            continue
        symlink_env_files(
            source_dir,
            frontend_dir,
            display_prefix=f"{project.frontend_dirname}/",
        )
        if _frontend_has_env(frontend_dir):
            return


def _prepare_frontend_dependencies(project: ProjectConfig, worktree: Path) -> None:
    if project.frontend_setup_command is None:
        return
    frontend_dir = worktree / project.frontend_dirname
    if not (frontend_dir / "package.json").is_file():
        return
    if (frontend_dir / "node_modules").exists():
        return
    _run_setup(frontend_dir, list(project.frontend_setup_command))


def _install_local_cursor_rule(project: ProjectConfig, worktree: Path) -> None:
    source = project.local_cursor_rule_source
    if source is None or not source.is_file():
        return

    destination = worktree / ".cursor" / "rules" / source.name
    if destination.exists() or destination.is_symlink():
        return

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.symlink_to(source)
    print(f"symlinked .cursor/rules/{source.name}")


def init_ticket(plan: InitPlan) -> None:
    project = _project_for_plan(plan)
    if not plan.worktree.exists():
        with chdir(plan.repo):
            create_worktree(
                plan.branch,
                plan.worktree,
                new_branch=not _branch_exists(plan.repo, plan.branch),
            )
        if project.backend_setup_command is not None:
            _run_setup(plan.worktree, list(project.backend_setup_command))

    _prepare_frontend_env(project, plan.worktree)
    _prepare_frontend_dependencies(project, plan.worktree)
    _install_local_cursor_rule(project, plan.worktree)

    plan.journal_dir.mkdir(parents=True, exist_ok=True)
    _ensure_parent_dirs(
        [
            plan.workspace_file,
            plan.journal_dir / "README.md",
            plan.journal_dir / "00-plan.md",
        ]
    )

    _write_text_if_missing(plan.journal_dir / "README.md", _build_readme_content(plan))
    _write_text_if_missing(plan.journal_dir / "00-plan.md", "")
    _write_text_if_missing(
        plan.workspace_file,
        json.dumps(_build_workspace_payload(plan), indent=2) + "\n",
    )

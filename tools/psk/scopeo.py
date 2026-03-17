import json
import re
import subprocess
from collections.abc import Iterable
from contextlib import chdir
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from psk.worktree import create_worktree

SCOPEO_ROOT = Path.home() / "Scopeo"
BACKEND_REPO = "draftnrun"
FRONTEND_REPO = "back-office"
NOTES_REPO = "scopeo-notes"
JOURNALS_DIR = "journals"


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
    backend_repo: Path
    backend_worktree: Path
    frontend_repo: Path | None
    frontend_worktree: Path | None
    notes_repo: Path
    journal_dir: Path
    workspace_file: Path


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


def resolve_repo(scopeo_root: Path, repo_name: str) -> Path:
    repo_path = scopeo_root / repo_name
    if not repo_path.is_dir():
        raise ValueError(f"Repo not found: {repo_path}")
    return repo_path


def build_branch_name(parts: TicketParts, owner: str = "pablo") -> str:
    return f"{owner}/{parts.project.lower()}-{parts.number}-{parts.slug}"


def build_journal_folder(parts: TicketParts) -> str:
    return f"{parts.number:04d}-{parts.slug}"


def resolve_worktree_path_for_repo(repo_root: Path, branch: str) -> Path:
    worktrees_dir = repo_root.parent / f"{repo_root.name}-worktrees"
    return worktrees_dir / branch.replace("/", "-")


def build_init_plan(
    ticket_or_url: str,
    slug: str,
    *,
    with_frontend: bool = False,
    branch: str | None = None,
    journal_folder: str | None = None,
    workspace_file: str | None = None,
) -> InitPlan:
    parts = build_ticket_parts(ticket_or_url, slug)
    scopeo_root = SCOPEO_ROOT
    backend_repo = resolve_repo(scopeo_root, BACKEND_REPO)
    frontend_repo = resolve_repo(scopeo_root, FRONTEND_REPO) if with_frontend else None
    notes_repo = resolve_repo(scopeo_root, NOTES_REPO)

    resolved_branch = branch or build_branch_name(parts)
    resolved_journal_folder = journal_folder or build_journal_folder(parts)
    journal_dir = notes_repo / JOURNALS_DIR / resolved_journal_folder

    backend_worktree = resolve_worktree_path_for_repo(backend_repo, resolved_branch)
    frontend_worktree = (
        resolve_worktree_path_for_repo(frontend_repo, resolved_branch)
        if frontend_repo
        else None
    )
    resolved_workspace_file = (
        Path(workspace_file)
        if workspace_file
        else journal_dir / f"{resolved_journal_folder}.code-workspace"
    )

    return InitPlan(
        ticket_id=parts.ticket_id,
        branch=resolved_branch,
        journal_folder=resolved_journal_folder,
        backend_repo=backend_repo,
        backend_worktree=backend_worktree,
        frontend_repo=frontend_repo,
        frontend_worktree=frontend_worktree,
        notes_repo=notes_repo,
        journal_dir=journal_dir,
        workspace_file=resolved_workspace_file,
    )


def render_summary(plan: InitPlan) -> str:
    rows = [
        ("ticket_id", plan.ticket_id),
        ("branch", plan.branch),
        ("backend_repo", str(plan.backend_repo)),
        ("backend_worktree", str(plan.backend_worktree)),
        ("frontend_repo", str(plan.frontend_repo) if plan.frontend_repo else "-"),
        (
            "frontend_worktree",
            str(plan.frontend_worktree) if plan.frontend_worktree else "-",
        ),
        ("journal_folder", plan.journal_folder),
        ("workspace_file", str(plan.workspace_file)),
    ]
    width = max(len(label) for label, _ in rows)
    return "\n".join(f"  {label:<{width}} : {value}" for label, value in rows)


def _build_readme_content(plan: InitPlan) -> str:
    started = date.today().isoformat()
    lines = [
        "---",
        "type: journal",
        'ai: "AI Assisted"',
        "linear:",
        f'  id: "{plan.ticket_id}"',
        f'  url: "https://linear.app/draftnrun/issue/{plan.ticket_id}"',
        '  status: "in_progress"',
        f"started: {started}",
        'status: "active"',
        "repos:",
        f'  - repo: "Scopeo/{plan.backend_repo.name}"',
        "    branches:",
        f"      - {plan.branch}",
    ]
    if plan.frontend_repo:
        lines.extend(
            [
                f'  - repo: "Scopeo/{plan.frontend_repo.name}"',
                "    branches:",
                f"      - {plan.branch}",
            ]
        )
    lines.extend(
        [
            "prs: []",
            "tags: []",
            f"updated: {started}",
            "---",
            "",
            f"# {plan.ticket_id} — {plan.journal_folder}",
            "",
        ]
    )
    return "\n".join(lines)


def _build_workspace_payload(plan: InitPlan) -> dict:
    folders = [
        {"path": str(plan.backend_worktree), "name": f"⚙️ {plan.backend_repo.name}"}
    ]
    if plan.frontend_worktree and plan.frontend_repo:
        folders.append(
            {
                "path": str(plan.frontend_worktree),
                "name": f"🖥️ {plan.frontend_repo.name}",
            }
        )
    folders.append({"path": str(plan.notes_repo), "name": "📓 scopeo-notes"})
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


def init_scopeo_ticket(plan: InitPlan) -> None:
    if not plan.backend_worktree.exists():
        with chdir(plan.backend_repo):
            create_worktree(
                plan.branch,
                plan.backend_worktree,
                new_branch=not _branch_exists(plan.backend_repo, plan.branch),
            )
        _run_setup(plan.backend_worktree, ["uv", "sync"])

    if (
        plan.frontend_repo
        and plan.frontend_worktree
        and not plan.frontend_worktree.exists()
    ):
        with chdir(plan.frontend_repo):
            create_worktree(
                plan.branch,
                plan.frontend_worktree,
                new_branch=not _branch_exists(plan.frontend_repo, plan.branch),
            )
        _run_setup(plan.frontend_worktree, ["npm", "install"])

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

import json
import re
import subprocess
from collections.abc import Iterable
from contextlib import chdir
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from psk.worktree import ENV_FILES, FRONTEND_DIRNAME, create_worktree, symlink_env_files

SCOPEO_ROOT = Path.home() / "Scopeo"
MONOREPO_REPO = "draftnrun"
BACKEND_REPO = MONOREPO_REPO
NOTES_REPO = "scopeo-notes"
JOURNALS_DIR = "journals"
LEGACY_FRONTEND_REPO = "back-office"
LOCAL_CURSOR_RULES_DIR = SCOPEO_ROOT / NOTES_REPO / "cursor-rules"
LOCAL_PERSONAL_RULE = "local-personal.mdc"


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
    branch: str | None = None,
    journal_folder: str | None = None,
    workspace_file: str | None = None,
) -> InitPlan:
    parts = build_ticket_parts(ticket_or_url, slug)
    scopeo_root = SCOPEO_ROOT
    repo = resolve_repo(scopeo_root, MONOREPO_REPO)
    notes_repo = resolve_repo(scopeo_root, NOTES_REPO)

    resolved_branch = branch or build_branch_name(parts)
    resolved_journal_folder = journal_folder or build_journal_folder(parts)
    journal_dir = notes_repo / JOURNALS_DIR / resolved_journal_folder
    worktree = resolve_worktree_path_for_repo(repo, resolved_branch)
    resolved_workspace_file = (
        Path(workspace_file)
        if workspace_file
        else journal_dir / f"{resolved_journal_folder}.code-workspace"
    )

    return InitPlan(
        ticket_id=parts.ticket_id,
        branch=resolved_branch,
        journal_folder=resolved_journal_folder,
        repo=repo,
        worktree=worktree,
        notes_repo=notes_repo,
        journal_dir=journal_dir,
        workspace_file=resolved_workspace_file,
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
        f'  - repo: "Scopeo/{plan.repo.name}"',
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
    folders = [
        {"path": str(plan.worktree), "name": f"⚙️ {plan.repo.name}"},
        {"path": str(plan.notes_repo), "name": "📓 scopeo-notes"},
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


@dataclass
class ActiveTicket:
    ticket_id: str
    slug: str


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


def find_workspace_for_ticket(worktree_path: Path, notes_repo: Path) -> Path | None:
    """Derive the .code-workspace path from a ticket worktree path, if it exists."""
    match = re.search(r"-([a-z]+)-(\d+)-(.+)", worktree_path.name)
    if not match:
        return None
    number = int(match.group(2))
    slug = match.group(3)
    journal_folder = f"{number:04d}-{slug}"
    workspace = (
        notes_repo
        / JOURNALS_DIR
        / journal_folder
        / f"{journal_folder}.code-workspace"
    )
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


def _prepare_frontend_env(repo: Path, worktree: Path) -> None:
    frontend_dir = worktree / FRONTEND_DIRNAME
    if not frontend_dir.is_dir() or _frontend_has_env(frontend_dir):
        return

    candidate_sources = [
        repo / FRONTEND_DIRNAME,
        SCOPEO_ROOT / LEGACY_FRONTEND_REPO,
    ]

    for source_dir in candidate_sources:
        if not source_dir.is_dir():
            continue
        symlink_env_files(
            source_dir,
            frontend_dir,
            display_prefix=f"{FRONTEND_DIRNAME}/",
        )
        if _frontend_has_env(frontend_dir):
            return


def _prepare_frontend_dependencies(worktree: Path) -> None:
    frontend_dir = worktree / FRONTEND_DIRNAME
    if not (frontend_dir / "package.json").is_file():
        return
    if (frontend_dir / "node_modules").exists():
        return
    _run_setup(frontend_dir, ["pnpm", "install"])


def _install_local_personal_rule(worktree: Path) -> None:
    source = LOCAL_CURSOR_RULES_DIR / LOCAL_PERSONAL_RULE
    if not source.is_file():
        return

    destination = worktree / ".cursor" / "rules" / LOCAL_PERSONAL_RULE
    if destination.exists() or destination.is_symlink():
        return

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.symlink_to(source)
    print(f"symlinked .cursor/rules/{LOCAL_PERSONAL_RULE}")


def init_scopeo_ticket(plan: InitPlan) -> None:
    if not plan.worktree.exists():
        with chdir(plan.repo):
            create_worktree(
                plan.branch,
                plan.worktree,
                new_branch=not _branch_exists(plan.repo, plan.branch),
            )
        _run_setup(plan.worktree, ["uv", "sync"])

    _prepare_frontend_env(plan.repo, plan.worktree)
    _prepare_frontend_dependencies(plan.worktree)
    _install_local_personal_rule(plan.worktree)

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

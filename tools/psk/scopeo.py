from dataclasses import replace
from pathlib import Path

from psk.project import resolve_project
from psk.ticketing import (
    ActiveTicket,
    InitPlan,
    TicketParts,
    _build_readme_content as _generic_build_readme_content,
    _build_workspace_payload as _generic_build_workspace_payload,
    _prepare_frontend_env as _generic_prepare_frontend_env,
    _write_text_if_missing as _generic_write_text_if_missing,
    build_branch_name,
    build_init_plan as _generic_build_init_plan,
    build_journal_folder,
    build_ticket_parts,
    find_workspace_for_ticket,
    find_worktree_for_ticket,
    init_ticket,
    list_active_tickets,
    parse_ticket,
    render_summary,
    resolve_worktree_path_for_repo,
    slugify,
)

MONOREPO_REPO = "draftnrun"
BACKEND_REPO = MONOREPO_REPO


def _scopeo_project():
    return resolve_project("scopeo")


def build_init_plan(
    ticket_or_url: str,
    slug: str,
    *,
    branch: str | None = None,
    journal_folder: str | None = None,
    workspace_file: str | None = None,
) -> InitPlan:
    return _generic_build_init_plan(
        _scopeo_project(),
        ticket_or_url,
        slug,
        branch=branch,
        journal_folder=journal_folder,
        workspace_file=workspace_file,
    )


def _build_readme_content(plan: InitPlan) -> str:
    if plan.project is None:
        plan.project = _scopeo_project()
    return _generic_build_readme_content(plan)


def _build_workspace_payload(plan: InitPlan) -> dict:
    if plan.project is None:
        plan.project = _scopeo_project()
    return _generic_build_workspace_payload(plan)


def _write_text_if_missing(path: Path, content: str) -> None:
    _generic_write_text_if_missing(path, content)


def _prepare_frontend_env(repo: Path, worktree: Path) -> None:
    project = replace(_scopeo_project(), code_repo=repo)
    _generic_prepare_frontend_env(project, worktree)


def init_scopeo_ticket(plan: InitPlan) -> None:
    if plan.project is None:
        plan.project = _scopeo_project()
    init_ticket(plan)

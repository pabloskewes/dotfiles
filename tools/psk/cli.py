import shutil
import subprocess
from pathlib import Path
from typing import Optional

import questionary
import typer

from psk.db import reset_to_main
from psk.pr_inspect import ALL_SECTIONS, DEFAULT_REPO, _BOT_NAMES, inspect_pr
from psk.scopeo import (
    BACKEND_REPO,
    FRONTEND_REPO,
    NOTES_REPO,
    SCOPEO_ROOT,
    build_init_plan,
    find_worktree_for_ticket,
    find_workspace_for_ticket,
    init_scopeo_ticket,
    list_active_tickets,
    parse_ticket,
    render_summary,
)
from psk.worktree import (
    create_worktree,
    get_repo_root,
    list_worktrees,
    remove_worktree,
    resolve_worktree_path,
)

worktree_app = typer.Typer(name="worktree", help="Manage git worktrees.")
scopeo_app = typer.Typer(name="scopeo", help="Scopeo-specific helpers.")
pr_inspect_app = typer.Typer(name="pr-inspect", help="Inspect a GitHub pull request.")
squash_app = typer.Typer(name="squash", invoke_without_command=True)


@worktree_app.command()
def create(
    branch: str = typer.Argument(..., help="Branch name"),
    new_branch: bool = typer.Option(False, "-b", help="Create a new branch"),
    worktrees_dir: Optional[str] = typer.Option(
        None, "-d", help="Override worktrees directory"
    ),
    worktree_path: Optional[str] = typer.Option(
        None, "-p", help="Override exact worktree path"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print resolved action without executing"
    ),
):
    try:
        repo_root = get_repo_root()
        path = resolve_worktree_path(branch, worktrees_dir, worktree_path)
    except (RuntimeError, ValueError) as e:
        typer.echo(f"❌ Error: {e}", err=True)
        raise typer.Exit(1)

    if dry_run:
        typer.echo(f"repo_root={repo_root}")
        typer.echo(f"branch={branch}")
        typer.echo(f"new_branch={new_branch}")
        typer.echo(f"worktree_path={path}")
        return

    try:
        create_worktree(branch, path, new_branch)
    except SystemExit:
        raise typer.Exit(1)

    typer.echo(f"\n✓ Worktree listo en: {path}")


@worktree_app.command()
def remove(
    branch: str = typer.Argument(..., help="Branch name"),
    worktrees_dir: Optional[str] = typer.Option(
        None, "-d", help="Override worktrees directory"
    ),
    worktree_path: Optional[str] = typer.Option(
        None, "-p", help="Override exact worktree path"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print resolved action without executing"
    ),
):
    try:
        repo_root = get_repo_root()
        path = resolve_worktree_path(branch, worktrees_dir, worktree_path)
    except (RuntimeError, ValueError) as e:
        typer.echo(f"❌ Error: {e}", err=True)
        raise typer.Exit(1)

    if dry_run:
        typer.echo(f"repo_root={repo_root}")
        typer.echo(f"branch={branch}")
        typer.echo(f"worktree_path={path}")
        return

    try:
        remove_worktree(path)
    except SystemExit:
        raise typer.Exit(1)

    typer.echo(f"✓ Worktree eliminado: {path}")


@worktree_app.command(name="list")
def list_cmd():
    try:
        worktrees = list_worktrees()
    except RuntimeError as e:
        typer.echo(f"❌ Error: {e}", err=True)
        raise typer.Exit(1)

    for wt in worktrees:
        branch = wt.get("branch", "(detached)")
        sha = wt.get("sha", "???????")
        path = wt.get("path", "")
        typer.echo(f"{branch}  {sha}  {path}")


@scopeo_app.command("qa")
def qa_deploy(
    target: str = typer.Option("staging", "--target", "-t", help="Target branch"),
    no_squash: bool = typer.Option(False, "--no-squash", help="Skip squash step"),
    push: bool = typer.Option(False, "--push", help="Push to remote after cherry-pick"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print plan without executing"
    ),
):
    """Squash + cherry-pick current branch to staging."""
    from psk.git_tui.git_ops import get_commit_message, get_commits, get_merge_base
    from psk.qa import build_qa_plan, execute_qa

    try:
        plan = build_qa_plan(target, skip_squash=no_squash)
    except ValueError as e:
        typer.echo(f"❌ {e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"\n  branch:    {plan.feature_branch}")
    typer.echo(f"  target:    {plan.target_branch}")
    typer.echo(f"  worktree:  {plan.staging_worktree}")
    typer.echo(f"  commits:   {plan.commit_count}")
    typer.echo(f"  squash:    {'yes' if plan.needs_squash else 'no'}")
    typer.echo(f"  HEAD:      {plan.head_sha[:7]}\n")

    if dry_run:
        return

    squash_message = None
    if plan.needs_squash:
        base_sha = get_merge_base("origin/main")
        commits = get_commits(base_sha)
        oldest = commits[-1]
        title, body = get_commit_message(oldest.sha)
        title = typer.prompt("Squash title", default=title)
        body = typer.prompt("Description (optional)", default=body or "")
        squash_message = f"{title}\n\n{body}" if body else title

    action = "cherry-pick + push" if push else "cherry-pick (local only)"
    if not typer.confirm(f"Deploy to QA? [{action}]", default=True):
        raise typer.Exit(0)

    try:
        sha = execute_qa(plan, squash_message, push=push)
    except RuntimeError as e:
        typer.echo(f"❌ {e}", err=True)
        raise typer.Exit(1)

    pushed = " + pushed" if push else " (local only — run with --push to push)"
    typer.echo(f"\n✓ {sha[:7]} cherry-picked{pushed} → {plan.target_branch}")
    typer.echo(f"  worktree: {plan.staging_worktree}")


@scopeo_app.command("db-reset-to-main")
def db_reset_to_main(
    upgrade: bool = typer.Option(
        False, "--upgrade", help="Also run 'alembic upgrade head' from cwd after resetting"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would happen without touching the DB"
    ),
):
    """Strip branch migrations from DB, returning it to main's alembic state."""
    upgrade_to = Path.cwd() if upgrade else None
    try:
        reset_to_main(upgrade_to=upgrade_to, dry_run=dry_run)
    except RuntimeError as e:
        typer.echo(f"❌ {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"❌ Unexpected error: {e}", err=True)
        raise typer.Exit(1)


@scopeo_app.command("ticket-init")
def ticket_init(
    ticket: str = typer.Argument(..., help="Linear ticket id or URL (e.g. DRA-1049)"),
    slug: Optional[str] = typer.Argument(
        None, help="Slug for branch and journal folder"
    ),
    with_frontend: bool = typer.Option(
        False, "--frontend", help="Also create a frontend worktree"
    ),
    branch: Optional[str] = typer.Option(None, help="Override branch name"),
    journal_folder: Optional[str] = typer.Option(None, help="Override journal folder"),
    workspace_file: Optional[str] = typer.Option(
        None, help="Override workspace file path"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print the resolved plan without writing"
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip all confirmation prompts"
    ),
    open_workspace: bool = typer.Option(
        False, "--open", help="Open workspace in Cursor after init"
    ),
):
    interactive = not yes and not dry_run

    if slug is None:
        if not interactive:
            typer.echo("❌ Error: slug is required in non-interactive mode", err=True)
            raise typer.Exit(1)
        slug = typer.prompt("Slug")

    if interactive and not with_frontend:
        with_frontend = typer.confirm("Include frontend?", default=False)

    try:
        plan = build_init_plan(
            ticket,
            slug,
            with_frontend=with_frontend,
            branch=branch,
            journal_folder=journal_folder,
            workspace_file=workspace_file,
        )
    except ValueError as e:
        typer.echo(f"❌ Error: {e}", err=True)
        raise typer.Exit(1)

    typer.echo(render_summary(plan))

    if dry_run:
        return

    if interactive and not typer.confirm("\nProceed?"):
        raise typer.Exit(0)

    try:
        init_scopeo_ticket(plan)
    except SystemExit:
        raise typer.Exit(1)

    typer.echo("\n✓ Scopeo ticket initialized")

    if open_workspace:
        cursor_bin = shutil.which("cursor")
        if cursor_bin:
            subprocess.run([cursor_bin, str(plan.workspace_file)])
        else:
            typer.echo("⚠️  cursor not found in PATH — open manually:", err=True)
            typer.echo(f"   cursor {plan.workspace_file}", err=True)


@scopeo_app.command("ticket-open")
def ticket_open(
    ticket: Optional[str] = typer.Argument(
        None, help="Linear ticket id or URL (e.g. DRA-996)"
    ),
):
    if ticket is None:
        active = list_active_tickets(SCOPEO_ROOT / BACKEND_REPO, SCOPEO_ROOT / FRONTEND_REPO)
        if not active:
            typer.echo("no active worktrees found", err=True)
            raise typer.Exit(1)
        choices = [
            questionary.Choice(
                title=f"{t.ticket_id:<10}  {t.slug}",
                value=t.ticket_id,
            )
            for t in active
        ]
        ticket = questionary.select("Select ticket:", choices=choices).ask()  # type: ignore[assignment]
        if ticket is None:
            raise typer.Exit(0)

    try:
        project, number = parse_ticket(ticket)
    except ValueError as e:
        typer.echo(f"❌ Error: {e}", err=True)
        raise typer.Exit(1)

    ticket_id = f"{project}-{number}"
    backend_repo = SCOPEO_ROOT / BACKEND_REPO
    frontend_repo = SCOPEO_ROOT / FRONTEND_REPO
    notes_repo = SCOPEO_ROOT / NOTES_REPO

    backend_path = find_worktree_for_ticket(backend_repo, ticket_id) or backend_repo
    frontend_path = find_worktree_for_ticket(frontend_repo, ticket_id) or frontend_repo

    typer.echo(f"opening backend: {backend_path}")
    subprocess.run(["open", "-a", "Terminal", str(backend_path)])

    typer.echo(f"opening frontend: {frontend_path}")
    subprocess.run(["open", "-a", "Terminal", str(frontend_path)])

    workspace = find_workspace_for_ticket(backend_path, notes_repo)
    if workspace:
        cursor_bin = shutil.which("cursor")
        if cursor_bin:
            typer.echo(f"opening workspace: {workspace}")
            subprocess.run([cursor_bin, str(workspace)])
        else:
            typer.echo(f"⚠️  cursor not found — open manually: cursor {workspace}", err=True)


@pr_inspect_app.command()
def inspect(
    pr_num: str = typer.Argument(..., help="PR number"),
    repo: str = typer.Option(DEFAULT_REPO, "--repo", "-R", help="GitHub repo (owner/name)"),
    only: Optional[list[str]] = typer.Option(
        None,
        "--only",
        help=f"Sections to show (repeatable): {', '.join(sorted(ALL_SECTIONS))}. Default: all.",
    ),
    no_bots: bool = typer.Option(
        False,
        "--no-bots",
        help=f"Hide comments from known bots ({', '.join(sorted(_BOT_NAMES))}).",
    ),
):
    """Print PR description, inline review comments, and filtered diff."""
    sections = set(only) if only else None
    try:
        inspect_pr(pr_num, repo, sections, no_bots=no_bots)
    except SystemExit as e:
        raise typer.Exit(int(e.code) if e.code is not None else 1)


@squash_app.callback()
def squash_default(
    base: str = typer.Option("origin/main", "--base", "-b", help="Base branch to compare against"),
    tui: bool = typer.Option(False, "--tui", help="Open the full interactive TUI"),
):
    """Squash all branch commits into one."""
    import subprocess as _sp

    from psk.git_tui.git_ops import (
        do_squash,
        get_commit_message,
        get_commits,
        get_current_branch,
        get_merge_base,
    )

    if tui:
        from psk.git_tui import run_app

        run_app(base)
        return

    try:
        branch = get_current_branch()
        base_sha = get_merge_base(base)
        commits = get_commits(base_sha)
    except _sp.CalledProcessError as exc:
        msg = exc.stderr.strip() if exc.stderr else str(exc)
        typer.echo(f"❌ {msg}", err=True)
        raise typer.Exit(1)

    if not commits:
        typer.echo(f"No commits between HEAD and {base}")
        raise typer.Exit(0)

    typer.echo(f"\n  {branch} — {len(commits)} commit(s) since {base}\n")
    for c in reversed(commits):
        typer.echo(f"  {c.short_sha}  {c.subject}")
    typer.echo()

    oldest = commits[-1]
    title, body = get_commit_message(oldest.sha)

    title = typer.prompt("Title", default=title)
    body = typer.prompt("Description (optional)", default=body or "")

    message = f"{title}\n\n{body}" if body else title

    if not typer.confirm(f"\nSquash {len(commits)} commits?", default=True):
        raise typer.Exit(0)

    try:
        do_squash(len(commits), message)
    except Exception as exc:
        typer.echo(f"❌ Squash failed: {exc}", err=True)
        raise typer.Exit(1)

    typer.echo(f"\n✓ Squashed {len(commits)} commits into: {title}")


def main_worktree() -> None:
    worktree_app()


def main_scopeo() -> None:
    scopeo_app()


def main_pr_inspect() -> None:
    pr_inspect_app()


def main_squash() -> None:
    squash_app()

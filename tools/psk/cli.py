import shutil
import subprocess
from typing import Optional

import typer

from psk.scopeo import build_init_plan, init_scopeo_ticket, render_summary, find_worktree_for_ticket, parse_ticket, SCOPEO_ROOT, BACKEND_REPO, FRONTEND_REPO
from psk.worktree import (
    create_worktree,
    get_repo_root,
    list_worktrees,
    remove_worktree,
    resolve_worktree_path,
)

worktree_app = typer.Typer(name="worktree", help="Manage git worktrees.")
scopeo_app = typer.Typer(name="scopeo", help="Scopeo-specific helpers.")


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
    ticket: str = typer.Argument(..., help="Linear ticket id or URL (e.g. DRA-996)"),
):
    try:
        project, number = parse_ticket(ticket)
    except ValueError as e:
        typer.echo(f"❌ Error: {e}", err=True)
        raise typer.Exit(1)

    ticket_id = f"{project}-{number}"
    backend_repo = SCOPEO_ROOT / BACKEND_REPO
    frontend_repo = SCOPEO_ROOT / FRONTEND_REPO

    backend_path = find_worktree_for_ticket(backend_repo, ticket_id) or backend_repo
    frontend_path = find_worktree_for_ticket(frontend_repo, ticket_id)

    typer.echo(f"opening backend: {backend_path}")
    subprocess.run(["open", "-a", "Terminal", str(backend_path)])

    if frontend_path:
        typer.echo(f"opening frontend: {frontend_path}")
        subprocess.run(["open", "-a", "Terminal", str(frontend_path)])
    else:
        typer.echo("no frontend worktree found — skipping")


app = typer.Typer(help="Personal automation tools.")
app.add_typer(worktree_app)
app.add_typer(scopeo_app)


def main() -> None:
    app()


def main_scopeo() -> None:
    scopeo_app()

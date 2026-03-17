import subprocess

import typer
from typing import Optional

from psk.worktree import get_repo_root, resolve_worktree_path, create_worktree, remove_worktree, list_worktrees
from psk.scopeo import build_init_plan, init_scopeo_ticket, render_summary

worktree_app = typer.Typer(name="worktree", help="Manage git worktrees.")
scopeo_app = typer.Typer(name="scopeo", help="Scopeo-specific helpers.")


@worktree_app.command()
def create(
    branch: str = typer.Argument(..., help="Branch name"),
    new_branch: bool = typer.Option(False, "-b", help="Create a new branch"),
    worktrees_dir: Optional[str] = typer.Option(None, "-d", help="Override worktrees directory"),
    worktree_path: Optional[str] = typer.Option(None, "-p", help="Override exact worktree path"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print resolved action without executing"),
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
    worktrees_dir: Optional[str] = typer.Option(None, "-d", help="Override worktrees directory"),
    worktree_path: Optional[str] = typer.Option(None, "-p", help="Override exact worktree path"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print resolved action without executing"),
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
    slug: Optional[str] = typer.Argument(None, help="Slug for branch and journal folder"),
    backend_repo: str = typer.Option("draftnrun", "--repo", help="Primary backend repo"),
    with_frontend: bool = typer.Option(False, "--frontend", help="Also create a frontend worktree"),
    frontend_repo: str = typer.Option("back-office", help="Frontend repo name"),
    branch: Optional[str] = typer.Option(None, help="Override branch name"),
    journal_folder: Optional[str] = typer.Option(None, help="Override journal folder"),
    workspace_file: Optional[str] = typer.Option(None, help="Override workspace file path"),
    create_readme: bool = typer.Option(True, "--create-readme/--no-create-readme"),
    create_plan: bool = typer.Option(True, "--create-plan/--no-create-plan"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the resolved plan without writing"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip all confirmation prompts"),
    open_workspace: bool = typer.Option(False, "--open", help="Open workspace in Cursor after init"),
):
    if slug is None:
        if yes:
            typer.echo("❌ Error: slug is required when using --yes", err=True)
            raise typer.Exit(1)
        slug = typer.prompt("Slug")

    if not yes and not with_frontend:
        with_frontend = typer.confirm("Include frontend?", default=False)

    try:
        plan = build_init_plan(
            ticket,
            slug,
            backend_repo_name=backend_repo,
            with_frontend=with_frontend,
            frontend_repo_name=frontend_repo,
            branch=branch,
            journal_folder=journal_folder,
            workspace_file=workspace_file,
            create_readme=create_readme,
            create_plan=create_plan,
        )
    except ValueError as e:
        typer.echo(f"❌ Error: {e}", err=True)
        raise typer.Exit(1)

    typer.echo(render_summary(plan))

    if dry_run:
        return

    if not yes and not typer.confirm("\nProceed?"):
        raise typer.Exit(0)

    try:
        init_scopeo_ticket(plan)
    except SystemExit:
        raise typer.Exit(1)

    typer.echo("\n✓ Scopeo ticket initialized")

    if open_workspace:
        subprocess.run(["cursor", str(plan.workspace_file)])


app = typer.Typer(help="Personal automation tools.")
app.add_typer(worktree_app)
app.add_typer(scopeo_app)


def main() -> None:
    app()


def main_scopeo_ticket_init() -> None:
    typer.run(ticket_init)

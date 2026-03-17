import typer
from pathlib import Path
from typing import Optional

from psk.worktree import get_repo_root, resolve_worktree_path, create_worktree, remove_worktree

worktree_create_app = typer.Typer()
worktree_remove_app = typer.Typer()


@worktree_create_app.command()
def worktree_create(
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


@worktree_remove_app.command()
def worktree_remove(
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

    remove_worktree(path)
    typer.echo(f"✓ Worktree eliminado: {path}")

import shutil
import subprocess
from pathlib import Path
from typing import Optional

import click
import questionary
import typer

from psk.cursor import infer_cursor_project, list_transcripts, render_tail
from psk.db import reset_to_main
from psk.pr_inspect import (
    _BOT_NAMES,
    ALL_SECTIONS,
    DEFAULT_REPO,
    inspect_pr,
    list_coderabbit_threads,
    resolve_coderabbit_threads,
)
from psk.scopeo import (
    MONOREPO_REPO,
    NOTES_REPO,
    SCOPEO_ROOT,
    build_init_plan,
    find_workspace_for_ticket,
    find_worktree_for_ticket,
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
pr_inspect_app = typer.Typer(
    name="pr-inspect",
    help="Inspect a GitHub pull request.",
    invoke_without_command=True,
)
squash_app = typer.Typer(name="squash", invoke_without_command=True)
cursor_app = typer.Typer(name="cursor-read", help="Inspect Cursor conversation transcripts.")


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


@scopeo_app.command("staging")
def staging_deploy(
    target: str = typer.Option("staging", "--target", "-t", help="Target branch"),
    message: Optional[str] = typer.Option(
        None, "--message", "-m", help="Commit message (non-interactive)"
    ),
    push: bool = typer.Option(False, "--push", help="Push to origin after commit"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print plan without executing"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
):
    """Apply the feature branch delta on top of origin/<target> as a single commit.

    Never rewrites the feature branch history. Never force-pushes.
    """
    from psk.staging import PROTECTED_TARGETS, build_staging_plan, execute_staging

    try:
        plan = build_staging_plan(target)
    except ValueError as e:
        typer.echo(f"❌ {e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"\n  feature:   {plan.feature_branch}")
    typer.echo(f"  target:    {plan.target_branch} @ {plan.target_remote_sha[:7]}")
    typer.echo(f"  HEAD:      {plan.feature_head_sha[:7]}")
    typer.echo(f"  worktree:  {plan.target_worktree}")
    typer.echo(f"  files:     {len(plan.changed_files)}")
    typer.echo(f"\n{plan.diff_stat}\n")
    if plan.commit_subjects:
        typer.echo(f"  Commits in feature ({len(plan.commit_subjects)}):")
        for subject in plan.commit_subjects:
            typer.echo(f"    • {subject}")
        typer.echo("")

    if dry_run:
        return

    if message is None:
        default = plan.commit_subjects[0] if plan.commit_subjects else ""
        title = typer.prompt("Commit title", default=default)
        body = typer.prompt("Description (optional)", default="")
        message = f"{title}\n\n{body}" if body else title

    action = "apply + commit" + (" + push" if push else " (local only)")
    if target in PROTECTED_TARGETS:
        typer.echo(f"⚠️  Target '{target}' is a protected branch.")
    if not yes and not typer.confirm(f"Deploy to {target}? [{action}]", default=True):
        raise typer.Exit(0)

    try:
        sha = execute_staging(plan, message, push=push)
    except RuntimeError as e:
        typer.echo(f"❌ {e}", err=True)
        raise typer.Exit(1)

    pushed = " + pushed" if push else " (local only — run with --push to push)"
    typer.echo(f"\n✓ {sha[:7]} committed{pushed} → {plan.target_branch}")
    typer.echo(f"  worktree: {plan.target_worktree}")


@scopeo_app.command("db-reset-to-main")
def db_reset_to_main(
    upgrade: bool = typer.Option(
        False,
        "--upgrade",
        help="Also run 'alembic upgrade head' from cwd after resetting",
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

    try:
        plan = build_init_plan(
            ticket,
            slug,
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
    repo = SCOPEO_ROOT / MONOREPO_REPO
    notes_repo = SCOPEO_ROOT / NOTES_REPO

    if ticket is None:
        active = list_active_tickets(repo)
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
    worktree_path = find_worktree_for_ticket(repo, ticket_id) or repo

    typer.echo(f"opening worktree: {worktree_path}")
    subprocess.run(["open", "-a", "Terminal", str(worktree_path)])

    workspace = find_workspace_for_ticket(worktree_path, notes_repo)
    if workspace:
        cursor_bin = shutil.which("cursor")
        if cursor_bin:
            typer.echo(f"opening workspace: {workspace}")
            subprocess.run([cursor_bin, str(workspace)])
        else:
            typer.echo(
                f"⚠️  cursor not found — open manually: cursor {workspace}", err=True
            )


@pr_inspect_app.callback()
def inspect(
    pr_num: str = typer.Argument(..., help="PR number"),
    repo: str = typer.Option(
        DEFAULT_REPO, "--repo", "-R", help="GitHub repo (owner/name)"
    ),
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


@pr_inspect_app.command("resolve-coderabbit")
def resolve_coderabbit(
    pr_num: str = typer.Argument(..., help="PR number"),
    repo: str = typer.Option(
        DEFAULT_REPO, "--repo", "-R", help="GitHub repo (owner/name)"
    ),
    list_only: bool = typer.Option(
        False, "--list", help="List open threads without resolving"
    ),
    resolve: Optional[str] = typer.Option(
        None, "--resolve", help="Comma-separated indices to resolve (e.g. 1,3)"
    ),
    all_threads: bool = typer.Option(
        False, "--all", help="Resolve all open CodeRabbit threads"
    ),
):
    try:
        if list_only:
            list_coderabbit_threads(pr_num, repo)
        else:
            resolve_coderabbit_threads(pr_num, repo, resolve, all_threads)
    except RuntimeError as e:
        typer.echo(f"❌ {e}", err=True)
        raise typer.Exit(1)


@squash_app.callback()
def squash_default(
    ctx: typer.Context,
    pr_num: Optional[str] = typer.Argument(None, help="PR number"),
):
    if ctx.invoked_subcommand is not None or pr_num is None:
        return
    from psk.git_tui.tui import run

    run(pr_num)


@cursor_app.command("list")
def cursor_list(
    path: Optional[str] = typer.Option(
        None, "--path", "-p", help="Folder or workspace file (default: CWD)"
    ),
    limit: int = typer.Option(20, "--limit", "-n", help="Max transcripts to show"),
):
    """List recent conversation transcripts for the inferred Cursor project."""

    project = infer_cursor_project(Path(path) if path else None)
    if not project:
        typer.echo("❌ Could not find Cursor project.", err=True)
        raise typer.Exit(1)

    transcripts = list_transcripts(project, n=limit)
    if not transcripts:
        typer.echo("No transcripts found.")
        return

    for t in transcripts:
        preview = t.first_user_message.replace("\n", " ")
        typer.echo(
            f"{t.short_uuid}  {t.timestamp}  users={t.user_turn_count:<2}  {preview}"
        )


@cursor_app.command("show")
def cursor_show(
    uuid_prefix: str = typer.Argument(..., help="UUID or prefix shown by list"),
    path: Optional[str] = typer.Option(
        None, "--path", "-p", help="Folder or workspace file (default: CWD)"
    ),
    turns: int = typer.Option(40, "--turns", "-t", help="Number of turns to show"),
    chars: int = typer.Option(12000, "--chars", "-c", help="Max characters"),
):
    """Show one transcript by UUID prefix."""

    project = infer_cursor_project(Path(path) if path else None)
    if not project:
        typer.echo("❌ Could not find Cursor project.", err=True)
        raise typer.Exit(1)

    transcripts = list_transcripts(project, n=200)
    matches = [t for t in transcripts if t.uuid.startswith(uuid_prefix)]
    if not matches:
        typer.echo(f"❌ No transcript found with prefix '{uuid_prefix}'", err=True)
        raise typer.Exit(1)
    if len(matches) > 1:
        typer.echo("Ambiguous prefix. Matches:", err=True)
        for t in matches:
            typer.echo(f"  {t.short_uuid}  {t.timestamp}  {t.first_user_message}")
        raise typer.Exit(1)

    typer.echo(render_tail(matches[0].jsonl_path, turns=turns, chars=chars))


@cursor_app.command("tail")
def cursor_tail(
    uuid_prefix: Optional[str] = typer.Argument(
        None, help="UUID prefix (default: most recent)"
    ),
    path: Optional[str] = typer.Option(
        None, "--path", "-p", help="Folder or workspace file (default: CWD)"
    ),
    turns: int = typer.Option(10, "--turns", "-t", help="Number of turns to show"),
    chars: int = typer.Option(4000, "--chars", "-c", help="Max characters"),
):
    """Show the tail of a conversation transcript."""
    from psk.cursor import infer_cursor_project, list_transcripts, render_tail

    project = infer_cursor_project(Path(path) if path else None)
    if not project:
        typer.echo("❌ Could not find Cursor project.", err=True)
        raise typer.Exit(1)

    transcripts = list_transcripts(project, n=200)
    if not transcripts:
        typer.echo("No transcripts found.", err=True)
        raise typer.Exit(1)

    if uuid_prefix:
        matches = [t for t in transcripts if t.uuid.startswith(uuid_prefix)]
        if not matches:
            typer.echo(f"❌ No transcript found with prefix '{uuid_prefix}'", err=True)
            raise typer.Exit(1)
        selected = matches[0]
    else:
        selected = transcripts[0]

    typer.echo(render_tail(selected.jsonl_path, turns=turns, chars=chars))


@cursor_app.command("latest")
def cursor_latest(
    path: Optional[str] = typer.Option(
        None, "--path", "-p", help="Folder or workspace file (default: CWD)"
    ),
    turns: int = typer.Option(10, "--turns", "-t", help="Number of turns to show"),
    chars: int = typer.Option(4000, "--chars", "-c", help="Max characters"),
):
    """Show the tail of the most recent transcript (shorthand for tail without UUID)."""

    project = infer_cursor_project(Path(path) if path else None)
    if not project:
        typer.echo("❌ Could not find Cursor project.", err=True)
        raise typer.Exit(1)

    transcripts = list_transcripts(project, n=1)
    if not transcripts:
        typer.echo("No transcripts found.", err=True)
        raise typer.Exit(1)

    typer.echo(render_tail(transcripts[0].jsonl_path, turns=turns, chars=chars))


def main_worktree() -> None:
    worktree_app()


def main_scopeo() -> None:
    scopeo_app()


def main_pr_inspect() -> None:
    pr_inspect_app()


def main_squash() -> None:
    squash_app()


def main_cursor_read() -> None:
    cursor_app()

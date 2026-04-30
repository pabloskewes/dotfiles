"""
Database migration helpers for Scopeo/draftnrun worktree workflow.

Strips branch-specific alembic migrations from the shared DB so it returns
to a state that belongs to main's migration chain.  Works from any worktree
by auto-detecting which worktree owns each branch migration.
"""

import re
import shutil
import subprocess
from pathlib import Path

from psk.project import resolve_project

_ALEMBIC_INI = "ada_backend/database/alembic.ini"
_VERSIONS_DIR = "ada_backend/database/alembic/versions"


def _main_repo() -> Path:
    return resolve_project("scopeo").code_repo


def _check_prerequisites() -> None:
    if not shutil.which("uv"):
        raise RuntimeError(
            "'uv' not found on PATH. Install it from https://docs.astral.sh/uv/"
        )


def _run_alembic(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run alembic and capture output (for parsing)."""
    return subprocess.run(
        ["uv", "run", "alembic", "--config", _ALEMBIC_INI, *args],
        check=True,
        capture_output=True,
        text=True,
        cwd=cwd,
    )


def _stream_alembic(cwd: Path, *args: str) -> None:
    """Run alembic with output streamed to the terminal."""
    subprocess.run(
        ["uv", "run", "alembic", "--config", _ALEMBIC_INI, *args],
        check=True,
        cwd=cwd,
    )


def _get_db_current() -> str | None:
    """Return the current alembic revision of the DB, or None if empty."""
    result = _run_alembic(_main_repo(), "current")
    match = re.search(r"^([a-f0-9]+)", result.stdout, re.MULTILINE)
    return match.group(1) if match else None


def _get_main_revisions() -> set[str]:
    """Return the set of all revision IDs present in main's alembic versions dir."""
    versions_dir = _main_repo() / _VERSIONS_DIR
    revisions = set()
    for py_file in versions_dir.glob("*.py"):
        # Filenames are like: a3b4c5d6e7e8_description.py
        rev_id = py_file.stem.split("_")[0]
        if re.fullmatch(r"[a-f0-9]+", rev_id):
            revisions.add(rev_id)
    return revisions


def _get_main_head() -> str:
    """Return the single alembic HEAD of main."""
    result = _run_alembic(_main_repo(), "heads")
    heads = re.findall(r"^([a-f0-9]+)\s+\(head\)", result.stdout, re.MULTILINE)
    if len(heads) != 1:
        raise RuntimeError(
            f"draftnrun/main has {len(heads)} alembic heads: {heads}\n"
            "Resolve the divergence on main before running db-reset-to-main."
        )
    return heads[0]


def _list_worktree_paths() -> list[Path]:
    """Return paths of all draftnrun worktrees (excluding the main checkout)."""
    main_repo = _main_repo()
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
        cwd=main_repo,
    )
    paths = []
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            p = Path(line[len("worktree ") :])
            if p != main_repo:
                paths.append(p)
    return paths


def _find_worktree_for_revision(revision: str) -> Path | None:
    """Find which worktree contains the migration file for a given revision."""
    for wt in _list_worktree_paths():
        versions_dir = wt / _VERSIONS_DIR
        if any(versions_dir.glob(f"{revision}_*.py")):
            return wt
    return None


def reset_to_main(*, upgrade_to: Path | None = None, dry_run: bool = False) -> None:
    """
    Strip branch-specific migrations from the DB until it's on main's chain.
    Optionally upgrade to a worktree's HEAD after.

    Args:
        upgrade_to: if set, run `alembic upgrade head` from this worktree after resetting.
        dry_run: if True, print the plan without touching the DB.
    """
    _check_prerequisites()

    main_revisions = _get_main_revisions()
    main_head = _get_main_head()
    current = _get_db_current()

    if current is None:
        print("DB has no alembic revision. Nothing to reset.")
        return

    print(f"DB current revision : {current}")
    print(f"main HEAD           : {main_head}")

    if current in main_revisions:
        if current == main_head:
            print("DB is already at main HEAD. Nothing to do.")
        else:
            print(f"DB is on main's chain but behind HEAD.")
            if dry_run:
                print(f"  would upgrade to main HEAD: {main_head}")
            else:
                print(f"  Upgrading to main HEAD...")
                _stream_alembic(_main_repo(), "upgrade", main_head)
                print("  Done.")
    else:
        print(f"DB has branch-specific migration(s). Stripping...")
        iteration = 0
        max_iterations = 20

        while current not in main_revisions:
            iteration += 1
            if iteration > max_iterations:
                raise RuntimeError(
                    f"Exceeded {max_iterations} downgrade steps. Something is wrong."
                )

            worktree = _find_worktree_for_revision(current)
            if worktree is None:
                raise RuntimeError(
                    f"Cannot find worktree containing migration {current}.\n"
                    "The worktree that owns this migration may have been deleted."
                )

            if dry_run:
                print(f"  would downgrade {current} (from {worktree.name})")
            else:
                print(f"  Downgrading {current} (from {worktree.name})...")
                _stream_alembic(worktree, "downgrade", "-1")

            current = _get_db_current() if not dry_run else None
            if dry_run:
                break

        if not dry_run:
            print(f"  DB is now at: {current}")
            if current != main_head:
                print(f"  Upgrading to main HEAD ({main_head})...")
                _stream_alembic(_main_repo(), "upgrade", main_head)

        print("  Done.")

    if upgrade_to:
        if dry_run:
            print(f"would upgrade to branch HEAD (from {upgrade_to.name})")
        else:
            print(f"Upgrading to branch HEAD (from {upgrade_to.name})...")
            _stream_alembic(upgrade_to, "upgrade", "head")
            print("Done.")

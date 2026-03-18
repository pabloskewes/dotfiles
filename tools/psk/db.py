"""
Database migration helpers for Scopeo/draftnrun worktree workflow.

All alembic commands run via `uv run alembic` subprocess so they use the
project's own venv (with all its dependencies) rather than psk's environment.
"""

import re
import shutil
import subprocess
from pathlib import Path

from psk.scopeo import BACKEND_REPO, SCOPEO_ROOT

_ALEMBIC_INI = "ada_backend/database/alembic.ini"
_MAIN_REPO = SCOPEO_ROOT / BACKEND_REPO


def _check_prerequisites() -> None:
    """Verify that required external tools are available on PATH."""
    if not shutil.which("uv"):
        raise RuntimeError(
            "'uv' not found on PATH. Install it from https://docs.astral.sh/uv/"
        )


def _run_alembic(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "alembic", "--config", _ALEMBIC_INI, *args],
        check=True,
        capture_output=True,
        text=True,
        cwd=cwd,
    )


def get_main_head() -> str:
    """
    Return the alembic HEAD revision of main by running `alembic heads`
    in the primary draftnrun checkout.

    Raises:
        RuntimeError: if main has 0 or multiple heads.
    """
    result = _run_alembic(_MAIN_REPO, "heads")
    heads = re.findall(r"^([a-f0-9]+)\s+\(head\)", result.stdout, re.MULTILINE)

    if len(heads) != 1:
        raise RuntimeError(
            f"draftnrun/main has {len(heads)} alembic heads: {heads}\n"
            "Resolve the divergence on main before running db-reset-to-main."
        )

    return heads[0]


def reset_to_main(repo_root: Path, *, upgrade: bool = False, dry_run: bool = False) -> None:
    """
    Downgrade the DB to main HEAD, optionally upgrade to branch HEAD after.

    Args:
        repo_root: path to the draftnrun worktree (where alembic.ini lives under ada_backend/).
        upgrade: if True, also run `alembic upgrade head` after downgrading.
        dry_run: if True, print the planned revisions without touching the DB.
    """
    _check_prerequisites()
    main_head = get_main_head()

    if dry_run:
        print(f"would downgrade to main HEAD: {main_head}")
        if upgrade:
            print("would upgrade to branch HEAD (alembic upgrade head)")
        return

    print(f"Downgrading to main HEAD: {main_head}")
    result = _run_alembic(repo_root, "downgrade", main_head)
    if result.stdout:
        print(result.stdout, end="")

    if upgrade:
        print("Upgrading to branch HEAD...")
        result = _run_alembic(repo_root, "upgrade", "head")
        if result.stdout:
            print(result.stdout, end="")

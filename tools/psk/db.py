"""
Database migration helpers for Scopeo/draftnrun worktree workflow.

Resolves the alembic HEAD of main by running `alembic heads` in the primary
draftnrun checkout (~/Scopeo/draftnrun), which is always on main and has all
project dependencies available via `uv run`.
"""

import re
import subprocess
from pathlib import Path

from alembic import command
from alembic.config import Config

from psk.scopeo import BACKEND_REPO, SCOPEO_ROOT

_ALEMBIC_INI = "ada_backend/database/alembic.ini"
_MAIN_REPO = SCOPEO_ROOT / BACKEND_REPO


def get_main_head() -> str:
    """
    Return the alembic HEAD revision of main by running `alembic heads`
    in the primary draftnrun checkout.

    Raises:
        RuntimeError: if main has 0 or multiple heads.
    """
    result = subprocess.run(
        ["uv", "run", "alembic", "--config", _ALEMBIC_INI, "heads"],
        check=True,
        capture_output=True,
        text=True,
        cwd=_MAIN_REPO,
    )
    # Each head line looks like: "a3b4c5d6e7e8 (head)"
    heads = re.findall(r"^([a-f0-9]+)\s+\(head\)", result.stdout, re.MULTILINE)

    if len(heads) != 1:
        raise RuntimeError(
            f"draftnrun/main has {len(heads)} alembic heads: {heads}\n"
            "Resolve the divergence on main before running db-reset-to-main."
        )

    return heads[0]


def reset_to_main(
    repo_root: Path, *, upgrade: bool = False, dry_run: bool = False
) -> None:
    """
    Downgrade the DB to main HEAD, optionally upgrade to branch HEAD after.

    Args:
        repo_root: path to the draftnrun worktree (where alembic.ini lives under ada_backend/).
        upgrade: if True, also run `alembic upgrade head` after downgrading.
        dry_run: if True, print the planned revisions without touching the DB.
    """
    main_head = get_main_head()

    if dry_run:
        print(f"would downgrade to main HEAD: {main_head}")
        if upgrade:
            print("would upgrade to branch HEAD (alembic upgrade head)")
        return

    cfg = Config(str(repo_root / _ALEMBIC_INI))

    print(f"Downgrading to main HEAD: {main_head}")
    command.downgrade(cfg, main_head)

    if upgrade:
        print("Upgrading to branch HEAD...")
        command.upgrade(cfg, "head")

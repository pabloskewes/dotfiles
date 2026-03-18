"""
Database migration helpers for Scopeo/draftnrun worktree workflow.

Provides `get_main_head()` to resolve the alembic HEAD of origin/main
without checking out the branch, using git-archive + alembic's ScriptDirectory.
"""

import subprocess
import tarfile
import tempfile
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

# Relative path to alembic config inside the draftnrun repo
_ALEMBIC_INI = "ada_backend/database/alembic.ini"
_ALEMBIC_DIR = "ada_backend/database/alembic"


def get_main_head(repo_root: Path) -> str:
    """
    Return the alembic HEAD revision of origin/main without checking out the branch.

    Raises:
        RuntimeError: if main has multiple heads (needs manual resolution).
        subprocess.CalledProcessError: if git archive fails.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # Extract only alembic files from origin/main into a temp dir
        archive_path = tmp / "archive.tar"
        with open(archive_path, "wb") as f:
            subprocess.run(
                ["git", "archive", "origin/main", _ALEMBIC_INI, _ALEMBIC_DIR],
                stdout=f,
                check=True,
                cwd=repo_root,
            )

        with tarfile.open(archive_path) as tar:
            tar.extractall(tmp)

        cfg = Config(str(tmp / _ALEMBIC_INI))
        cfg.set_main_option("script_location", str(tmp / _ALEMBIC_DIR))
        script = ScriptDirectory.from_config(cfg)
        heads = script.get_heads()

        if len(heads) != 1:
            raise RuntimeError(
                f"origin/main has multiple alembic heads: {heads}\n"
                "Resolve the divergence on main before running db-reset-to-main."
            )

        return heads[0]


def reset_to_main(
    repo_root: Path, *, upgrade: bool = False, dry_run: bool = False
) -> None:
    """
    Downgrade the DB to origin/main HEAD, optionally upgrade to branch HEAD after.

    Args:
        repo_root: path to the draftnrun worktree (where alembic.ini lives under ada_backend/).
        upgrade: if True, also run `alembic upgrade head` after downgrading.
        dry_run: if True, print the planned revisions without touching the DB.
    """
    subprocess.run(["git", "fetch", "origin", "main"], check=True, cwd=repo_root)
    main_head = get_main_head(repo_root)

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

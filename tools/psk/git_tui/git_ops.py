from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass
class Commit:
    sha: str
    short_sha: str
    subject: str
    author: str


def get_current_branch() -> str:
    return subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def get_merge_base(base: str = "main") -> str:
    return subprocess.run(
        ["git", "merge-base", "HEAD", base],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def get_commits(since_sha: str) -> list[Commit]:
    """Return commits from ``since_sha..HEAD``, newest first."""
    text = subprocess.run(
        ["git", "log", "--format=%H%n%h%n%s%n%an", f"{since_sha}..HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    if not text:
        return []
    lines = text.split("\n")
    return [
        Commit(
            sha=lines[i],
            short_sha=lines[i + 1],
            subject=lines[i + 2],
            author=lines[i + 3],
        )
        for i in range(0, len(lines), 4)
    ]


def get_commit_message(sha: str) -> tuple[str, str]:
    """Return (subject, body) for a single commit."""
    text = subprocess.run(
        ["git", "log", "-1", "--format=%s%n---%n%b", sha],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    parts = text.split("\n---\n", 1)
    subject = parts[0].strip()
    raw_body = parts[1] if len(parts) > 1 else ""
    body = "\n".join(l for l in raw_body.splitlines() if not l.startswith("#")).strip()
    return subject, body


def get_commit_detail(sha: str) -> str:
    """Return full commit message + file stats for *sha*."""
    header = subprocess.run(
        ["git", "log", "-1", "--format=commit %H%nAuthor: %an <%ae>%nDate:   %ad%n%n%B", sha],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    stat = subprocess.run(
        ["git", "diff-tree", "--stat", "--no-commit-id", "-r", sha],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return f"{header}\n\n{stat}" if stat else header


def has_uncommitted_changes() -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True,
    )
    return bool(result.stdout.strip())


def do_squash(count: int, message: str) -> None:
    """Squash the top *count* commits into one with *message*."""
    subprocess.run(["git", "reset", "--soft", f"HEAD~{count}"], check=True)
    subprocess.run(["git", "commit", "-m", message], check=True)


def do_reorder(base_sha: str, shas_oldest_first: list[str]) -> None:
    """Reorder commits by cherry-picking in *shas_oldest_first* order on top of *base_sha*."""
    orig_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    subprocess.run(["git", "reset", "--hard", base_sha], check=True)
    try:
        for sha in shas_oldest_first:
            subprocess.run(["git", "cherry-pick", sha], check=True)
    except subprocess.CalledProcessError:
        subprocess.run(["git", "cherry-pick", "--abort"], check=False)
        subprocess.run(["git", "reset", "--hard", orig_head], check=True)
        raise RuntimeError("Cherry-pick failed; branch restored to original state")

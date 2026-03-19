import json
import os
import re
import subprocess
import sys

DEFAULT_REPO = "Scopeo/draftnrun"
_BOT_NAMES = {"coderabbitai", "github-actions", "dependabot"}
KNOWN_BOTS = _BOT_NAMES | {f"{b}[bot]" for b in _BOT_NAMES}
IGNORE_PATTERNS = [
    r"uv\.lock",
    r"package-lock\.json",
    r"yarn\.lock",
    r".*\.min\.js",
    r".*\.ipynb",
]


def _base_env() -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        {
            "GH_PAGER": "",
            "GH_FORCE_TTY": "0",
            "NO_COLOR": "1",
            "TERM": "dumb",
        }
    )
    return env


def filter_diff(diff_text: str, ignore_patterns: list[str]) -> str:
    pattern = re.compile("|".join(ignore_patterns))
    kept_lines: list[str] = []
    current_chunk: list[str] = []
    skip_chunk = False

    for line in diff_text.splitlines(keepends=True):
        if line.startswith("diff --git "):
            if current_chunk and not skip_chunk:
                kept_lines.extend(current_chunk)
            current_chunk = [line]
            skip_chunk = bool(pattern.search(line))
            continue
        current_chunk.append(line)

    if current_chunk and not skip_chunk:
        kept_lines.extend(current_chunk)

    return "".join(kept_lines)


def fetch_pr_view(pr_num: str, repo: str, env: dict[str, str]) -> int:
    result = subprocess.run(
        ["gh", "pr", "view", pr_num, "--repo", repo, "--comments"],
        text=True,
        env=env,
    )
    return result.returncode


def fetch_inline_comments(
    pr_num: str,
    repo: str,
    env: dict[str, str],
    exclude_users: set[str] | None = None,
) -> int:
    result = subprocess.run(
        [
            "gh",
            "api",
            "-H",
            "Accept: application/vnd.github+json",
            f"/repos/{repo}/pulls/{pr_num}/comments",
            "--paginate",
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        return result.returncode

    comments: list[dict] = json.loads(result.stdout)
    for c in comments:
        login = c.get("user", {}).get("login", "?")
        if exclude_users and login in exclude_users:
            continue
        created_at = c.get("created_at", "")
        path = c.get("path", "")
        line = c.get("line") or c.get("original_line") or 0
        body = c.get("body", "")
        print(f"{login}  {created_at}  ({path}:{line})")
        print(body)
        print("---")

    return 0


def fetch_diff(pr_num: str, repo: str, env: dict[str, str]) -> int:
    result = subprocess.run(
        ["gh", "pr", "diff", pr_num, "--repo", repo, "--color=never"],
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        return result.returncode

    print(filter_diff(result.stdout, IGNORE_PATTERNS), end="")
    return 0


ALL_SECTIONS = {"summary", "comments", "diff"}


def inspect_pr(
    pr_num: str,
    repo: str = DEFAULT_REPO,
    sections: set[str] | None = None,
    no_bots: bool = False,
) -> None:
    if sections is None:
        sections = ALL_SECTIONS

    unknown = sections - ALL_SECTIONS
    if unknown:
        print(
            f"❌ Unknown section(s): {', '.join(sorted(unknown))}. Valid: summary, comments, diff",
            file=sys.stderr,
        )
        raise SystemExit(1)

    env = _base_env()

    print(f"🔍 Searching PR #{pr_num} in the repo: {repo}...")
    print("---------------------------------------------------")

    if "summary" in sections:
        rc = fetch_pr_view(pr_num, repo, env)
        if rc != 0:
            raise SystemExit(rc)

    if "comments" in sections:
        print()
        print("=============================================")
        print(f"🧵 INLINE REVIEW COMMENTS OF PR #{pr_num}")
        print("=============================================")
        print()
        exclude_users = KNOWN_BOTS if no_bots else None
        rc = fetch_inline_comments(pr_num, repo, env, exclude_users=exclude_users)
        if rc != 0:
            raise SystemExit(rc)

    if "diff" in sections:
        print()
        print("=============================================")
        print(f"📄 CODE (DIFF) OF PR #{pr_num}")
        print("=============================================")
        print()
        rc = fetch_diff(pr_num, repo, env)
        if rc != 0:
            raise SystemExit(rc)

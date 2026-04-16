import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from psk.scopeo import find_workspace_for_ticket

CURSOR_PROJECTS_DIR = Path.home() / ".cursor" / "projects"
_NOTES_CANDIDATES = [
    Path.home() / "Scopeo" / "scopeo-notes",
    Path.home() / "FCFM" / "Magister" / "thesis-notes",
]


def _path_to_project_hash(path: Path) -> str:
    """Convert an absolute path to its Cursor project folder name."""
    normalized = str(path).lstrip("/")
    return re.sub(r"[^a-zA-Z0-9\-]", "-", normalized)


def _project_dir(path: Path) -> Path:
    return CURSOR_PROJECTS_DIR / _path_to_project_hash(path)


def _has_transcripts(project: Path) -> bool:
    return (project / "agent-transcripts").exists()


def _workspace_for_dir(cwd: Path) -> Path | None:
    """Try to find a .code-workspace for a worktree/repo CWD via notes repos."""
    for notes_repo in _NOTES_CANDIDATES:
        if not notes_repo.exists():
            continue
        workspace = find_workspace_for_ticket(cwd, notes_repo)
        if workspace:
            return workspace
    return None


def infer_cursor_project(path: Path | None = None) -> Path | None:
    """Infer the Cursor project directory from a path or CWD.

    Resolution order:
    1. Workspace file passed directly.
    2. Workspace file derived from a worktree/repo folder via notes repo lookup.
    3. The folder itself as a Cursor project.
    4. Fuzzy match: most recently active project whose folder name contains the CWD name.
    """
    target = path or Path.cwd()

    if target.is_file():
        proj = _project_dir(target)
        if _has_transcripts(proj):
            return proj

    if target.is_dir():
        workspace = _workspace_for_dir(target)
        if workspace:
            proj = _project_dir(workspace)
            if _has_transcripts(proj):
                return proj

        proj = _project_dir(target)
        if _has_transcripts(proj):
            return proj

    if not CURSOR_PROJECTS_DIR.exists():
        return None

    name_part = target.name
    candidates = [
        p
        for p in CURSOR_PROJECTS_DIR.iterdir()
        if p.is_dir() and name_part in p.name and _has_transcripts(p)
    ]
    if candidates:
        candidates.sort(
            key=lambda p: max(
                (f.stat().st_mtime for f in (p / "agent-transcripts").rglob("*.jsonl")),
                default=0.0,
            ),
            reverse=True,
        )
        return candidates[0]

    return None


@dataclass
class TranscriptInfo:
    uuid: str
    jsonl_path: Path
    mtime: float
    user_turn_count: int
    first_user_message: str

    @property
    def timestamp(self) -> str:
        return datetime.fromtimestamp(self.mtime).strftime("%Y-%m-%d %H:%M")

    @property
    def short_uuid(self) -> str:
        return self.uuid[:8]


def list_transcripts(project_dir: Path, n: int = 20) -> list[TranscriptInfo]:
    transcripts_dir = project_dir / "agent-transcripts"
    results = []
    for entry in transcripts_dir.iterdir():
        if not entry.is_dir():
            continue
        jsonl = entry / f"{entry.name}.jsonl"
        if not jsonl.exists():
            continue
        try:
            mtime = jsonl.stat().st_mtime
            with open(jsonl) as f:
                messages = [json.loads(line) for line in f if line.strip()]
            user_msgs = [m for m in messages if m.get("role") == "user"]
            first_text = (
                _clean_user_text(_extract_text(user_msgs[0]["message"]["content"])) if user_msgs else ""
            )
            results.append(
                TranscriptInfo(
                    uuid=entry.name,
                    jsonl_path=jsonl,
                    mtime=mtime,
                    user_turn_count=len(user_msgs),
                    first_user_message=first_text[:80].replace("\n", " "),
                )
            )
        except (json.JSONDecodeError, KeyError, OSError, IndexError):
            continue

    results.sort(key=lambda t: t.mtime, reverse=True)
    return results[:n]


_SYSTEM_TAG_RE = re.compile(r"<[a-z][a-z_]*(?:\s[^>]*)?>.*?</[a-z][a-z_]*>", re.DOTALL)
_THINKING_RE = re.compile(r"<thinking>.*?</thinking>", re.DOTALL)
_USER_QUERY_RE = re.compile(r"<user_query>(.*?)</user_query>", re.DOTALL)


def _extract_text(content: list[dict]) -> str:
    """Extract raw text from a content array (no tag stripping — used for grouping)."""
    parts = []
    for item in content:
        if item.get("type") == "text":
            text = item.get("text", "")
            if text.strip():
                parts.append(text)
    return "\n".join(parts)


def _clean_user_text(text: str) -> str:
    user_query_match = _USER_QUERY_RE.search(text)
    if user_query_match:
        return user_query_match.group(1).strip()
    return _SYSTEM_TAG_RE.sub("", text).strip()


def _clean_assistant_text(text: str) -> str:
    text = _THINKING_RE.sub("", text)
    # Strip content up to any orphaned </thinking> whose <thinking> opener was in a prior chunk
    text = re.sub(r"^[\s\S]*?</thinking>", "", text)
    text = _SYSTEM_TAG_RE.sub("", text)
    return text.strip()


@dataclass
class Turn:
    role: str
    text: str


def load_turns(jsonl_path: Path) -> list[Turn]:
    """Parse JSONL and group consecutive same-role messages into logical turns."""
    with open(jsonl_path) as f:
        raw = [json.loads(line) for line in f if line.strip()]

    groups: list[tuple[str, list[str]]] = []
    for msg in raw:
        role = msg.get("role")
        if not role:
            continue
        raw_text = _extract_text(msg.get("message", {}).get("content", []))
        if not raw_text:
            continue
        if groups and groups[-1][0] == role:
            groups[-1][1].append(raw_text)
        else:
            groups.append((role, [raw_text]))

    turns: list[Turn] = []
    for role, parts in groups:
        combined = "\n\n".join(parts)
        text = _clean_user_text(combined) if role == "user" else _clean_assistant_text(combined)
        if text:
            turns.append(Turn(role=role, text=text))

    return turns


def _format_turn(turn: Turn) -> str:
    label = "[User]" if turn.role == "user" else "[Assistant]"
    return f"{label}\n{turn.text}"


def render_tail(jsonl_path: Path, turns: int = 10, chars: int = 4000) -> str:
    all_turns = load_turns(jsonl_path)
    tail = all_turns[-turns:]

    sections: list[str] = []
    total = 0
    for turn in tail:
        formatted = _format_turn(turn)
        if total + len(formatted) > chars:
            remaining = chars - total
            if remaining > 150:
                sections.append(formatted[:remaining] + "\n[...truncated]")
            break
        sections.append(formatted)
        total += len(formatted)

    return "\n\n---\n\n".join(sections)


def render_full(jsonl_path: Path) -> str:
    turns = load_turns(jsonl_path)
    return "\n\n---\n\n".join(_format_turn(t) for t in turns)

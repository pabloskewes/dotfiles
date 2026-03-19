from __future__ import annotations

import subprocess
import time

from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Header, Input, Static, TextArea

from psk.git_tui.git_ops import (
    Commit,
    do_reorder,
    do_squash,
    get_commit_detail,
    get_commits,
    get_current_branch,
    get_merge_base,
    has_uncommitted_changes,
)


class CommitDetailScreen(ModalScreen[None]):
    """Modal that shows full info for a single commit."""

    BINDINGS = [Binding("escape,enter,q", "dismiss", "Close")]

    def __init__(self, sha: str, subject: str) -> None:
        super().__init__()
        self._sha = sha
        self._subject = subject

    def compose(self) -> ComposeResult:
        with Vertical(id="detail-dialog"):
            yield Static(self._subject, id="detail-title")
            yield TextArea("Loading…", id="detail-body", read_only=True)
            yield Static("Escape / Enter / Q  close", id="detail-hint")

    def on_mount(self) -> None:
        try:
            detail = get_commit_detail(self._sha)
        except subprocess.CalledProcessError as exc:
            detail = f"Error: {exc.stderr or exc}"
        self.query_one("#detail-body", TextArea).load_text(detail)

    def action_dismiss(self) -> None:
        self.dismiss(None)


class SquashScreen(ModalScreen[str | None]):
    """Modal dialog for entering the squash commit message."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "confirm", "Confirm"),
    ]

    def __init__(self, commits: list[Commit]) -> None:
        super().__init__()
        self._commits = commits

    def compose(self) -> ComposeResult:
        default_title = self._commits[0].subject if self._commits else ""
        body = "\n".join(f"* {c.subject}" for c in self._commits)
        with Vertical(id="squash-dialog"):
            yield Static(
                f"Squash {len(self._commits)} commits", id="squash-title"
            )
            yield Static("Title")
            yield Input(value=default_title, id="title-input")
            yield Static("Description")
            yield TextArea(body, id="body-input")
            yield Static(
                "Ctrl+S confirm · Escape cancel", id="squash-hint"
            )

    def action_confirm(self) -> None:
        title = self.query_one("#title-input", Input).value.strip()
        if not title:
            self.notify("Title cannot be empty", severity="error")
            return
        body = self.query_one("#body-input", TextArea).text.strip()
        message = f"{title}\n\n{body}" if body else title
        self.dismiss(message)

    def action_cancel(self) -> None:
        self.dismiss(None)


class GitTuiApp(App[str | None]):
    """Interactive TUI for squashing and reordering git commits."""

    CSS_PATH = "styles.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("space", "toggle_select", "Select"),
        Binding("a", "select_all", "All"),
        Binding("n", "select_none", "None"),
        Binding("s", "squash", "Squash"),
        Binding("r", "apply_reorder", "Reorder"),
        Binding("enter", "show_detail", "Detail"),
        Binding("ctrl+up", "move_up", "Move ↑", show=False),
        Binding("ctrl+down", "move_down", "Move ↓", show=False),
    ]

    _DOUBLE_CLICK_THRESHOLD = 0.4

    def __init__(self, base_branch: str = "main") -> None:
        super().__init__()
        self.base_branch = base_branch
        self.base_sha: str = ""
        self.commits: list[Commit] = []
        self.selected: set[int] = set()
        self.original_shas: list[str] = []
        self._last_click: tuple[float, int, int] = (0.0, -1, -1)

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="commits")
        yield Footer()

    def on_mount(self) -> None:
        try:
            branch = get_current_branch()
            self.title = f"squash · {branch}"
            self.base_sha = get_merge_base(self.base_branch)
            self.commits = get_commits(self.base_sha)
            self.original_shas = [c.sha for c in self.commits]
        except subprocess.CalledProcessError as exc:
            msg = exc.stderr.strip() if exc.stderr else str(exc)
            self.exit(result=f"❌ git error: {msg}")
            return

        if not self.commits:
            self.exit(result=f"No commits between HEAD and {self.base_branch}")
            return

        table = self.query_one("#commits", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns(" ", "SHA", "Message", "Author")
        self._refresh_table()

    # ------------------------------------------------------------------
    # Table helpers
    # ------------------------------------------------------------------

    def _refresh_table(self) -> None:
        table = self.query_one("#commits", DataTable)
        row = table.cursor_row
        table.clear()
        for i, c in enumerate(self.commits):
            marker = "✓" if i in self.selected else " "
            table.add_row(marker, c.short_sha, c.subject, c.author, key=str(i))
        table.move_cursor(row=min(row, len(self.commits) - 1))

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def action_toggle_select(self) -> None:
        table = self.query_one("#commits", DataTable)
        idx = table.cursor_row
        self.selected.symmetric_difference_update({idx})
        self._refresh_table()

    def action_select_all(self) -> None:
        self.selected = set(range(len(self.commits)))
        self._refresh_table()

    def action_select_none(self) -> None:
        self.selected.clear()
        self._refresh_table()

    # ------------------------------------------------------------------
    # Reorder (move commits up/down)
    # ------------------------------------------------------------------

    def _swap(self, a: int, b: int) -> None:
        self.commits[a], self.commits[b] = self.commits[b], self.commits[a]
        new: set[int] = set()
        for s in self.selected:
            if s == a:
                new.add(b)
            elif s == b:
                new.add(a)
            else:
                new.add(s)
        self.selected = new

    def action_move_up(self) -> None:
        table = self.query_one("#commits", DataTable)
        idx = table.cursor_row
        if idx <= 0:
            return
        self._swap(idx, idx - 1)
        self._refresh_table()
        table.move_cursor(row=idx - 1)

    def action_move_down(self) -> None:
        table = self.query_one("#commits", DataTable)
        idx = table.cursor_row
        if idx >= len(self.commits) - 1:
            return
        self._swap(idx, idx + 1)
        self._refresh_table()
        table.move_cursor(row=idx + 1)

    @property
    def _order_changed(self) -> bool:
        return [c.sha for c in self.commits] != self.original_shas

    def action_apply_reorder(self) -> None:
        if not self._order_changed:
            self.notify("Order unchanged", severity="information")
            return
        if has_uncommitted_changes():
            self.notify(
                "Commit or stash changes before reordering", severity="error"
            )
            return
        shas_oldest_first = [c.sha for c in reversed(self.commits)]
        try:
            do_reorder(self.base_sha, shas_oldest_first)
            self.exit(result="✓ Commits reordered")
        except RuntimeError as exc:
            self.exit(result=f"❌ {exc}")

    # ------------------------------------------------------------------
    # Squash
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Commit detail
    # ------------------------------------------------------------------

    def _show_commit_detail(self, idx: int) -> None:
        if 0 <= idx < len(self.commits):
            c = self.commits[idx]
            self.push_screen(CommitDetailScreen(c.sha, c.subject))

    def action_show_detail(self) -> None:
        table = self.query_one("#commits", DataTable)
        self._show_commit_detail(table.cursor_row)

    def on_click(self, event: events.Click) -> None:
        now = time.monotonic()
        last_time, last_x, last_y = self._last_click
        same_spot = abs(event.x - last_x) < 4 and abs(event.y - last_y) < 2
        if same_spot and (now - last_time) < self._DOUBLE_CLICK_THRESHOLD:
            table = self.query_one("#commits", DataTable)
            self._show_commit_detail(table.cursor_row)
            self._last_click = (0.0, -1, -1)
        else:
            self._last_click = (now, event.x, event.y)

    def action_squash(self) -> None:
        if self._order_changed:
            self.notify(
                "Apply or reset reorder before squashing", severity="error"
            )
            return
        if not self.selected:
            self.notify("Select commits to squash (Space)", severity="warning")
            return

        indices = sorted(self.selected)
        if indices != list(range(indices[-1] + 1)):
            self.notify(
                "Select contiguous commits from the top", severity="error"
            )
            return

        selected_commits = [self.commits[i] for i in indices]

        def on_dismiss(message: str | None) -> None:
            if message is None:
                return
            try:
                do_squash(len(selected_commits), message)
                self.exit(
                    result=f"✓ Squashed {len(selected_commits)} commits"
                )
            except Exception as exc:
                self.exit(result=f"❌ Squash failed: {exc}")

        self.push_screen(SquashScreen(selected_commits), callback=on_dismiss)

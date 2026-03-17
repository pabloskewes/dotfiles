import json
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from psk.scopeo import (
    ActiveTicket,
    InitPlan,
    TicketParts,
    _build_readme_content,
    _build_workspace_payload,
    _write_text_if_missing,
    build_branch_name,
    build_init_plan,
    build_journal_folder,
    build_ticket_parts,
    find_worktree_for_ticket,
    init_scopeo_ticket,
    list_active_tickets,
    parse_ticket,
    render_summary,
    resolve_worktree_path_for_repo,
    slugify,
)


# ---------------------------------------------------------------------------
# parse_ticket
# ---------------------------------------------------------------------------


class TestParseTicket:
    def test_simple_ticket_id(self):
        project, number = parse_ticket("DRA-1049")
        assert project == "DRA"
        assert number == 1049

    def test_lowercase_input_normalized(self):
        project, number = parse_ticket("dra-1049")
        assert project == "DRA"

    def test_extracts_from_linear_url(self):
        url = "https://linear.app/draftnrun/issue/DRA-1049/my-ticket-title"
        project, number = parse_ticket(url)
        assert project == "DRA"
        assert number == 1049

    def test_extracts_from_url_without_trailing_slug(self):
        url = "https://linear.app/draftnrun/issue/BAC-42"
        project, number = parse_ticket(url)
        assert project == "BAC"
        assert number == 42

    def test_different_project_code(self):
        project, number = parse_ticket("BAC-999")
        assert project == "BAC"
        assert number == 999

    def test_invalid_string_raises(self):
        with pytest.raises(ValueError, match="Ticket must look like"):
            parse_ticket("not-a-ticket")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            parse_ticket("")


# ---------------------------------------------------------------------------
# slugify
# ---------------------------------------------------------------------------


class TestSlugify:
    def test_basic_lowercase(self):
        assert slugify("my feature") == "my-feature"

    def test_special_chars_replaced(self):
        assert slugify("Add new! Feature@2") == "add-new-feature-2"

    def test_leading_trailing_dashes_stripped(self):
        assert slugify("  ---hello---  ") == "hello"

    def test_uppercase_lowercased(self):
        assert slugify("MyBigFeature") == "mybigfeature"

    def test_multiple_separators_collapsed(self):
        assert slugify("hello   world") == "hello-world"

    def test_already_clean_input_unchanged(self):
        assert slugify("my-slug") == "my-slug"

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="Slug cannot be empty"):
            slugify("")

    def test_only_special_chars_raises(self):
        with pytest.raises(ValueError, match="Slug cannot be empty"):
            slugify("!@#$%")


# ---------------------------------------------------------------------------
# build_ticket_parts
# ---------------------------------------------------------------------------


class TestBuildTicketParts:
    def test_builds_from_ticket_id(self):
        parts = build_ticket_parts("DRA-1049", "my feature")
        assert parts.project == "DRA"
        assert parts.number == 1049
        assert parts.slug == "my-feature"
        assert parts.ticket_id == "DRA-1049"

    def test_builds_from_url(self):
        parts = build_ticket_parts(
            "https://linear.app/draftnrun/issue/DRA-42", "some task"
        )
        assert parts.ticket_id == "DRA-42"
        assert parts.slug == "some-task"

    def test_slug_is_normalized(self):
        parts = build_ticket_parts("DRA-1", "Hello World!")
        assert parts.slug == "hello-world"


# ---------------------------------------------------------------------------
# build_branch_name
# ---------------------------------------------------------------------------


class TestBuildBranchName:
    def _parts(self, project="DRA", number=1049, slug="my-feature"):
        return TicketParts(
            project=project,
            number=number,
            slug=slug,
            ticket_id=f"{project}-{number}",
        )

    def test_default_owner(self):
        branch = build_branch_name(self._parts())
        assert branch == "pablo/dra-1049-my-feature"

    def test_custom_owner(self):
        branch = build_branch_name(self._parts(), owner="alice")
        assert branch == "alice/dra-1049-my-feature"

    def test_project_code_lowercased(self):
        branch = build_branch_name(self._parts(project="BAC", number=7, slug="fix"))
        assert branch == "pablo/bac-7-fix"


# ---------------------------------------------------------------------------
# build_journal_folder
# ---------------------------------------------------------------------------


class TestBuildJournalFolder:
    def _parts(self, number, slug="some-slug"):
        return TicketParts(
            project="DRA", number=number, slug=slug, ticket_id=f"DRA-{number}"
        )

    def test_zero_padded_to_4_digits(self):
        assert build_journal_folder(self._parts(7)) == "0007-some-slug"
        assert build_journal_folder(self._parts(42)) == "0042-some-slug"
        assert build_journal_folder(self._parts(1049)) == "1049-some-slug"

    def test_includes_slug(self):
        folder = build_journal_folder(self._parts(1, slug="add-auth"))
        assert folder == "0001-add-auth"


# ---------------------------------------------------------------------------
# resolve_worktree_path_for_repo
# ---------------------------------------------------------------------------


class TestResolveWorktreePathForRepo:
    def test_default_path(self):
        repo = Path("/home/user/Scopeo/draftnrun")
        result = resolve_worktree_path_for_repo(repo, "pablo/dra-1049-my-feature")
        assert result == Path(
            "/home/user/Scopeo/draftnrun-worktrees/pablo-dra-1049-my-feature"
        )

    def test_slash_in_branch_converted(self):
        repo = Path("/repos/myrepo")
        result = resolve_worktree_path_for_repo(repo, "a/b/c")
        assert result == Path("/repos/myrepo-worktrees/a-b-c")


# ---------------------------------------------------------------------------
# build_init_plan
# ---------------------------------------------------------------------------


def _make_mock_resolve_repo(backend, notes, frontend=None):
    def side_effect(root, name):
        mapping = {
            "draftnrun": backend,
            "scopeo-notes": notes,
        }
        if frontend is not None:
            mapping["back-office"] = frontend
        if name not in mapping:
            raise ValueError(f"Unexpected repo: {name}")
        return mapping[name]

    return side_effect


class TestBuildInitPlan:
    @patch("psk.scopeo.resolve_repo")
    def test_backend_only(self, mock_resolve_repo):
        backend = Path("/Scopeo/draftnrun")
        notes = Path("/Scopeo/scopeo-notes")
        mock_resolve_repo.side_effect = _make_mock_resolve_repo(backend, notes)

        plan = build_init_plan("DRA-1049", "my-feature")

        assert plan.ticket_id == "DRA-1049"
        assert plan.branch == "pablo/dra-1049-my-feature"
        assert plan.journal_folder == "1049-my-feature"
        assert plan.frontend_repo is None
        assert plan.frontend_worktree is None

    @patch("psk.scopeo.resolve_repo")
    def test_with_frontend(self, mock_resolve_repo):
        backend = Path("/Scopeo/draftnrun")
        notes = Path("/Scopeo/scopeo-notes")
        fe = Path("/Scopeo/back-office")
        mock_resolve_repo.side_effect = _make_mock_resolve_repo(backend, notes, fe)

        plan = build_init_plan("DRA-1049", "my-feature", with_frontend=True)

        assert plan.frontend_repo == fe
        assert plan.frontend_worktree is not None

    @patch("psk.scopeo.resolve_repo")
    def test_custom_branch_override(self, mock_resolve_repo):
        backend = Path("/Scopeo/draftnrun")
        notes = Path("/Scopeo/scopeo-notes")
        mock_resolve_repo.side_effect = _make_mock_resolve_repo(backend, notes)

        plan = build_init_plan("DRA-1049", "my-feature", branch="custom/branch")

        assert plan.branch == "custom/branch"

    @patch("psk.scopeo.resolve_repo")
    def test_custom_journal_folder_override(self, mock_resolve_repo):
        backend = Path("/Scopeo/draftnrun")
        notes = Path("/Scopeo/scopeo-notes")
        mock_resolve_repo.side_effect = _make_mock_resolve_repo(backend, notes)

        plan = build_init_plan("DRA-1049", "my-feature", journal_folder="custom-folder")

        assert plan.journal_folder == "custom-folder"

    @patch("psk.scopeo.resolve_repo")
    def test_workspace_file_inside_journal_dir_by_default(self, mock_resolve_repo):
        backend = Path("/Scopeo/draftnrun")
        notes = Path("/Scopeo/scopeo-notes")
        mock_resolve_repo.side_effect = _make_mock_resolve_repo(backend, notes)

        plan = build_init_plan("DRA-1049", "my-feature")

        assert plan.workspace_file.parent == plan.journal_dir
        assert plan.workspace_file.suffix == ".code-workspace"

    @patch("psk.scopeo.resolve_repo")
    def test_custom_workspace_file_override(self, mock_resolve_repo):
        backend = Path("/Scopeo/draftnrun")
        notes = Path("/Scopeo/scopeo-notes")
        mock_resolve_repo.side_effect = _make_mock_resolve_repo(backend, notes)

        plan = build_init_plan(
            "DRA-1049", "my-feature", workspace_file="/custom/path.code-workspace"
        )

        assert plan.workspace_file == Path("/custom/path.code-workspace")

    @patch("psk.scopeo.resolve_repo")
    def test_accepts_linear_url(self, mock_resolve_repo):
        backend = Path("/Scopeo/draftnrun")
        notes = Path("/Scopeo/scopeo-notes")
        mock_resolve_repo.side_effect = _make_mock_resolve_repo(backend, notes)

        plan = build_init_plan(
            "https://linear.app/draftnrun/issue/DRA-1049/title", "my-feature"
        )

        assert plan.ticket_id == "DRA-1049"


# ---------------------------------------------------------------------------
# render_summary
# ---------------------------------------------------------------------------


def _make_plan(
    backend=Path("/Scopeo/draftnrun"),
    notes=Path("/Scopeo/scopeo-notes"),
    with_frontend=False,
):
    fe = Path("/Scopeo/back-office") if with_frontend else None
    fe_wt = Path("/Scopeo/back-office-worktrees/pablo-dra-1049") if with_frontend else None
    return InitPlan(
        ticket_id="DRA-1049",
        branch="pablo/dra-1049-my-feature",
        journal_folder="1049-my-feature",
        backend_repo=backend,
        backend_worktree=backend.parent / "draftnrun-worktrees/pablo-dra-1049-my-feature",
        frontend_repo=fe,
        frontend_worktree=fe_wt,
        notes_repo=notes,
        journal_dir=notes / "journals/1049-my-feature",
        workspace_file=notes / "journals/1049-my-feature/1049-my-feature.code-workspace",
    )


class TestRenderSummary:
    def test_contains_ticket_id(self):
        plan = _make_plan()
        output = render_summary(plan)
        assert "DRA-1049" in output

    def test_contains_branch(self):
        plan = _make_plan()
        output = render_summary(plan)
        assert "pablo/dra-1049-my-feature" in output

    def test_frontend_shown_as_dash_when_absent(self):
        plan = _make_plan(with_frontend=False)
        output = render_summary(plan)
        assert "frontend_repo" in output
        assert ": -" in output

    def test_frontend_shown_when_present(self):
        plan = _make_plan(with_frontend=True)
        output = render_summary(plan)
        assert "back-office" in output


# ---------------------------------------------------------------------------
# _build_readme_content
# ---------------------------------------------------------------------------


class TestBuildReadmeContent:
    def test_contains_yaml_frontmatter(self):
        plan = _make_plan()
        with patch("psk.scopeo.date") as mock_date:
            mock_date.today.return_value.isoformat.return_value = "2026-01-15"
            content = _build_readme_content(plan)
        assert content.startswith("---\n")
        assert "type: journal" in content

    def test_contains_ticket_id_in_frontmatter(self):
        plan = _make_plan()
        with patch("psk.scopeo.date") as mock_date:
            mock_date.today.return_value.isoformat.return_value = "2026-01-15"
            content = _build_readme_content(plan)
        assert 'id: "DRA-1049"' in content

    def test_contains_linear_url(self):
        plan = _make_plan()
        with patch("psk.scopeo.date") as mock_date:
            mock_date.today.return_value.isoformat.return_value = "2026-01-15"
            content = _build_readme_content(plan)
        assert "https://linear.app/draftnrun/issue/DRA-1049" in content

    def test_contains_branch(self):
        plan = _make_plan()
        with patch("psk.scopeo.date") as mock_date:
            mock_date.today.return_value.isoformat.return_value = "2026-01-15"
            content = _build_readme_content(plan)
        assert "pablo/dra-1049-my-feature" in content

    def test_includes_frontend_repo_when_present(self):
        plan = _make_plan(with_frontend=True)
        with patch("psk.scopeo.date") as mock_date:
            mock_date.today.return_value.isoformat.return_value = "2026-01-15"
            content = _build_readme_content(plan)
        assert "back-office" in content

    def test_no_frontend_repo_section_when_absent(self):
        plan = _make_plan(with_frontend=False)
        with patch("psk.scopeo.date") as mock_date:
            mock_date.today.return_value.isoformat.return_value = "2026-01-15"
            content = _build_readme_content(plan)
        assert "back-office" not in content

    def test_contains_started_date(self):
        plan = _make_plan()
        with patch("psk.scopeo.date") as mock_date:
            mock_date.today.return_value.isoformat.return_value = "2026-01-15"
            content = _build_readme_content(plan)
        assert "started: 2026-01-15" in content

    def test_contains_markdown_heading(self):
        plan = _make_plan()
        with patch("psk.scopeo.date") as mock_date:
            mock_date.today.return_value.isoformat.return_value = "2026-01-15"
            content = _build_readme_content(plan)
        assert "# DRA-1049" in content


# ---------------------------------------------------------------------------
# _build_workspace_payload
# ---------------------------------------------------------------------------


class TestBuildWorkspacePayload:
    def test_backend_only_has_two_folders(self):
        plan = _make_plan(with_frontend=False)
        payload = _build_workspace_payload(plan)
        assert len(payload["folders"]) == 2

    def test_with_frontend_has_three_folders(self):
        plan = _make_plan(with_frontend=True)
        payload = _build_workspace_payload(plan)
        assert len(payload["folders"]) == 3

    def test_notes_repo_always_last(self):
        plan = _make_plan(with_frontend=False)
        payload = _build_workspace_payload(plan)
        assert "scopeo-notes" in payload["folders"][-1]["name"]

    def test_backend_folder_has_emoji(self):
        plan = _make_plan()
        payload = _build_workspace_payload(plan)
        backend_entry = payload["folders"][0]
        assert "⚙️" in backend_entry["name"]
        assert "draftnrun" in backend_entry["name"]

    def test_frontend_folder_has_emoji(self):
        plan = _make_plan(with_frontend=True)
        payload = _build_workspace_payload(plan)
        frontend_entry = payload["folders"][1]
        assert "🖥️" in frontend_entry["name"]
        assert "back-office" in frontend_entry["name"]

    def test_contains_settings(self):
        plan = _make_plan()
        payload = _build_workspace_payload(plan)
        assert "settings" in payload
        assert payload["settings"]["task.allowAutomaticTasks"] == "off"

    def test_paths_are_absolute_strings(self):
        plan = _make_plan()
        payload = _build_workspace_payload(plan)
        for folder in payload["folders"]:
            assert Path(folder["path"]).is_absolute()


# ---------------------------------------------------------------------------
# _write_text_if_missing
# ---------------------------------------------------------------------------


class TestWriteTextIfMissing:
    def test_creates_file_when_missing(self, tmp_path):
        target = tmp_path / "file.md"
        _write_text_if_missing(target, "hello")
        assert target.read_text() == "hello"

    def test_does_not_overwrite_existing_file(self, tmp_path):
        target = tmp_path / "file.md"
        target.write_text("original")
        _write_text_if_missing(target, "new content")
        assert target.read_text() == "original"


# ---------------------------------------------------------------------------
# list_active_tickets
# ---------------------------------------------------------------------------

_BACKEND_PORCELAIN = (
    "worktree /Scopeo/draftnrun\n"
    "HEAD aaa0000\n"
    "branch refs/heads/main\n"
    "\n"
    "worktree /Scopeo/draftnrun-worktrees/pablo-dra-1049-my-feature\n"
    "HEAD bbb1111\n"
    "branch refs/heads/pablo/dra-1049-my-feature\n"
    "\n"
    "worktree /Scopeo/draftnrun-worktrees/pablo-bac-42-another\n"
    "HEAD ccc2222\n"
    "branch refs/heads/pablo/bac-42-another\n"
    "\n"
)

_FRONTEND_PORCELAIN = (
    "worktree /Scopeo/back-office\n"
    "HEAD ddd3333\n"
    "branch refs/heads/main\n"
    "\n"
    "worktree /Scopeo/back-office-worktrees/pablo-dra-1049-my-feature\n"
    "HEAD eee4444\n"
    "branch refs/heads/pablo/dra-1049-my-feature\n"
    "\n"
)


class TestListActiveTickets:
    def _run_side_effect(self, backend_output, frontend_output):
        def side_effect(cmd, **kwargs):
            cwd = kwargs.get("cwd")
            if cwd and "back-office" in str(cwd):
                return MagicMock(returncode=0, stdout=frontend_output)
            return MagicMock(returncode=0, stdout=backend_output)

        return side_effect

    def test_returns_active_tickets(self):
        backend_repo = Path("/Scopeo/draftnrun")
        frontend_repo = Path("/Scopeo/back-office")

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = self._run_side_effect(
                _BACKEND_PORCELAIN, _FRONTEND_PORCELAIN
            )
            tickets = list_active_tickets(backend_repo, frontend_repo)

        assert len(tickets) == 2
        ticket_ids = {t.ticket_id for t in tickets}
        assert "DRA-1049" in ticket_ids
        assert "BAC-42" in ticket_ids

    def test_has_frontend_flag_set_correctly(self):
        backend_repo = Path("/Scopeo/draftnrun")
        frontend_repo = Path("/Scopeo/back-office")

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = self._run_side_effect(
                _BACKEND_PORCELAIN, _FRONTEND_PORCELAIN
            )
            tickets = list_active_tickets(backend_repo, frontend_repo)

        by_id = {t.ticket_id: t for t in tickets}
        assert by_id["DRA-1049"].has_frontend is True
        assert by_id["BAC-42"].has_frontend is False

    def test_main_worktree_excluded(self):
        backend_repo = Path("/Scopeo/draftnrun")
        frontend_repo = Path("/Scopeo/back-office")

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = self._run_side_effect(
                _BACKEND_PORCELAIN, _FRONTEND_PORCELAIN
            )
            tickets = list_active_tickets(backend_repo, frontend_repo)

        ticket_ids = {t.ticket_id for t in tickets}
        assert all("-" in tid for tid in ticket_ids)

    def test_sorted_by_ticket_id(self):
        backend_repo = Path("/Scopeo/draftnrun")
        frontend_repo = Path("/Scopeo/back-office")

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = self._run_side_effect(
                _BACKEND_PORCELAIN, _FRONTEND_PORCELAIN
            )
            tickets = list_active_tickets(backend_repo, frontend_repo)

        ids = [t.ticket_id for t in tickets]
        assert ids == sorted(ids)

    def test_empty_when_no_worktrees(self):
        backend_repo = Path("/Scopeo/draftnrun")
        frontend_repo = Path("/Scopeo/back-office")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="worktree /Scopeo/draftnrun\nHEAD abc\nbranch refs/heads/main\n\n",
            )
            tickets = list_active_tickets(backend_repo, frontend_repo)

        assert tickets == []


# ---------------------------------------------------------------------------
# find_worktree_for_ticket
# ---------------------------------------------------------------------------

_FIND_PORCELAIN = (
    "worktree /Scopeo/draftnrun\n"
    "HEAD aaa\n"
    "branch refs/heads/main\n"
    "\n"
    "worktree /Scopeo/draftnrun-worktrees/pablo-dra-1049-my-feature\n"
    "HEAD bbb\n"
    "branch refs/heads/pablo/dra-1049\n"
    "\n"
    "worktree /Scopeo/draftnrun-worktrees/pablo-bac-42-other\n"
    "HEAD ccc\n"
    "branch refs/heads/pablo/bac-42\n"
    "\n"
)


class TestFindWorktreeForTicket:
    def test_finds_correct_worktree(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=_FIND_PORCELAIN)
            result = find_worktree_for_ticket(Path("/Scopeo/draftnrun"), "DRA-1049")

        assert result == Path(
            "/Scopeo/draftnrun-worktrees/pablo-dra-1049-my-feature"
        )

    def test_returns_none_when_not_found(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=_FIND_PORCELAIN)
            result = find_worktree_for_ticket(Path("/Scopeo/draftnrun"), "DRA-9999")

        assert result is None

    def test_matches_by_number_segment(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=_FIND_PORCELAIN)
            result = find_worktree_for_ticket(Path("/Scopeo/draftnrun"), "BAC-42")

        assert result == Path("/Scopeo/draftnrun-worktrees/pablo-bac-42-other")


# ---------------------------------------------------------------------------
# init_scopeo_ticket
# ---------------------------------------------------------------------------


@contextmanager
def _noop_chdir(_):
    yield


class TestInitScopeoTicket:
    def _make_plan(self, tmp_path: Path, with_frontend: bool = False) -> InitPlan:
        backend_repo = tmp_path / "draftnrun"
        backend_repo.mkdir()
        backend_wt = tmp_path / "draftnrun-worktrees/pablo-dra-1049-feat"
        notes_repo = tmp_path / "scopeo-notes"
        notes_repo.mkdir()
        journal_dir = notes_repo / "journals/1049-feat"
        workspace_file = journal_dir / "1049-feat.code-workspace"

        fe_repo = None
        fe_wt = None
        if with_frontend:
            fe_repo = tmp_path / "back-office"
            fe_repo.mkdir()
            fe_wt = tmp_path / "back-office-worktrees/pablo-dra-1049-feat"

        return InitPlan(
            ticket_id="DRA-1049",
            branch="pablo/dra-1049-feat",
            journal_folder="1049-feat",
            backend_repo=backend_repo,
            backend_worktree=backend_wt,
            frontend_repo=fe_repo,
            frontend_worktree=fe_wt,
            notes_repo=notes_repo,
            journal_dir=journal_dir,
            workspace_file=workspace_file,
        )

    def test_creates_journal_directory(self, tmp_path):
        plan = self._make_plan(tmp_path)

        with (
            patch("psk.scopeo.create_worktree"),
            patch("psk.scopeo._branch_exists", return_value=False),
            patch("psk.scopeo._run_setup"),
            patch("psk.scopeo.chdir", side_effect=_noop_chdir),
        ):
            init_scopeo_ticket(plan)

        assert plan.journal_dir.is_dir()

    def test_creates_readme_file(self, tmp_path):
        plan = self._make_plan(tmp_path)

        with (
            patch("psk.scopeo.create_worktree"),
            patch("psk.scopeo._branch_exists", return_value=False),
            patch("psk.scopeo._run_setup"),
            patch("psk.scopeo.chdir", side_effect=_noop_chdir),
            patch("psk.scopeo.date") as mock_date,
        ):
            mock_date.today.return_value.isoformat.return_value = "2026-01-15"
            init_scopeo_ticket(plan)

        readme = plan.journal_dir / "README.md"
        assert readme.exists()
        assert "DRA-1049" in readme.read_text()

    def test_creates_plan_file(self, tmp_path):
        plan = self._make_plan(tmp_path)

        with (
            patch("psk.scopeo.create_worktree"),
            patch("psk.scopeo._branch_exists", return_value=False),
            patch("psk.scopeo._run_setup"),
            patch("psk.scopeo.chdir", side_effect=_noop_chdir),
        ):
            init_scopeo_ticket(plan)

        assert (plan.journal_dir / "00-plan.md").exists()

    def test_creates_valid_workspace_file(self, tmp_path):
        plan = self._make_plan(tmp_path)

        with (
            patch("psk.scopeo.create_worktree"),
            patch("psk.scopeo._branch_exists", return_value=False),
            patch("psk.scopeo._run_setup"),
            patch("psk.scopeo.chdir", side_effect=_noop_chdir),
        ):
            init_scopeo_ticket(plan)

        assert plan.workspace_file.exists()
        payload = json.loads(plan.workspace_file.read_text())
        assert "folders" in payload

    def test_does_not_overwrite_existing_readme(self, tmp_path):
        plan = self._make_plan(tmp_path)
        plan.journal_dir.mkdir(parents=True, exist_ok=True)
        readme = plan.journal_dir / "README.md"
        readme.write_text("# existing content")

        with (
            patch("psk.scopeo.create_worktree"),
            patch("psk.scopeo._branch_exists", return_value=False),
            patch("psk.scopeo._run_setup"),
            patch("psk.scopeo.chdir", side_effect=_noop_chdir),
        ):
            init_scopeo_ticket(plan)

        assert readme.read_text() == "# existing content"

    def test_skips_backend_worktree_creation_when_exists(self, tmp_path):
        plan = self._make_plan(tmp_path)
        plan.backend_worktree.mkdir(parents=True)

        with (
            patch("psk.scopeo.create_worktree") as mock_create,
            patch("psk.scopeo._branch_exists", return_value=False),
            patch("psk.scopeo._run_setup"),
            patch("psk.scopeo.chdir", side_effect=_noop_chdir),
        ):
            init_scopeo_ticket(plan)

        mock_create.assert_not_called()

    def test_calls_uv_sync_after_backend_worktree(self, tmp_path):
        plan = self._make_plan(tmp_path)

        with (
            patch("psk.scopeo.create_worktree"),
            patch("psk.scopeo._branch_exists", return_value=False),
            patch("psk.scopeo._run_setup") as mock_setup,
            patch("psk.scopeo.chdir", side_effect=_noop_chdir),
        ):
            init_scopeo_ticket(plan)

        mock_setup.assert_any_call(plan.backend_worktree, ["uv", "sync"])

    def test_calls_npm_install_for_frontend(self, tmp_path):
        plan = self._make_plan(tmp_path, with_frontend=True)

        with (
            patch("psk.scopeo.create_worktree"),
            patch("psk.scopeo._branch_exists", return_value=False),
            patch("psk.scopeo._run_setup") as mock_setup,
            patch("psk.scopeo.chdir", side_effect=_noop_chdir),
        ):
            init_scopeo_ticket(plan)

        mock_setup.assert_any_call(plan.frontend_worktree, ["npm", "install"])

    def test_no_npm_install_without_frontend(self, tmp_path):
        plan = self._make_plan(tmp_path, with_frontend=False)

        with (
            patch("psk.scopeo.create_worktree"),
            patch("psk.scopeo._branch_exists", return_value=False),
            patch("psk.scopeo._run_setup") as mock_setup,
            patch("psk.scopeo.chdir", side_effect=_noop_chdir),
        ):
            init_scopeo_ticket(plan)

        all_cmds = [c.args[1] for c in mock_setup.call_args_list]
        assert not any("npm" in cmd for cmd in all_cmds)

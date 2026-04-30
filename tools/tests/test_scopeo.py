import json
import textwrap
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
from typer.testing import CliRunner

import psk.project as project_module
from psk.cli import psk_app, scopeo_app
from psk.project import ProjectConfig
from psk.scopeo import (
    InitPlan,
    TicketParts,
    _build_readme_content,
    _build_workspace_payload,
    _prepare_frontend_env,
    _write_text_if_missing,
    build_branch_name,
    build_init_plan,
    build_journal_folder,
    build_ticket_parts,
    find_worktree_for_ticket,
    find_workspace_for_ticket,
    init_scopeo_ticket,
    list_active_tickets,
    parse_ticket,
    render_summary,
    resolve_worktree_path_for_repo,
    slugify,
)
from psk.staging import StagingPlan


def _write_scopeo_config(
    config_dir: Path,
    *,
    repo: Path = Path("/Scopeo/draftnrun"),
    notes: Path = Path("/Scopeo/scopeo-notes"),
    frontend_env_source_candidates: list[Path] | None = None,
) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    frontend_candidates_block = ""
    if frontend_env_source_candidates:
        rendered = ",\n".join(f'  "{path}"' for path in frontend_env_source_candidates)
        frontend_candidates_block = f"frontend_env_source_candidates = [\n{rendered}\n]\n"

    (config_dir / "scopeo.toml").write_text(
        textwrap.dedent(
            f"""\
            name = "scopeo"
            code_repo = "{repo}"
            notes_repo = "{notes}"
            github_repo = "Scopeo/draftnrun"
            linear_workspace_url = "https://linear.app/draftnrun"
            {frontend_candidates_block}\
            """
        )
    )


class TestParseTicket:
    def test_simple_ticket_id(self):
        project, number = parse_ticket("DRA-1049")
        assert project == "DRA"
        assert number == 1049

    def test_extracts_from_linear_url(self):
        url = "https://linear.app/draftnrun/issue/DRA-1049/my-ticket-title"
        project, number = parse_ticket(url)
        assert project == "DRA"
        assert number == 1049

    def test_invalid_string_raises(self):
        with pytest.raises(ValueError, match="Ticket must look like"):
            parse_ticket("not-a-ticket")


class TestSlugify:
    def test_basic_lowercase(self):
        assert slugify("my feature") == "my-feature"

    def test_special_chars_replaced(self):
        assert slugify("Add new! Feature@2") == "add-new-feature-2"

    def test_only_special_chars_raises(self):
        with pytest.raises(ValueError, match="Slug cannot be empty"):
            slugify("!@#$%")


class TestBuildTicketParts:
    def test_builds_from_ticket_id(self):
        parts = build_ticket_parts("DRA-1049", "my feature")
        assert parts.project == "DRA"
        assert parts.number == 1049
        assert parts.slug == "my-feature"
        assert parts.ticket_id == "DRA-1049"


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


class TestBuildJournalFolder:
    def _parts(self, number, slug="some-slug"):
        return TicketParts(
            project="DRA", number=number, slug=slug, ticket_id=f"DRA-{number}"
        )

    def test_zero_padded_to_4_digits(self):
        assert build_journal_folder(self._parts(7)) == "0007-some-slug"
        assert build_journal_folder(self._parts(42)) == "0042-some-slug"


class TestResolveWorktreePathForRepo:
    def test_default_path(self):
        repo = Path("/home/user/Scopeo/draftnrun")
        result = resolve_worktree_path_for_repo(repo, "pablo/dra-1049-my-feature")
        assert result == Path(
            "/home/user/Scopeo/draftnrun-worktrees/pablo-dra-1049-my-feature"
        )

class TestBuildInitPlan:
    def test_returns_single_repo_plan(self, monkeypatch, tmp_path):
        repo = Path("/Scopeo/draftnrun")
        notes = Path("/Scopeo/scopeo-notes")
        config_dir = tmp_path / "projects"
        monkeypatch.setattr(project_module, "CONFIG_DIR", config_dir)
        _write_scopeo_config(config_dir, repo=repo, notes=notes)

        plan = build_init_plan("DRA-1049", "my-feature")

        assert plan.ticket_id == "DRA-1049"
        assert plan.branch == "pablo/dra-1049-my-feature"
        assert plan.journal_folder == "1049-my-feature"
        assert plan.repo == repo
        assert plan.worktree == Path(
            "/Scopeo/draftnrun-worktrees/pablo-dra-1049-my-feature"
        )

    def test_custom_workspace_file_override(self, monkeypatch, tmp_path):
        repo = Path("/Scopeo/draftnrun")
        notes = Path("/Scopeo/scopeo-notes")
        config_dir = tmp_path / "projects"
        monkeypatch.setattr(project_module, "CONFIG_DIR", config_dir)
        _write_scopeo_config(config_dir, repo=repo, notes=notes)

        plan = build_init_plan(
            "DRA-1049", "my-feature", workspace_file="/custom/path.code-workspace"
        )

        assert plan.workspace_file == Path("/custom/path.code-workspace")


def _make_plan(
    repo=Path("/Scopeo/draftnrun"),
    notes=Path("/Scopeo/scopeo-notes"),
):
    project = ProjectConfig(
        name="scopeo",
        code_repo=repo,
        notes_repo=notes,
        github_repo="Scopeo/draftnrun",
        linear_workspace_url="https://linear.app/draftnrun",
    )
    return InitPlan(
        ticket_id="DRA-1049",
        branch="pablo/dra-1049-my-feature",
        journal_folder="1049-my-feature",
        repo=repo,
        worktree=repo.parent / "draftnrun-worktrees/pablo-dra-1049-my-feature",
        notes_repo=notes,
        journal_dir=notes / "journals/1049-my-feature",
        workspace_file=notes / "journals/1049-my-feature/1049-my-feature.code-workspace",
        project=project,
    )


class TestRenderSummary:
    def test_contains_ticket_id(self):
        output = render_summary(_make_plan())
        assert "DRA-1049" in output

    def test_uses_repo_and_worktree_labels(self):
        output = render_summary(_make_plan())
        assert "repo" in output
        assert "worktree" in output
        assert "frontend" not in output.lower()


class TestBuildReadmeContent:
    def test_contains_yaml_frontmatter(self):
        plan = _make_plan()
        with patch("psk.ticketing.date") as mock_date:
            mock_date.today.return_value.isoformat.return_value = "2026-01-15"
            content = _build_readme_content(plan)
        assert content.startswith("---\n")
        assert 'repo: "Scopeo/draftnrun"' in content

    def test_does_not_reference_back_office(self):
        plan = _make_plan()
        with patch("psk.ticketing.date") as mock_date:
            mock_date.today.return_value.isoformat.return_value = "2026-01-15"
            content = _build_readme_content(plan)
        assert "back-office" not in content


class TestBuildWorkspacePayload:
    def test_has_two_folders(self):
        payload = _build_workspace_payload(_make_plan())
        assert len(payload["folders"]) == 2

    def test_notes_repo_is_last(self):
        payload = _build_workspace_payload(_make_plan())
        assert "scopeo-notes" in payload["folders"][-1]["name"]

    def test_paths_are_absolute_strings(self):
        payload = _build_workspace_payload(_make_plan())
        for folder in payload["folders"]:
            assert Path(folder["path"]).is_absolute()


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


class TestFindWorkspaceForTicket:
    def test_returns_workspace_when_exists(self, tmp_path):
        notes_repo = tmp_path / "scopeo-notes"
        journal_dir = notes_repo / "journals" / "1049-my-feature"
        journal_dir.mkdir(parents=True)
        workspace = journal_dir / "1049-my-feature.code-workspace"
        workspace.write_text("{}")

        worktree = tmp_path / "draftnrun-worktrees" / "pablo-dra-1049-my-feature"
        result = find_workspace_for_ticket(worktree, notes_repo)

        assert result == workspace

    def test_returns_none_for_unrecognized_path(self, tmp_path):
        notes_repo = tmp_path / "scopeo-notes"
        notes_repo.mkdir()

        result = find_workspace_for_ticket(tmp_path / "draftnrun", notes_repo)

        assert result is None


_WORKTREE_PORCELAIN = (
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


class TestListActiveTickets:
    def test_returns_active_tickets(self):
        repo = Path("/Scopeo/draftnrun")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=_WORKTREE_PORCELAIN)
            tickets = list_active_tickets(repo)

        assert [ticket.ticket_id for ticket in tickets] == ["BAC-42", "DRA-1049"]
        assert [ticket.slug for ticket in tickets] == ["another", "my-feature"]

    def test_empty_when_no_ticket_worktrees(self):
        repo = Path("/Scopeo/draftnrun")
        stdout = "worktree /Scopeo/draftnrun\nHEAD abc\nbranch refs/heads/main\n\n"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=stdout)
            tickets = list_active_tickets(repo)

        assert tickets == []


class TestFindWorktreeForTicket:
    def test_finds_correct_worktree(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=_WORKTREE_PORCELAIN)
            result = find_worktree_for_ticket(Path("/Scopeo/draftnrun"), "DRA-1049")

        assert result == Path(
            "/Scopeo/draftnrun-worktrees/pablo-dra-1049-my-feature"
        )


@contextmanager
def _noop_chdir(_):
    yield


class TestInitScopeoTicket:
    def _make_plan(self, tmp_path: Path) -> InitPlan:
        repo = tmp_path / "draftnrun"
        repo.mkdir()
        worktree = tmp_path / "draftnrun-worktrees/pablo-dra-1049-feat"
        notes_repo = tmp_path / "scopeo-notes"
        notes_repo.mkdir()
        journal_dir = notes_repo / "journals/1049-feat"
        workspace_file = journal_dir / "1049-feat.code-workspace"
        project = ProjectConfig(
            name="scopeo",
            code_repo=repo,
            notes_repo=notes_repo,
            github_repo="Scopeo/draftnrun",
            linear_workspace_url="https://linear.app/draftnrun",
        )

        return InitPlan(
            ticket_id="DRA-1049",
            branch="pablo/dra-1049-feat",
            journal_folder="1049-feat",
            repo=repo,
            worktree=worktree,
            notes_repo=notes_repo,
            journal_dir=journal_dir,
            workspace_file=workspace_file,
            project=project,
        )

    def test_creates_journal_directory(self, tmp_path):
        plan = self._make_plan(tmp_path)

        with (
            patch("psk.ticketing.create_worktree"),
            patch("psk.ticketing._branch_exists", return_value=False),
            patch("psk.ticketing._run_setup"),
            patch("psk.ticketing.chdir", side_effect=_noop_chdir),
        ):
            init_scopeo_ticket(plan)

        assert plan.journal_dir.is_dir()

    def test_creates_valid_workspace_file(self, tmp_path):
        plan = self._make_plan(tmp_path)

        with (
            patch("psk.ticketing.create_worktree"),
            patch("psk.ticketing._branch_exists", return_value=False),
            patch("psk.ticketing._run_setup"),
            patch("psk.ticketing.chdir", side_effect=_noop_chdir),
        ):
            init_scopeo_ticket(plan)

        payload = json.loads(plan.workspace_file.read_text())
        assert payload["folders"][0]["path"] == str(plan.worktree)

    def test_calls_uv_sync_after_worktree(self, tmp_path):
        plan = self._make_plan(tmp_path)

        with (
            patch("psk.ticketing.create_worktree"),
            patch("psk.ticketing._branch_exists", return_value=False),
            patch("psk.ticketing._run_setup") as mock_setup,
            patch("psk.ticketing.chdir", side_effect=_noop_chdir),
        ):
            init_scopeo_ticket(plan)

        mock_setup.assert_called_once_with(plan.worktree, ["uv", "sync"])

    def test_calls_pnpm_install_for_frontend_when_node_modules_missing(self, tmp_path):
        plan = self._make_plan(tmp_path)

        def _create_worktree_side_effect(*_args, **_kwargs):
            frontend_dir = plan.worktree / "frontend"
            frontend_dir.mkdir(parents=True)
            (frontend_dir / "package.json").write_text("{}")

        with (
            patch("psk.ticketing.create_worktree", side_effect=_create_worktree_side_effect),
            patch("psk.ticketing._branch_exists", return_value=False),
            patch("psk.ticketing._run_setup") as mock_setup,
            patch("psk.ticketing.chdir", side_effect=_noop_chdir),
        ):
            init_scopeo_ticket(plan)

        assert mock_setup.call_args_list == [
            call(plan.worktree, ["uv", "sync"]),
            call(plan.worktree / "frontend", ["pnpm", "install"]),
        ]

    def test_skips_pnpm_install_when_frontend_node_modules_exists(self, tmp_path):
        plan = self._make_plan(tmp_path)
        frontend_dir = plan.worktree / "frontend"
        frontend_dir.mkdir(parents=True)
        (frontend_dir / "package.json").write_text("{}")
        (frontend_dir / "node_modules").mkdir()

        with (
            patch("psk.ticketing.create_worktree") as mock_create,
            patch("psk.ticketing._branch_exists", return_value=False),
            patch("psk.ticketing._run_setup") as mock_setup,
            patch("psk.ticketing.chdir", side_effect=_noop_chdir),
        ):
            init_scopeo_ticket(plan)

        mock_create.assert_not_called()
        mock_setup.assert_not_called()

    def test_prepare_frontend_env_uses_configured_source_candidates(self, monkeypatch, tmp_path):
        repo = tmp_path / "draftnrun"
        (repo / "frontend").mkdir(parents=True)
        worktree = tmp_path / "draftnrun-worktrees" / "pablo-dra-1049-feat"
        frontend_dir = worktree / "frontend"
        frontend_dir.mkdir(parents=True)

        legacy_repo = tmp_path / "back-office"
        legacy_repo.mkdir()
        (legacy_repo / ".env").write_text("VITE_SCOPEO_API_URL=http://localhost:8000")

        config_dir = tmp_path / "projects"
        monkeypatch.setattr(project_module, "CONFIG_DIR", config_dir)
        _write_scopeo_config(
            config_dir,
            repo=repo,
            notes=tmp_path / "scopeo-notes",
            frontend_env_source_candidates=[legacy_repo],
        )

        _prepare_frontend_env(repo, worktree)

        frontend_env = frontend_dir / ".env"
        assert frontend_env.is_symlink()
        assert frontend_env.resolve() == (legacy_repo / ".env").resolve()

    def test_skips_worktree_creation_when_exists(self, tmp_path):
        plan = self._make_plan(tmp_path)
        plan.worktree.mkdir(parents=True)

        with (
            patch("psk.ticketing.create_worktree") as mock_create,
            patch("psk.ticketing._branch_exists", return_value=False),
            patch("psk.ticketing._run_setup"),
            patch("psk.ticketing.chdir", side_effect=_noop_chdir),
        ):
            init_scopeo_ticket(plan)

        mock_create.assert_not_called()


class TestTicketCli:
    runner = CliRunner()

    def test_ticket_init_help_does_not_show_frontend(self):
        result = self.runner.invoke(psk_app, ["ticket", "init", "--help"])
        assert result.exit_code == 0
        assert "--frontend" not in result.output

    def test_ticket_init_dry_run_outputs_single_worktree_summary(self):
        plan = _make_plan()

        with (
            patch("psk.cli.resolve_project", return_value=MagicMock()),
            patch("psk.cli.build_init_plan", return_value=plan),
        ):
            result = self.runner.invoke(
                psk_app,
                ["ticket", "init", "DRA-1049", "my-feature", "--dry-run"],
            )

        assert result.exit_code == 0
        assert "worktree" in result.output
        assert "frontend" not in result.output.lower()

    def test_ticket_open_opens_one_terminal_and_workspace(self):
        worktree = Path("/Scopeo/draftnrun-worktrees/pablo-dra-1049-my-feature")
        workspace = Path(
            "/Scopeo/scopeo-notes/journals/1049-my-feature/1049-my-feature.code-workspace"
        )
        project = MagicMock(code_repo=Path("/Scopeo/draftnrun"))
        project.notes_repo = Path("/Scopeo/scopeo-notes")
        project.journals_dir = "journals"

        with (
            patch("psk.cli.resolve_project", return_value=project),
            patch("psk.cli.find_worktree_for_ticket", return_value=worktree),
            patch("psk.cli.find_workspace_for_ticket", return_value=workspace),
            patch("psk.cli.shutil.which", return_value="/usr/local/bin/cursor"),
            patch("psk.cli.subprocess.run") as mock_run,
        ):
            result = self.runner.invoke(psk_app, ["ticket", "open", "DRA-1049"])

        assert result.exit_code == 0
        assert [call.args[0] for call in mock_run.call_args_list] == [
            ["open", "-a", "Terminal", str(worktree)],
            ["/usr/local/bin/cursor", str(workspace)],
        ]

    def test_ticket_list_uses_inferred_project_repo(self):
        project = MagicMock(code_repo=Path("/Scopeo/draftnrun"))
        tickets = [
            MagicMock(ticket_id="DRA-1049", slug="my-feature"),
            MagicMock(ticket_id="DRA-1050", slug="other-feature"),
        ]

        with (
            patch("psk.cli.resolve_project", return_value=project),
            patch("psk.cli.list_active_tickets", return_value=tickets),
        ):
            result = self.runner.invoke(psk_app, ["ticket", "list"])

        assert result.exit_code == 0
        assert "DRA-1049" in result.output
        assert "other-feature" in result.output


class TestScopeoCli:
    runner = CliRunner()

    def test_staging_help_shows_push_flag(self):
        result = self.runner.invoke(scopeo_app, ["staging", "--help"])

        assert result.exit_code == 0
        assert "--push" in result.output
        assert "--no-push" not in result.output

    def test_staging_defaults_to_local_only(self):
        plan = StagingPlan(
            feature_branch="pablo/dra-1049-my-feature",
            target_branch="staging",
            target_worktree=Path("/Scopeo/draftnrun-worktrees/staging"),
            feature_head_sha="abcdef123456",
            patch_base_sha="1111111",
            source_base_sha="2222222",
            target_remote_sha="1234567890abcdef",
            diff_stat=" file.txt | 1 +\n 1 file changed, 1 insertion(+)",
            changed_files=["file.txt"],
            commit_subjects=["bugfix"],
        )

        with (
            patch("psk.staging.build_staging_plan", return_value=plan),
            patch("psk.staging.execute_staging", return_value="fedcba987654"),
        ):
            result = self.runner.invoke(
                scopeo_app,
                ["staging", "--message", "deploy", "--yes"],
            )

        assert result.exit_code == 0
        assert "(local only" in result.output
        assert "run with --push to push" in result.output

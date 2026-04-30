"""Tests for psk.setup -- SymlinkStep, RunStep, SetupConfig, run_project_setup, parse_setup_config."""
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from psk.setup import (
    RunStep,
    SetupConfig,
    SymlinkStep,
    parse_setup_config,
    run_project_setup,
)


# ---------------------------------------------------------------------------
# parse_setup_config
# ---------------------------------------------------------------------------


class TestParseSetupConfig:
    def test_empty_data_returns_empty_config(self):
        config = parse_setup_config({})
        assert config.is_empty()

    def test_no_setup_key_returns_empty_config(self):
        config = parse_setup_config({"name": "foo"})
        assert config.is_empty()

    def test_parses_single_symlink_step_with_string_source(self):
        data = {
            "setup": {
                "symlinks": [
                    {"source": ".", "target": ".", "files": [".env", "credentials.env"]}
                ]
            }
        }
        config = parse_setup_config(data)
        assert len(config.symlinks) == 1
        step = config.symlinks[0]
        assert step.sources == (".",)
        assert step.target == "."
        assert step.files == (".env", "credentials.env")

    def test_parses_symlink_step_with_list_source(self):
        data = {
            "setup": {
                "symlinks": [
                    {
                        "source": ["frontend", "~/other/path"],
                        "target": "frontend",
                        "files": [".env"],
                    }
                ]
            }
        }
        config = parse_setup_config(data)
        step = config.symlinks[0]
        assert step.sources == ("frontend", "~/other/path")
        assert step.target == "frontend"

    def test_symlink_step_target_defaults_to_dot(self):
        data = {
            "setup": {
                "symlinks": [{"source": ".", "files": [".env"]}]
            }
        }
        config = parse_setup_config(data)
        assert config.symlinks[0].target == "."

    def test_parses_run_step_minimal(self):
        data = {"setup": {"run": [{"argv": ["uv", "sync"]}]}}
        config = parse_setup_config(data)
        assert len(config.run) == 1
        step = config.run[0]
        assert step.argv == ("uv", "sync")
        assert step.cwd == "."
        assert step.if_exists is None
        assert step.skip_if_exists is None

    def test_parses_run_step_with_all_fields(self):
        data = {
            "setup": {
                "run": [
                    {
                        "argv": ["pnpm", "install"],
                        "cwd": "frontend",
                        "if_exists": "package.json",
                        "skip_if_exists": "node_modules",
                    }
                ]
            }
        }
        config = parse_setup_config(data)
        step = config.run[0]
        assert step.argv == ("pnpm", "install")
        assert step.cwd == "frontend"
        assert step.if_exists == "package.json"
        assert step.skip_if_exists == "node_modules"

    def test_parses_multiple_symlink_and_run_steps(self):
        data = {
            "setup": {
                "symlinks": [
                    {"source": ".", "target": ".", "files": [".env"]},
                    {"source": "frontend", "target": "frontend", "files": [".env"]},
                ],
                "run": [
                    {"argv": ["uv", "sync"]},
                    {"argv": ["pnpm", "install"], "cwd": "frontend"},
                ],
            }
        }
        config = parse_setup_config(data)
        assert len(config.symlinks) == 2
        assert len(config.run) == 2

    def test_invalid_symlink_source_type_raises(self):
        data = {"setup": {"symlinks": [{"source": 123, "files": [".env"]}]}}
        with pytest.raises(ValueError, match="source"):
            parse_setup_config(data)

    def test_missing_argv_raises(self):
        data = {"setup": {"run": [{"cwd": "frontend"}]}}
        with pytest.raises(ValueError, match="argv"):
            parse_setup_config(data)

    def test_invalid_argv_type_raises(self):
        data = {"setup": {"run": [{"argv": "uv sync"}]}}
        with pytest.raises(ValueError, match="argv"):
            parse_setup_config(data)


# ---------------------------------------------------------------------------
# run_project_setup -- symlink steps
# ---------------------------------------------------------------------------


class TestRunProjectSetupSymlinks:
    def test_creates_symlink_for_existing_file(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".env").write_text("SECRET=1")

        worktree = tmp_path / "worktree"
        worktree.mkdir()

        config = SetupConfig(
            symlinks=(SymlinkStep(sources=(".",), target=".", files=(".env",)),)
        )
        run_project_setup(worktree, repo, config)

        link = worktree / ".env"
        assert link.is_symlink()
        assert link.resolve() == (repo / ".env").resolve()

    def test_skips_file_not_in_source_dir(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()

        worktree = tmp_path / "worktree"
        worktree.mkdir()

        config = SetupConfig(
            symlinks=(SymlinkStep(sources=(".",), target=".", files=(".env",)),)
        )
        run_project_setup(worktree, repo, config)

        assert not (worktree / ".env").exists()

    def test_skips_existing_symlink_at_destination(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".env").write_text("SECRET=1")

        worktree = tmp_path / "worktree"
        worktree.mkdir()
        existing = worktree / ".env"
        existing.write_text("already here")

        config = SetupConfig(
            symlinks=(SymlinkStep(sources=(".",), target=".", files=(".env",)),)
        )
        run_project_setup(worktree, repo, config)

        assert not existing.is_symlink()
        assert existing.read_text() == "already here"

    def test_creates_parent_dirs_for_nested_target(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "local.mdc").write_text("# rule")

        worktree = tmp_path / "worktree"
        worktree.mkdir()

        config = SetupConfig(
            symlinks=(
                SymlinkStep(sources=(".",), target=".cursor/rules", files=("local.mdc",)),
            )
        )
        run_project_setup(worktree, repo, config)

        link = worktree / ".cursor" / "rules" / "local.mdc"
        assert link.is_symlink()

    def test_candidate_sources_uses_first_existing(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()

        primary = tmp_path / "primary"
        primary.mkdir()
        (primary / ".env").write_text("FROM_PRIMARY=1")

        secondary = tmp_path / "secondary"
        secondary.mkdir()
        (secondary / ".env").write_text("FROM_SECONDARY=1")

        worktree = tmp_path / "worktree"
        worktree.mkdir()

        config = SetupConfig(
            symlinks=(
                SymlinkStep(
                    sources=(str(primary), str(secondary)),
                    target=".",
                    files=(".env",),
                ),
            )
        )
        run_project_setup(worktree, repo, config)

        link = worktree / ".env"
        assert link.is_symlink()
        assert link.resolve() == (primary / ".env").resolve()

    def test_candidate_sources_falls_through_to_second_when_first_missing(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()

        secondary = tmp_path / "secondary"
        secondary.mkdir()
        (secondary / ".env").write_text("FROM_SECONDARY=1")

        worktree = tmp_path / "worktree"
        worktree.mkdir()

        config = SetupConfig(
            symlinks=(
                SymlinkStep(
                    sources=(str(tmp_path / "nonexistent"), str(secondary)),
                    target=".",
                    files=(".env",),
                ),
            )
        )
        run_project_setup(worktree, repo, config)

        link = worktree / ".env"
        assert link.is_symlink()
        assert link.resolve() == (secondary / ".env").resolve()

    def test_relative_source_resolves_against_repo_root(self, tmp_path):
        repo = tmp_path / "repo"
        frontend_src = repo / "frontend"
        frontend_src.mkdir(parents=True)
        (frontend_src / ".env").write_text("VITE_URL=http://localhost:8000")

        worktree = tmp_path / "worktree"
        (worktree / "frontend").mkdir(parents=True)

        config = SetupConfig(
            symlinks=(
                SymlinkStep(sources=("frontend",), target="frontend", files=(".env",)),
            )
        )
        run_project_setup(worktree, repo, config)

        link = worktree / "frontend" / ".env"
        assert link.is_symlink()
        assert link.resolve() == (frontend_src / ".env").resolve()


# ---------------------------------------------------------------------------
# run_project_setup -- run steps
# ---------------------------------------------------------------------------


class TestRunProjectSetupRun:
    def test_runs_command(self, tmp_path):
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        config = SetupConfig(run=(RunStep(argv=("uv", "sync")),))

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            run_project_setup(worktree, tmp_path / "repo", config)

        mock_run.assert_called_once_with(["uv", "sync"], cwd=worktree)

    def test_cwd_is_relative_to_worktree(self, tmp_path):
        worktree = tmp_path / "worktree"
        frontend = worktree / "frontend"
        frontend.mkdir(parents=True)

        config = SetupConfig(run=(RunStep(argv=("pnpm", "install"), cwd="frontend"),))

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            run_project_setup(worktree, tmp_path / "repo", config)

        mock_run.assert_called_once_with(["pnpm", "install"], cwd=frontend)

    def test_skips_when_if_exists_file_is_missing(self, tmp_path):
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        config = SetupConfig(
            run=(RunStep(argv=("pnpm", "install"), if_exists="package.json"),)
        )

        with patch("subprocess.run") as mock_run:
            run_project_setup(worktree, tmp_path / "repo", config)

        mock_run.assert_not_called()

    def test_runs_when_if_exists_file_is_present(self, tmp_path):
        worktree = tmp_path / "worktree"
        worktree.mkdir()
        (worktree / "package.json").write_text("{}")

        config = SetupConfig(
            run=(RunStep(argv=("pnpm", "install"), if_exists="package.json"),)
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            run_project_setup(worktree, tmp_path / "repo", config)

        mock_run.assert_called_once()

    def test_skips_when_skip_if_exists_is_present(self, tmp_path):
        worktree = tmp_path / "worktree"
        worktree.mkdir()
        (worktree / "node_modules").mkdir()

        config = SetupConfig(
            run=(RunStep(argv=("pnpm", "install"), skip_if_exists="node_modules"),)
        )

        with patch("subprocess.run") as mock_run:
            run_project_setup(worktree, tmp_path / "repo", config)

        mock_run.assert_not_called()

    def test_runs_when_skip_if_exists_is_absent(self, tmp_path):
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        config = SetupConfig(
            run=(RunStep(argv=("pnpm", "install"), skip_if_exists="node_modules"),)
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            run_project_setup(worktree, tmp_path / "repo", config)

        mock_run.assert_called_once()

    def test_non_zero_exit_does_not_raise(self, tmp_path):
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        config = SetupConfig(run=(RunStep(argv=("false",)),))

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            run_project_setup(worktree, tmp_path / "repo", config)  # should not raise

    def test_empty_config_runs_nothing(self, tmp_path):
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        with patch("subprocess.run") as mock_run:
            run_project_setup(worktree, tmp_path / "repo", SetupConfig())

        mock_run.assert_not_called()

    def test_if_exists_and_skip_if_exists_relative_to_cwd(self, tmp_path):
        worktree = tmp_path / "worktree"
        frontend = worktree / "frontend"
        frontend.mkdir(parents=True)
        (frontend / "package.json").write_text("{}")

        config = SetupConfig(
            run=(
                RunStep(
                    argv=("pnpm", "install"),
                    cwd="frontend",
                    if_exists="package.json",
                    skip_if_exists="node_modules",
                ),
            )
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            run_project_setup(worktree, tmp_path / "repo", config)

        mock_run.assert_called_once_with(["pnpm", "install"], cwd=frontend)

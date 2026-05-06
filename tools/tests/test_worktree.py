from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from psk.worktree import (
    create_worktree,
    get_repo_root,
    list_worktrees,
    remove_worktree,
    resolve_worktree_path,
)

# ---------------------------------------------------------------------------
# get_repo_root
# ---------------------------------------------------------------------------


class TestGetRepoRoot:
    def test_returns_path_on_success(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="/home/user/repo\n")
            result = get_repo_root()
        assert result == Path("/home/user/repo")

    def test_strips_trailing_newline(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="/some/path/with/spaces \n"
            )
            result = get_repo_root()
        assert result == Path("/some/path/with/spaces")

    def test_raises_when_not_in_repo(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=128, stdout="")
            with pytest.raises(RuntimeError, match="Not inside a git repository"):
                get_repo_root()

    def test_calls_correct_git_command(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="/repo\n")
            get_repo_root()
        mock_run.assert_called_once_with(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
        )


# ---------------------------------------------------------------------------
# resolve_worktree_path
# ---------------------------------------------------------------------------


class TestResolveWorktreePath:
    def test_explicit_path_returns_as_is(self):
        result = resolve_worktree_path("main", worktree_path="/tmp/my-wt")
        assert result == Path("/tmp/my-wt")

    def test_explicit_path_ignores_branch_name(self):
        result = resolve_worktree_path("feature/foo", worktree_path="/custom/path")
        assert result == Path("/custom/path")

    def test_both_options_raises(self):
        with pytest.raises(ValueError):
            resolve_worktree_path(
                "main",
                worktrees_dir="/some/dir",
                worktree_path="/some/path",
            )

    def test_default_path_derived_from_repo_root(self):
        with patch(
            "psk.worktree.get_repo_root", return_value=Path("/home/user/myrepo")
        ):
            result = resolve_worktree_path("main")
        assert result == Path("/home/user/myrepo-worktrees/main")

    def test_custom_worktrees_dir(self):
        with patch("psk.worktree.get_repo_root", return_value=Path("/repo")):
            result = resolve_worktree_path("feature/foo", worktrees_dir="/custom/dir")
        assert result == Path("/custom/dir/feature-foo")

    def test_slash_in_branch_name_converted_to_dash(self):
        with patch("psk.worktree.get_repo_root", return_value=Path("/repo")):
            result = resolve_worktree_path("pablo/dra-1049-my-feature")
        assert result == Path("/repo-worktrees/pablo-dra-1049-my-feature")

    def test_multiple_slashes_in_branch_name(self):
        with patch("psk.worktree.get_repo_root", return_value=Path("/repo")):
            result = resolve_worktree_path("a/b/c")
        assert result == Path("/repo-worktrees/a-b-c")


# ---------------------------------------------------------------------------
# list_worktrees
# ---------------------------------------------------------------------------


_PORCELAIN_TWO_ENTRIES = (
    "worktree /home/user/myrepo\n"
    "HEAD abc1234def5678\n"
    "branch refs/heads/main\n"
    "\n"
    "worktree /home/user/myrepo-worktrees/feature-x\n"
    "HEAD 9999999abcdef\n"
    "branch refs/heads/feature/x\n"
    "\n"
)

_PORCELAIN_NO_TRAILING_BLANK = (
    "worktree /home/user/myrepo\n" "HEAD abc1234def5678\n" "branch refs/heads/main\n"
)


class TestListWorktrees:
    def _mock_run(self, stdout: str):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=stdout)
            return list_worktrees()

    def test_parses_two_entries(self):
        result = self._mock_run(_PORCELAIN_TWO_ENTRIES)
        assert len(result) == 2

    def test_path_parsed_correctly(self):
        result = self._mock_run(_PORCELAIN_TWO_ENTRIES)
        assert result[0]["path"] == "/home/user/myrepo"
        assert result[1]["path"] == "/home/user/myrepo-worktrees/feature-x"

    def test_branch_strips_refs_heads_prefix(self):
        result = self._mock_run(_PORCELAIN_TWO_ENTRIES)
        assert result[0]["branch"] == "main"
        assert result[1]["branch"] == "feature/x"

    def test_sha_truncated_to_7_chars(self):
        result = self._mock_run(_PORCELAIN_TWO_ENTRIES)
        assert result[0]["sha"] == "abc1234"
        assert result[1]["sha"] == "9999999"

    def test_empty_output_returns_empty_list(self):
        result = self._mock_run("")
        assert result == []

    def test_last_entry_without_trailing_blank_line(self):
        result = self._mock_run(_PORCELAIN_NO_TRAILING_BLANK)
        assert len(result) == 1
        assert result[0]["path"] == "/home/user/myrepo"
        assert result[0]["branch"] == "main"

    def test_raises_on_git_failure(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            with pytest.raises(RuntimeError, match="Failed to list worktrees"):
                list_worktrees()


# ---------------------------------------------------------------------------
# create_worktree
# ---------------------------------------------------------------------------


class TestCreateWorktree:
    def test_cmd_without_new_branch(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0),
                MagicMock(returncode=0),
                MagicMock(returncode=0, stdout="origin/main\n"),
                MagicMock(returncode=0),
            ]
            create_worktree("main", Path("/tmp/wt"))

        first_call_args = mock_run.call_args_list[0][0][0]
        assert first_call_args == ["git", "worktree", "add", "/tmp/wt", "main"]

    def test_cmd_with_new_branch(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0),
                MagicMock(returncode=1),
                MagicMock(returncode=0, stdout=""),
            ]
            create_worktree("feature/foo", Path("/tmp/wt"), new_branch=True)

        first_call_args = mock_run.call_args_list[0][0][0]
        assert first_call_args == [
            "git",
            "worktree",
            "add",
            "-b",
            "feature/foo",
            "/tmp/wt",
        ]

    def test_raises_system_exit_on_git_failure(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            with pytest.raises(SystemExit):
                create_worktree("main", Path("/tmp/wt"))

    def test_sets_upstream_when_unique_remote_exists(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0),
                MagicMock(returncode=1),
                MagicMock(returncode=0, stdout="origin/staging\n"),
                MagicMock(returncode=0),
            ]
            create_worktree("staging", Path("/tmp/wt"))

        calls = [c[0][0] for c in mock_run.call_args_list]
        assert calls[3] == [
            "git",
            "branch",
            "--set-upstream-to",
            "origin/staging",
            "staging",
        ]

    def test_skips_upstream_when_already_configured(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0),
                MagicMock(returncode=0),
            ]
            create_worktree("staging", Path("/tmp/wt"))

        calls = [c[0][0] for c in mock_run.call_args_list]
        assert calls == [
            ["git", "worktree", "add", "/tmp/wt", "staging"],
            ["git", "rev-parse", "--abbrev-ref", "staging@{upstream}"],
        ]

    def test_skips_upstream_when_remote_is_ambiguous(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0),
                MagicMock(returncode=1),
                MagicMock(returncode=0, stdout="origin/staging\nfork/staging\n"),
            ]
            create_worktree("staging", Path("/tmp/wt"))

        calls = [c[0][0] for c in mock_run.call_args_list]
        assert calls == [
            ["git", "worktree", "add", "/tmp/wt", "staging"],
            ["git", "rev-parse", "--abbrev-ref", "staging@{upstream}"],
            ["git", "for-each-ref", "refs/remotes", "--format=%(refname:short)"],
        ]


# ---------------------------------------------------------------------------
# remove_worktree
# ---------------------------------------------------------------------------


class TestRemoveWorktree:
    def test_calls_remove_then_prune(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            remove_worktree(Path("/tmp/wt"))

        calls = [c[0][0] for c in mock_run.call_args_list]
        assert calls[0] == ["git", "worktree", "remove", "/tmp/wt"]
        assert calls[1] == ["git", "worktree", "prune"]

    def test_raises_system_exit_on_remove_failure(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            with pytest.raises(SystemExit):
                remove_worktree(Path("/tmp/wt"))

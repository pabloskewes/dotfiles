import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from psk.staging import (
    StagingPlan,
    _apply_patch,
    _build_deploy_commit_message,
    _find_worktree_path,
    build_staging_plan,
    execute_staging,
)


def _init_repo(path: Path, initial_branch: str = "main") -> None:
    subprocess.run(["git", "init", "-b", initial_branch, str(path)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "t@t.co"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "commit.gpgsign", "false"], check=True)


def _commit_file(path: Path, name: str, content: str, msg: str) -> str:
    (path / name).write_text(content)
    subprocess.run(["git", "-C", str(path), "add", name], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-m", msg], check=True, capture_output=True)
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


@pytest.fixture
def repo_with_origin(tmp_path, monkeypatch):
    """Set up a feature repo with an origin remote and a staging worktree.

    Layout:
      tmp_path/origin.git            (bare remote)
      tmp_path/feature               (main repo, feature branch checked out)
      tmp_path/staging-wt            (worktree for 'staging' branch)
    """
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(bare)], check=True, capture_output=True)

    feature = tmp_path / "feature"
    _init_repo(feature)
    _commit_file(feature, "a.txt", "base\n", "base")
    subprocess.run(
        ["git", "-C", str(feature), "remote", "add", "origin", str(bare)],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(feature), "push", "-u", "origin", "main"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(feature), "checkout", "-b", "staging"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(feature), "push", "-u", "origin", "staging"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(feature), "checkout", "-b", "pablo/dra-1-feat", "main"],
        check=True, capture_output=True,
    )

    staging_wt = tmp_path / "staging-wt"
    subprocess.run(
        ["git", "-C", str(feature), "worktree", "add", str(staging_wt), "staging"],
        check=True, capture_output=True,
    )

    monkeypatch.chdir(feature)
    return feature, staging_wt, bare


class TestBuildStagingPlan:
    def test_rejects_uncommitted_changes(self, repo_with_origin):
        feature, _, _ = repo_with_origin
        (feature / "dirty.txt").write_text("x")
        with pytest.raises(ValueError, match="uncommitted changes"):
            build_staging_plan("staging")

    def test_rejects_protected_source_branch(self, repo_with_origin):
        feature, _, _ = repo_with_origin
        subprocess.run(["git", "checkout", "main"], cwd=feature, check=True, capture_output=True)
        with pytest.raises(ValueError, match="protected branch"):
            build_staging_plan("staging")

    def test_rejects_missing_target_worktree(self, repo_with_origin):
        feature, staging_wt, _ = repo_with_origin
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(staging_wt)],
            cwd=feature, check=True, capture_output=True,
        )
        with pytest.raises(ValueError, match="No worktree found"):
            build_staging_plan("staging")

    def test_rejects_empty_delta(self, repo_with_origin):
        with pytest.raises(ValueError, match="Nothing to deploy"):
            build_staging_plan("staging")

    def test_builds_plan_with_delta_and_worktree(self, repo_with_origin):
        feature, staging_wt, _ = repo_with_origin
        _commit_file(feature, "b.txt", "new\n", "add b")

        plan = build_staging_plan("staging")

        assert plan.feature_branch == "pablo/dra-1-feat"
        assert plan.target_branch == "staging"
        assert plan.target_worktree == staging_wt
        assert plan.patch_base_sha == plan.source_base_sha
        assert "b.txt" in plan.changed_files
        assert plan.commit_subjects == ["add b"]

    def test_uses_feature_delta_instead_of_staging_delta(self, repo_with_origin):
        feature, _, bare = repo_with_origin
        subprocess.run(
            ["git", "-C", str(feature), "checkout", "main"],
            check=True,
            capture_output=True,
        )
        _commit_file(feature, "main-only.txt", "main\n", "advance main")
        subprocess.run(
            ["git", "-C", str(feature), "push", "origin", "main"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(feature), "checkout", "pablo/dra-1-feat"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(feature), "merge", "--ff-only", "origin/main"],
            check=True,
            capture_output=True,
        )
        _commit_file(feature, "feature.txt", "feature\n", "feature change")

        plan = build_staging_plan("staging")

        assert "feature.txt" in plan.changed_files
        assert "main-only.txt" not in plan.changed_files
        assert plan.commit_subjects == ["feature change"]


class TestFindWorktreePath:
    def test_returns_path_when_branch_is_checked_out(self, repo_with_origin):
        _, staging_wt, _ = repo_with_origin
        assert _find_worktree_path("staging") == staging_wt

    def test_returns_none_for_unknown_branch(self, repo_with_origin):
        assert _find_worktree_path("does-not-exist") is None


class TestApplyPatch:
    def test_saves_patch_and_raises_on_conflict(self, repo_with_origin, tmp_path):
        _, staging_wt, _ = repo_with_origin
        patch_bytes = b"not a valid patch\n"
        with pytest.raises(RuntimeError, match="Patch did not apply cleanly"):
            _apply_patch(staging_wt, patch_bytes)


class TestExecuteStaging:
    def test_applies_delta_commits_and_pushes(self, repo_with_origin):
        feature, staging_wt, bare = repo_with_origin
        _commit_file(feature, "b.txt", "hello\n", "add b")

        plan = build_staging_plan("staging")
        sha = execute_staging(plan, "deploy: add b", push=True)

        staging_head = subprocess.run(
            ["git", "-C", str(staging_wt), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        assert staging_head == sha
        assert (staging_wt / "b.txt").read_text() == "hello\n"

        remote_sha = subprocess.run(
            ["git", "-C", str(bare), "rev-parse", "refs/heads/staging"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        assert remote_sha == sha

        body = subprocess.run(
            ["git", "-C", str(staging_wt), "log", "-1", "--format=%B"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert "source-branch: pablo/dra-1-feat" in body
        assert "source-base:" in body
        assert "source-head:" in body

    def test_local_only_when_push_false(self, repo_with_origin):
        feature, staging_wt, bare = repo_with_origin
        _commit_file(feature, "b.txt", "hello\n", "add b")
        remote_before = subprocess.run(
            ["git", "-C", str(bare), "rev-parse", "refs/heads/staging"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()

        plan = build_staging_plan("staging")
        sha = execute_staging(plan, "deploy: add b", push=False)

        remote_after = subprocess.run(
            ["git", "-C", str(bare), "rev-parse", "refs/heads/staging"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        assert remote_before == remote_after
        local_sha = subprocess.run(
            ["git", "-C", str(staging_wt), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        assert local_sha == sha

    def test_incremental_deploy_applies_only_new_delta(self, repo_with_origin):
        """Second run after a partial staging deploy applies only the new changes.

        Simulates the scenario the user hit: feature has N commits, M are already
        on staging, the next deploy should apply only the (N-M) delta without
        conflicts and without force-push.
        """
        feature, staging_wt, _ = repo_with_origin
        _commit_file(feature, "b.txt", "v1\n", "add b v1")
        plan1 = build_staging_plan("staging")
        execute_staging(plan1, "deploy b v1", push=True)

        _commit_file(feature, "c.txt", "c\n", "add c")
        (feature / "b.txt").write_text("v2\n")
        subprocess.run(["git", "-C", str(feature), "add", "b.txt"], check=True)
        subprocess.run(
            ["git", "-C", str(feature), "commit", "-m", "bump b v2"],
            check=True, capture_output=True,
        )

        plan2 = build_staging_plan("staging")
        assert "b.txt" in plan2.changed_files
        assert "c.txt" in plan2.changed_files

        execute_staging(plan2, "deploy b v2 + c", push=True)
        assert (staging_wt / "b.txt").read_text() == "v2\n"
        assert (staging_wt / "c.txt").read_text() == "c\n"

        body = subprocess.run(
            ["git", "-C", str(staging_wt), "log", "-1", "--format=%B"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        source_head = subprocess.run(
            ["git", "-C", str(feature), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert f"source-head: {source_head}" in body

    def test_restores_worktree_when_patch_fails(self, repo_with_origin):
        feature, staging_wt, _ = repo_with_origin
        _commit_file(feature, "b.txt", "hello\n", "add b")
        plan = build_staging_plan("staging")

        with patch("psk.staging._diff_patch", return_value=b"garbage patch\n"):
            with pytest.raises(RuntimeError, match="Patch did not apply cleanly"):
                execute_staging(plan, "should fail", push=False)

        status = subprocess.run(
            ["git", "-C", str(staging_wt), "status", "--porcelain"],
            capture_output=True, text=True, check=True,
        ).stdout
        assert status == ""


class TestCommitMessageMetadata:
    def test_appends_requested_metadata_keys(self):
        plan = StagingPlan(
            feature_branch="pablo/dra-1-feat",
            target_branch="staging",
            target_worktree=Path("/tmp/staging"),
            feature_head_sha="abc123",
            patch_base_sha="def456",
            source_base_sha="fedcba",
            target_remote_sha="123abc",
            diff_stat="",
            changed_files=[],
            commit_subjects=[],
        )

        message = _build_deploy_commit_message("deploy fix", plan)

        assert "source-branch: pablo/dra-1-feat" in message
        assert "source-head: abc123" in message
        assert "source-base: fedcba" in message

from pathlib import Path
from unittest.mock import patch

import psk.cursor as cursor_module
from psk.project import ProjectConfig


def test_workspace_for_dir_respects_project_journals_dir(tmp_path):
    notes_repo = tmp_path / "scopeo-notes"
    journal_dir = notes_repo / "ticket-journals" / "1049-my-feature"
    journal_dir.mkdir(parents=True)
    workspace = journal_dir / "1049-my-feature.code-workspace"
    workspace.write_text("{}")

    worktree = tmp_path / "draftnrun-worktrees" / "pablo-dra-1049-my-feature"
    worktree.mkdir(parents=True)

    project = ProjectConfig(
        name="scopeo",
        code_repo=tmp_path / "draftnrun",
        notes_repo=notes_repo,
        github_repo="Scopeo/draftnrun",
        linear_workspace_url="https://linear.app/draftnrun",
        journals_dir="ticket-journals",
    )

    with patch.object(cursor_module, "list_projects", return_value={"scopeo": project}):
        assert cursor_module._workspace_for_dir(worktree) == workspace

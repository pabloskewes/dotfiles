import textwrap
from pathlib import Path

import pytest

import psk.project as project_module
from psk.project import resolve_project


def _write_project_config(
    config_dir: Path,
    *,
    name: str,
    code_repo: str,
    notes_repo: str,
    github_repo: str,
    linear_workspace_url: str,
    extra: str = "",
) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / f"{name}.toml").write_text(
        textwrap.dedent(
            f"""\
            name = "{name}"
            code_repo = "{code_repo}"
            notes_repo = "{notes_repo}"
            github_repo = "{github_repo}"
            linear_workspace_url = "{linear_workspace_url}"
            {extra}
            """
        )
    )


class TestResolveProject:
    def test_errors_when_no_projects_are_configured(self, monkeypatch, tmp_path):
        monkeypatch.setattr(project_module, "CONFIG_DIR", tmp_path / "projects")

        with pytest.raises(ValueError, match="No projects configured"):
            resolve_project(cwd=Path("/tmp"))

    def test_explicit_project_name(self, monkeypatch, tmp_path):
        config_dir = tmp_path / "projects"
        monkeypatch.setattr(project_module, "CONFIG_DIR", config_dir)
        _write_project_config(
            config_dir,
            name="scopeo",
            code_repo="/Scopeo/draftnrun",
            notes_repo="/Scopeo/scopeo-notes",
            github_repo="Scopeo/draftnrun",
            linear_workspace_url="https://linear.app/draftnrun",
        )

        resolved = resolve_project("scopeo", cwd=Path("/tmp"))

        assert resolved.name == "scopeo"
        assert resolved.code_repo == Path("/Scopeo/draftnrun")

    def test_infers_from_code_repo_path(self, monkeypatch, tmp_path):
        config_dir = tmp_path / "projects"
        monkeypatch.setattr(project_module, "CONFIG_DIR", config_dir)
        _write_project_config(
            config_dir,
            name="scopeo",
            code_repo="/Scopeo/draftnrun",
            notes_repo="/Scopeo/scopeo-notes",
            github_repo="Scopeo/draftnrun",
            linear_workspace_url="https://linear.app/draftnrun",
        )

        resolved = resolve_project(cwd=Path("/Scopeo/draftnrun/ada_backend"))

        assert resolved.name == "scopeo"

    def test_infers_from_worktree_path(self, monkeypatch, tmp_path):
        config_dir = tmp_path / "projects"
        monkeypatch.setattr(project_module, "CONFIG_DIR", config_dir)
        _write_project_config(
            config_dir,
            name="scopeo",
            code_repo="/Scopeo/draftnrun",
            notes_repo="/Scopeo/scopeo-notes",
            github_repo="Scopeo/draftnrun",
            linear_workspace_url="https://linear.app/draftnrun",
        )

        resolved = resolve_project(
            cwd=Path("/Scopeo/draftnrun-worktrees/pablo-dra-1049-my-feature")
        )

        assert resolved.name == "scopeo"

    def test_errors_when_single_project_cannot_be_inferred(self, monkeypatch, tmp_path):
        config_dir = tmp_path / "projects"
        monkeypatch.setattr(project_module, "CONFIG_DIR", config_dir)
        _write_project_config(
            config_dir,
            name="scopeo",
            code_repo="/Scopeo/draftnrun",
            notes_repo="/Scopeo/scopeo-notes",
            github_repo="Scopeo/draftnrun",
            linear_workspace_url="https://linear.app/draftnrun",
        )

        with pytest.raises(ValueError, match="Could not infer project"):
            resolve_project(cwd=Path("/Users/pabloskewes"))

    def test_errors_when_ambiguous(self, monkeypatch, tmp_path):
        config_dir = tmp_path / "projects"
        monkeypatch.setattr(project_module, "CONFIG_DIR", config_dir)
        _write_project_config(
            config_dir,
            name="scopeo",
            code_repo="/Scopeo/draftnrun",
            notes_repo="/Scopeo/scopeo-notes",
            github_repo="Scopeo/draftnrun",
            linear_workspace_url="https://linear.app/draftnrun",
        )
        _write_project_config(
            config_dir,
            name="neverdrop",
            code_repo="/Scopeo/never-drop",
            notes_repo="/Scopeo/neverdrop-notes",
            github_repo="Scopeo/never-drop",
            linear_workspace_url="https://linear.app/neverdrop",
        )

        with pytest.raises(ValueError, match="Could not infer project"):
            resolve_project(cwd=Path("/Users/pabloskewes"))


class TestProjectConfigSetup:
    def test_no_setup_section_yields_empty_setup(self, monkeypatch, tmp_path):
        config_dir = tmp_path / "projects"
        monkeypatch.setattr(project_module, "CONFIG_DIR", config_dir)
        _write_project_config(
            config_dir,
            name="myproject",
            code_repo="/repos/myproject",
            notes_repo="/repos/notes",
            github_repo="org/myproject",
            linear_workspace_url="https://linear.app/org",
        )

        project = resolve_project("myproject", cwd=Path("/tmp"))
        assert project.setup.is_empty()

    def test_setup_section_is_parsed(self, monkeypatch, tmp_path):
        config_dir = tmp_path / "projects"
        monkeypatch.setattr(project_module, "CONFIG_DIR", config_dir)
        extra = textwrap.dedent("""\
            [[setup.symlinks]]
            source = "."
            target = "."
            files = [".env", "credentials.env"]

            [[setup.run]]
            argv = ["uv", "sync"]

            [[setup.run]]
            cwd = "frontend"
            argv = ["pnpm", "install"]
            if_exists = "package.json"
            skip_if_exists = "node_modules"
        """)
        _write_project_config(
            config_dir,
            name="myproject",
            code_repo="/repos/myproject",
            notes_repo="/repos/notes",
            github_repo="org/myproject",
            linear_workspace_url="https://linear.app/org",
            extra=extra,
        )

        project = resolve_project("myproject", cwd=Path("/tmp"))
        assert len(project.setup.symlinks) == 1
        assert project.setup.symlinks[0].files == (".env", "credentials.env")
        assert len(project.setup.run) == 2
        assert project.setup.run[0].argv == ("uv", "sync")
        assert project.setup.run[1].cwd == "frontend"
        assert project.setup.run[1].if_exists == "package.json"

    def test_setup_symlinks_with_list_source(self, monkeypatch, tmp_path):
        config_dir = tmp_path / "projects"
        monkeypatch.setattr(project_module, "CONFIG_DIR", config_dir)
        extra = textwrap.dedent("""\
            [[setup.symlinks]]
            source = ["frontend", "~/other/repo"]
            target = "frontend"
            files = [".env"]
        """)
        _write_project_config(
            config_dir,
            name="myproject",
            code_repo="/repos/myproject",
            notes_repo="/repos/notes",
            github_repo="org/myproject",
            linear_workspace_url="https://linear.app/org",
            extra=extra,
        )

        project = resolve_project("myproject", cwd=Path("/tmp"))
        step = project.setup.symlinks[0]
        assert step.sources == ("frontend", "~/other/repo")
        assert step.target == "frontend"

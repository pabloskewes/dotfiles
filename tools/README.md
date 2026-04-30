# psk tools

Personal CLI tools for development workflows. Installed as a `uv` tool, exposing entry points such as `psk`, `scopeo`, `worktree`, and `pr-inspect`.

## Install / reinstall

```bash
cd ~/dotfiles/tools
uv tool install --reinstall .
```

## Project config

`psk` reads project definitions from `~/.config/psk/projects/*.toml`.

Example `~/.config/psk/projects/scopeo.toml`:

```toml
name = "scopeo"
code_repo = "~/Scopeo/draftnrun"
notes_repo = "~/Scopeo/scopeo-notes"
github_repo = "Scopeo/draftnrun"
linear_workspace_url = "https://linear.app/draftnrun"
branch_owner = "pablo"
workspace_notes_label = "📓 scopeo-notes"
frontend_env_source_candidates = [
  "~/Scopeo/draftnrun/frontend",
  "~/Scopeo/back-office",
]
local_cursor_rule_source = "~/Scopeo/scopeo-notes/cursor-rules/local-personal.mdc"
```

## Commands

### `psk`

Project-agnostic workflow helpers.

| Command | Description |
|---|---|
| `psk ticket init` | Initialize a new ticket worktree, journal folder, and workspace file |
| `psk ticket open` | Open an existing ticket's monorepo worktree and workspace |
| `psk ticket list` | List active ticket worktrees for the inferred project |

#### `psk ticket init`

```bash
# Preview the resolved branch/worktree/journal paths
psk ticket init DRA-1049 my-feature --dry-run

# Create the worktree + journal + workspace
psk ticket init DRA-1049 my-feature --yes --open
```

#### `psk ticket open`

```bash
psk ticket open DRA-1049
```

#### `psk ticket list`

```bash
psk ticket list
```

### `scopeo`

Scopeo-specific helpers for the `draftnrun` monorepo.

| Command | Description |
|---|---|
| `scopeo db-reset-to-main` | Downgrade DB to main HEAD (see below) |

#### `scopeo db-reset-to-main`

Resets the shared database to the alembic HEAD of `~/Scopeo/draftnrun` (always on `main`). Useful when switching between worktrees that have different migration histories.

```bash
# Show what would happen without touching the DB
scopeo db-reset-to-main --dry-run

# Downgrade to main HEAD
scopeo db-reset-to-main

# Downgrade to main HEAD, then upgrade to current branch HEAD
scopeo db-reset-to-main --upgrade

```

### `worktree`

Git worktree management helpers.

## Development

```bash
# Run tests
cd ~/dotfiles/tools
uv run pytest
```

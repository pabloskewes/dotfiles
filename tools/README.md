# psk tools

Personal CLI tools for Scopeo development workflows. Installed as a `uv` tool, exposing two entry points: `scopeo` and `worktree`.

## Install / reinstall

```bash
cd ~/dotfiles/tools
uv tool install --reinstall .
```

## Commands

### `scopeo`

Scopeo-specific helpers.

| Command | Description |
|---|---|
| `scopeo ticket-init` | Initialize a new ticket (worktrees, journal folder, workspace file) |
| `scopeo ticket-open` | Open an existing ticket's workspace |
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

# Run from a specific worktree path instead of cwd
scopeo db-reset-to-main --repo /path/to/worktree
```

### `worktree`

Git worktree management helpers.

## Development

```bash
# Run tests
cd ~/dotfiles/tools
uv run pytest
```

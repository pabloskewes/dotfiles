# psk tools

Personal CLI tools for development workflows. Installed as a `uv` tool, exposing entry points such as `psk`, `scopeo`, `worktree`, and `pr-inspect`.

## Install / reinstall

```bash
cd ~/dotfiles/tools
uv tool install --reinstall .
```

## Project config

`psk` reads project definitions from `~/.config/psk/projects/*.toml`.

Each project file declares the repositories and an optional `[setup]` section that runs automatically whenever a new worktree is created (via `worktree create` or `psk ticket init`).

### Required fields

| Field | Description |
|---|---|
| `code_repo` | Absolute path (or `~`) to the git repository |
| `notes_repo` | Absolute path to the notes/journal repo |
| `github_repo` | `owner/repo` string for GitHub |
| `linear_workspace_url` | Linear workspace base URL |

### Optional fields

| Field | Default | Description |
|---|---|---|
| `name` | filename stem | Project name |
| `branch_owner` | `"pablo"` | Branch prefix (e.g. `pablo/dra-1049-...`) |
| `journals_dir` | `"journals"` | Subfolder inside `notes_repo` for journals |
| `workspace_code_label` | auto | Cursor workspace label for code repo |
| `workspace_notes_label` | auto | Cursor workspace label for notes repo |

### `[setup]` section

The `[setup]` section declares two kinds of idempotent steps that run after a worktree is created:

#### `[[setup.symlinks]]` — create symlinks into the worktree

```toml
[[setup.symlinks]]
source = "."                  # path relative to repo root (or absolute / ~)
target = "."                  # path relative to worktree root
files = [".env", "credentials.env"]

[[setup.symlinks]]
# source can be a list — first existing directory wins
source = ["frontend", "~/other/repo"]
target = "frontend"
files = [".env", ".env.local", ".env.development.local"]

[[setup.symlinks]]
source = "~/notes-repo/cursor-rules"
target = ".cursor/rules"
files = ["local-personal.mdc"]
```

**Path rules:**
- `source` relative → resolved against repo root. Absolute or `~` → expanded as-is.
- `source` as a list → candidates tried in order; first existing directory is used.
- `target` → always relative to the worktree root. Created automatically if missing.
- Symlinks are skipped if the destination already exists (idempotent).

#### `[[setup.run]]` — run commands inside the worktree

```toml
[[setup.run]]
argv = ["uv", "sync"]

[[setup.run]]
cwd = "frontend"              # relative to worktree root (default: ".")
argv = ["pnpm", "install"]
if_exists = "package.json"   # only run if this path exists (relative to cwd)
skip_if_exists = "node_modules"  # skip if this path already exists
```

**Behaviour:**
- `cwd` defaults to `.` (worktree root).
- `if_exists` and `skip_if_exists` are checked relative to the resolved `cwd`.
- A non-zero exit code prints a warning but does not abort the remaining steps.

### Full example — `~/.config/psk/projects/scopeo.toml`

```toml
name = "scopeo"
code_repo = "~/Scopeo/draftnrun"
notes_repo = "~/Scopeo/scopeo-notes"
github_repo = "Scopeo/draftnrun"
linear_workspace_url = "https://linear.app/draftnrun"
branch_owner = "pablo"
workspace_notes_label = "📓 scopeo-notes"

[[setup.symlinks]]
source = "."
target = "."
files = [".env", ".env.local", ".env.development.local", "credentials.env"]

[[setup.symlinks]]
source = ["frontend", "~/Scopeo/back-office"]
target = "frontend"
files = [".env", ".env.local", ".env.development.local", "credentials.env"]

[[setup.symlinks]]
source = "~/Scopeo/scopeo-notes/cursor-rules"
target = ".cursor/rules"
files = ["local-personal.mdc"]

[[setup.run]]
argv = ["uv", "sync"]

[[setup.run]]
cwd = "frontend"
argv = ["pnpm", "install"]
if_exists = "package.json"
skip_if_exists = "node_modules"
```

### No project config → no-op

If `worktree create` is run from a repo that doesn't match any configured project, the worktree is created normally and no setup steps run.

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

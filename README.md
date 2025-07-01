# Dotfiles

This repository contains my personal dotfiles and configuration files for setting up my development environment. It includes configurations for VS Code/Cursor, Git, Bash, and Karabiner-Elements.

## Quick Start

1. Clone this repository:

```bash
git clone https://github.com/yourusername/dotfiles.git ~/dotfiles
```

2. Run the setup script:

```bash
cd ~/dotfiles
chmod +x scripts/setup_symlinks.sh
./scripts/setup_symlinks.sh
```

This will automatically create all necessary symlinks for your configuration files.

## Configuration Files

### Hammerspoon Configuration

Window management and automation for macOS. Includes always-on-top functionality with `Ctrl + Alt + \` hotkey and visual border indicators.

### VS Code / Cursor Configuration

The setup script handles both VS Code and Cursor configurations automatically:

- On macOS:
  - VS Code: `~/Library/Application Support/Code/User/`
  - Cursor: `~/Library/Application Support/Cursor/User/`
- On Linux:
  - VS Code: `~/.config/Code/User/`

Both editors will use the same configuration files from your dotfiles repository.

### Git Configuration

The `.gitconfig` file includes:

- Multiple GitHub account support via SSH
- Custom aliases for cloning repositories
- Common Git configurations

#### SSH Configuration

The repository includes SSH configuration for managing multiple GitHub accounts:

```plaintext
# Personal GitHub account
Host github
  HostName github.com
  User git
  IdentityFile ~/.ssh/id_rsa_personal

# Work GitHub account
Host github-scopeo
  HostName github.com
  User git
  IdentityFile ~/.ssh/id_rsa_scopeo
```

#### Git Aliases

Useful Git aliases for quick repository cloning:

```bash
# Clone personal repository
git clone-personal some-repo

# Clone work repository
git clone-scopeo some-repo
```

### Bash Configuration

- `.bashrc`: Main Bash configuration file
- `.bash_aliases`: Custom Bash aliases

### Karabiner-Elements Configuration

Custom keyboard mappings for macOS, supporting both MacBook and external keyboards:

#### Keyboard-Specific Mappings

- **USB Keyboard (Keychron, etc.)**:

  - Swap Alt (Option) and Command keys
  - `Ctrl + W` → `Command + W` (Close Window)
  - `Ctrl + Shift + W` → `Command + Q` (Close Application)
  - `Ctrl + Alt + T` → Open Terminal
  - `Command + |` → `Command + `` (Move Focus to Next Window)

- **MacBook Keyboard**:

  - `Fn + W` → `Command + W` (Close Window)
  - `Fn + Shift + W` → `Command + Q` (Close Application)
  - `Fn + 1` → `Command + Control + Shift + 4` (Screenshot Selected Area)
  - `Fn + 2` → Open Bluetooth Settings

- **Magic Keyboard**:
  - `Ctrl + W` → `Command + W` (Close Window)
  - `Ctrl + Shift + W` → `Command + Q` (Close Application)

#### Universal Shortcuts

- **Terminal Access**:

  - `Ctrl + Right Alt + T` or `Ctrl + Left Alt + T` → Open Terminal

- **Window Management**:

  - `Command + D` → `Fn + F11` (Show Desktop)

- **Finder Operations**:

  - `Command + X` → Cut Files (with paste)

- **Special Characters**:
  - `\` → `<` (on USB keyboard)
  - `Shift + \` → `>` (on USB keyboard)
  - `` ` `` → `<` (on MacBook keyboard)
  - ` Shift + ``  ` ``→`>` (on MacBook keyboard)
  - `Command + \` → `Option + -` (for backslash usage)

#### Screenshot Tools

- `Fn + 1` → `Command + Control + Shift + 4` (Screenshot Selected Area)
- `Print Screen` → `Command + Control + Shift + 4` (Screenshot Selected Area)

## VS Code Extensions

Install all recommended extensions:

```bash
cat ~/dotfiles/.vscode/extensions.txt | grep -v '^#' | xargs -n 1 code --install-extension
```

## Maintenance

### Checking Symlinks

To verify that all symlinks are correctly set up:

```bash
./scripts/check_symlinks.sh
```

### Updating Symlinks

If you need to update your symlinks:

```bash
./scripts/setup_symlinks.sh
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.

# Dotfiles

This repository contains my personal dotfiles and configuration files for setting up my development environment. Follow the instructions below to clone the repository and set up the environment on a new machine.

## Table of Contents

- [Cloning the Repository](#cloning-the-repository)
- [Creating Symlinks](#creating-symlinks)
- [VS Code Configuration](#vs-code-configuration)
- [VS Code Extensions](#vs-code-extensions)
- [Git Configuration](#git-configuration)
- [Karabiner Configuration](#karabiner-configuration)

## Cloning the Repository

Start by cloning the dotfiles repository to your home directory:

```bash
git clone https://github.com/yourusername/dotfiles.git ~/dotfiles
```

## Creating Symlinks

To ensure your system uses the configurations stored in this repository, create symlinks from your home directory to the dotfiles in this repository.

### Bash Configuration

```bash
ln -sf ~/dotfiles/.bashrc ~/.bashrc
ln -sf ~/dotfiles/.bash_aliases ~/.bash_aliases
```

### VS Code Configuration

For Linux, the VS Code configuration files are stored in the `~/.config/Code/User` directory. Create symlinks to the settings and keybindings files in this repository:

```bash
ln -sf ~/dotfiles/.vscode/settings.json ~/.config/Code/User/settings.json
ln -sf ~/dotfiles/.vscode/keybindings.json ~/.config/Code/User/keybindings.json
```

For macOS, the VS Code configuration files are stored in the `~/Library/Application Support/Code/User` directory. Create symlinks to the settings and keybindings files in this repository:

```bash
ln -sf ~/dotfiles/.vscode/settings.json ~/Library/Application\ Support/Code/User/settings.json
ln -sf ~/dotfiles/.vscode/keybindings.json ~/Library/Application\ Support/Code/User/keybindings.json
```

### Git Configuration

To manage your Git configuration across multiple systems, store the `.gitconfig` file in your dotfiles repository and create a symlink:

```bash
ln -sf ~/dotfiles/.gitconfig ~/.gitconfig
```

## VS Code Configuration

### Settings

The VS Code settings and keybindings are managed in this repository. They are stored in:

- `~/.vscode/settings.json`
- `~/.vscode/keybindings.json`

### Keybindings

Keybindings for VS Code include custom shortcuts, especially useful for LaTeX editing:

- `Ctrl+B` for bold text in LaTeX
- `Ctrl+I` for italic text in LaTeX
- `Ctrl+U` for underlined text in LaTeX

### Custom Settings

The `settings.json` includes configurations for:

- Python formatting with Black
- Enabling GitHub Copilot
- Setting up terminal behavior
- File associations for custom file types

## VS Code Extensions

To install the VS Code extensions listed in the repository, use the provided `extensions.txt` file.

### Exported Extensions

This repository includes a list of VS Code extensions that I commonly use, stored in `.vscode/extensions.txt`. You can install all these extensions using the following command:

```bash
cat ~/dotfiles/.vscode/extensions.txt | grep -v '^#' | xargs -n 1 code --install-extension
```

### Commented Extensions List

The `extensions.txt` file includes comments explaining the purpose of each extension. These comments are ignored when running the installation command.

```plaintext
# SQL Formatter
adpyke.vscode-sql-formatter

# Django support
batisteo.vscode-django

# (etc.)
```

## Karabiner Configuration

The Karabiner configuration file is stored in `~/.config/karabiner/karabiner.json`. Create a symlink to the configuration file in this repository:

```bash
ln -sf ~/dotfiles/.config/karabiner/karabiner.json ~/.config/karabiner/karabiner.json
```

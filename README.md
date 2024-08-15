# Dotfiles

This repository contains my personal dotfiles and configuration files for setting up my development environment. Follow the instructions below to clone the repository and set up the environment on a new machine.

## Table of Contents

- [Cloning the Repository](#cloning-the-repository)
- [Creating Symlinks](#creating-symlinks)
  - [Bash Configuration](#bash-configuration)
  - [VS Code Configuration](#vs-code-configuration)
- [Git Configuration](#git-configuration)
  - [SSH Configuration](#ssh-configuration)
- [VS Code Configuration](#vs-code-configuration)
  - [Settings](#settings)
  - [Keybindings](#keybindings)
  - [Custom Settings](#custom-settings)
- [VS Code Extensions](#vs-code-extensions)
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

## Git Configuration

To manage your Git configuration across multiple systems, store the `.gitconfig` file in your dotfiles repository and create a symlink:

```bash
ln -sf ~/dotfiles/.gitconfig ~/.gitconfig
```

### SSH Configuration

To manage multiple GitHub accounts (e.g., personal and work) using SSH, you can set up SSH configuration aliases. This allows you to easily switch between accounts based on the folder or project you're working on.

#### SSH Config Setup

Add the following configuration to your `~/.ssh/config` file:

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

#### Using Git Aliases

To streamline your workflow, this repository includes Git aliases that allow you to clone repositories using the appropriate SSH key without manually specifying the full URL:

```plaintext
[alias]
    clone-personal = "!f() { git clone git@github:$1.git; }; f"
    clone-scopeo = "!f() { git clone git@github-scopeo:$1.git; }; f"
```

These aliases allow you to quickly clone repositories based on your SSH configuration:

- **For personal repositories**:
  ```bash
  git clone-personal some-repo
  ```

- **For work repositories**:
  ```bash
  git clone-scopeo some-repo
  ```


#### Summary

Ensure that the `Host` names in your SSH config (`github` and `github-scopeo`) match the aliases used in your Git remote URLs. If you've already cloned a repository, update the remote URL to use the correct alias to ensure the right SSH key is used.

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

- **Invert Alt (Option) and Command keys**
  - **USB Keyboard:** Swaps `Alt (Option)` and `Command` keys.

- **Close Application**
  - **MacBook keyboard:** `Fn + Shift + W` ⟶ `Command + Q`
  - **USB Keyboard:** `Ctrl + Shift + W` ⟶ `Command + Q`

- **Close Window**
  - **MacBook keyboard:** `Fn + W` ⟶ `Command + W`
  - **USB Keyboard:** `Ctrl + W` ⟶ `Command + W`

- **Open Terminal**
  - `Ctrl + RAlt + T` or `Ctrl + LAlt + T`

- **Show Desktop**
  - `Command + D` ⟶ `Fn + F11`

- **Cut Files in Finder**
  - `Command + X` ⟶ Cut files

- **Screenshot Selected Area to Clipboard**
  - `Fn + 1` ⟶ `Command + Control + Shift + 4`

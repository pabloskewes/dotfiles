#!/bin/bash

# Function to create directory if it doesn't exist
create_dir() {
    if [ ! -d "$1" ]; then
        mkdir -p "$1"
        echo "Created directory: $1"
    fi
}

# Function to create symlink
create_symlink() {
    local source="$1"
    local target="$2"

    # Create parent directory if it doesn't exist
    create_dir "$(dirname "$target")"

    # Remove existing file/symlink if it exists
    if [ -e "$target" ]; then
        rm -rf "$target"
        echo "Removed existing: $target"
    fi

    # Create symlink
    ln -sf "$source" "$target"
    echo "Created symlink: $target -> $source"
}

# Get the directory where the script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOTFILES_DIR="$(dirname "$SCRIPT_DIR")"

# Bash configuration
create_symlink "$DOTFILES_DIR/.bashrc" "$HOME/.bashrc"
create_symlink "$DOTFILES_DIR/.bash_aliases" "$HOME/.bash_aliases"

# Git configuration
create_symlink "$DOTFILES_DIR/.gitconfig" "$HOME/.gitconfig"

# Karabiner configuration
create_symlink "$DOTFILES_DIR/karabiner/karabiner.json" "$HOME/.config/karabiner/karabiner.json"

# Hammerspoon configuration
create_symlink "$DOTFILES_DIR/hammerspoon/init.lua" "$HOME/.hammerspoon/init.lua"

# VS Code / Cursor configuration
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS paths
    create_symlink "$DOTFILES_DIR/.vscode/settings.json" "$HOME/Library/Application Support/Code/User/settings.json"
    create_symlink "$DOTFILES_DIR/.vscode/keybindings.json" "$HOME/Library/Application Support/Code/User/keybindings.json"
    create_symlink "$DOTFILES_DIR/.vscode/settings.json" "$HOME/Library/Application Support/Cursor/User/settings.json"
    create_symlink "$DOTFILES_DIR/.vscode/keybindings.json" "$HOME/Library/Application Support/Cursor/User/keybindings.json"
else
    # Linux paths
    create_symlink "$DOTFILES_DIR/.vscode/settings.json" "$HOME/.config/Code/User/settings.json"
    create_symlink "$DOTFILES_DIR/.vscode/keybindings.json" "$HOME/.config/Code/User/keybindings.json"
fi

echo "✅ All symlinks have been set up successfully!"

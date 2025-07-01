#!/bin/bash

# Function to check symlink
check_symlink() {
    if [ -L "$1" ]; then
        if [ ! -e "$1" ]; then
            echo "Broken symlink: $1"
        else
            echo "Symlink OK: $1"
        fi
    else
        echo "Not a symlink: $1"
    fi
}

# List of symlinks to check
symlinks=(
    "$HOME/.bashrc"
    "$HOME/.bash_aliases"
    "$HOME/.gitconfig"
    "$HOME/.config/karabiner/karabiner.json"
    "$HOME/.hammerspoon/init.lua"
)

# Add VS Code / Cursor paths based on OS
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS paths
    symlinks+=(
        "$HOME/Library/Application Support/Code/User/settings.json"
        "$HOME/Library/Application Support/Code/User/keybindings.json"
        "$HOME/Library/Application Support/Cursor/User/settings.json"
        "$HOME/Library/Application Support/Cursor/User/keybindings.json"
    )
else
    # Linux paths
    symlinks+=(
        "$HOME/.config/Code/User/settings.json"
        "$HOME/.config/Code/User/keybindings.json"
    )
fi

# Loop through each symlink and check it
for symlink in "${symlinks[@]}"; do
    check_symlink "$symlink"
done

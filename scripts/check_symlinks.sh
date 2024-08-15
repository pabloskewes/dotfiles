#!/bin/bash

# List of symlinks to check
symlinks=(
    "$HOME/.bashrc"
    "$HOME/.bash_aliases"
    "$HOME/.config/Code/User/settings.json"
    "$HOME/.config/Code/User/keybindings.json"
    "$HOME/Library/Application Support/Code/User/settings.json"
    "$HOME/Library/Application Support/Code/User/keybindings.json"
    "$HOME/.gitconfig"
    "$HOME/.config/karabiner/karabiner.json"
)

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

# Loop through each symlink and check it
for symlink in "${symlinks[@]}"; do
    check_symlink "$symlink"
done

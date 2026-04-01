#!/usr/bin/env bash
# Installs pandoc 2.9.2.1 and wkhtmltox 0.12.6.1 to ~/.local (no root required).
# Adds the binaries to PATH in ~/.zshrc and ~/.bashrc if not already present.

set -euo pipefail

INSTALL_DIR="$HOME/.local"

# --- pandoc 2.9.2.1 ---
PANDOC_URL="https://github.com/jgm/pandoc/releases/download/2.9.2.1/pandoc-2.9.2.1-1-amd64.deb"
PANDOC_DEB="/tmp/pandoc-2.9.2.1-1-amd64.deb"
PANDOC_DIR="$INSTALL_DIR/pandoc"
PANDOC_BIN="$PANDOC_DIR/usr/bin"

echo "Downloading pandoc 2.9.2.1..."
wget -qO "$PANDOC_DEB" "$PANDOC_URL"

echo "Extracting to $PANDOC_DIR..."
mkdir -p "$PANDOC_DIR"
dpkg-deb --extract "$PANDOC_DEB" "$PANDOC_DIR"

echo "Verifying pandoc..."
"$PANDOC_BIN/pandoc" --version | head -1

# --- wkhtmltox 0.12.6.1 ---
WKHTMLTOX_URL="https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6.1-2/wkhtmltox_0.12.6.1-2.jammy_amd64.deb"
WKHTMLTOX_DEB="/tmp/wkhtmltox_0.12.6.1-2.jammy_amd64.deb"
WKHTMLTOX_DIR="$INSTALL_DIR/wkhtmltox"
WKHTMLTOX_BIN="$WKHTMLTOX_DIR/usr/local/bin"

echo "Downloading wkhtmltox 0.12.6.1..."
wget -qO "$WKHTMLTOX_DEB" "$WKHTMLTOX_URL"

echo "Extracting to $WKHTMLTOX_DIR..."
mkdir -p "$WKHTMLTOX_DIR"
dpkg-deb --extract "$WKHTMLTOX_DEB" "$WKHTMLTOX_DIR"

echo "Verifying wkhtmltoimage..."
"$WKHTMLTOX_BIN/wkhtmltoimage" --version

# --- Add to PATH ---
PATH_LINE="export PATH=\"$PANDOC_BIN:$WKHTMLTOX_BIN:\$PATH\""

for RC in "$HOME/.zshrc" "$HOME/.bashrc"; do
    if [ -f "$RC" ] && ! grep -qF 'agenttg deps' "$RC"; then
        echo "" >> "$RC"
        echo "# agenttg deps (pandoc + wkhtmltox local install)" >> "$RC"
        echo "$PATH_LINE" >> "$RC"
        echo "Added PATH entry to $RC"
    fi
done

echo "Done. Restart your shell or run:"
echo "  $PATH_LINE"

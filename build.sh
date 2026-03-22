#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "Building CTRL+F+Claude.app..."

# Clean previous build
rm -rf build dist

# Check for icon
if [ ! -f icon.icns ]; then
    echo "Warning: icon.icns not found. Build will use default icon."
    echo "To add a custom icon, place icon.icns in this directory."
fi

# Build .app bundle
python setup.py py2app 2>&1 | tail -5

# Copy to Applications
echo "Installing to /Applications..."
rm -rf "/Applications/CTRL+F+Claude.app"
cp -r "dist/CTRL+F+Claude.app" /Applications/

echo "Done! Launch from Applications or Spotlight."

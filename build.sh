#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "Building Claude Conversations.app..."

# Clean previous build
rm -rf build dist

# Generate icon if missing
if [ ! -f icon.icns ]; then
    echo "Generating icon..."
    python icon_gen.py
fi

# Build .app bundle
python setup.py py2app 2>&1 | tail -5

# Copy to Applications
echo "Installing to /Applications..."
rm -rf "/Applications/Claude Conversations.app"
cp -r "dist/Claude Conversations.app" /Applications/

echo "Done! Launch from Applications or Spotlight."

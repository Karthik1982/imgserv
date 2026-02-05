#!/bin/bash
# Build script for Photo Frame Server executable

set -e

echo "Installing PyInstaller..."
pip install pyinstaller

echo "Building executable..."
pyinstaller imgserv.spec --clean

echo ""
echo "Build complete!"
echo "Executable located at: dist/imgserv"
echo ""
echo "Usage:"
echo "  ./dist/imgserv /path/to/photos --city 'New York' --weather-api-key YOUR_KEY"

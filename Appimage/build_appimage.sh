#!/bin/bash
# Build script for MO2 Manager AppImage
# Run this script from the project directory

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

APP_NAME="MO2Manager"
APPDIR="${SCRIPT_DIR}/${APP_NAME}.AppDir"

echo "=========================================="
echo "Building ${APP_NAME} AppImage"
echo "=========================================="

# Clean up previous builds (keep .build_venv for faster rebuilds)
echo "Cleaning up previous builds..."
rm -rf build dist "${APPDIR}" *.AppImage *.spec

# Check for Python and pip
echo "Checking Python installation..."
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 not found"
    exit 1
fi

# Create or reuse virtual environment for build
VENV_DIR="${SCRIPT_DIR}/.build_venv"
if [ -d "$VENV_DIR" ]; then
    echo "Reusing existing build virtual environment..."
else
    echo "Creating build virtual environment..."
    python3 -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"

# Install/update dependencies
echo "Installing dependencies..."
pip install --quiet pyinstaller PyQt6 certifi py7zr

SRC_DIR="${SCRIPT_DIR}/../src"

# Run PyInstaller
echo "Running PyInstaller..."
python3 -m PyInstaller \
    --name mo2manager \
    --onedir \
    --windowed \
    --noconfirm \
    --add-data "${SRC_DIR}/build_data_folder.py:." \
    "${SRC_DIR}/gui.py"

# Create AppDir structure
echo "Creating AppDir structure..."
mkdir -p "${APPDIR}/usr/bin"
mkdir -p "${APPDIR}/usr/share/applications"
mkdir -p "${APPDIR}/usr/share/icons"

# Copy PyInstaller output to AppDir
echo "Copying application files..."
cp -r dist/mo2manager/* "${APPDIR}/usr/bin/"

# Generate desktop file
cat > "${APPDIR}/mo2manager.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=MO2 Manager
Exec=mo2manager
Icon=mo2manager
Categories=Utility;
DESKTOP
cp "${APPDIR}/mo2manager.desktop" "${APPDIR}/usr/share/applications/"

# Generate AppRun
cat > "${APPDIR}/AppRun" <<'APPRUN'
#!/bin/bash
SELF=$(readlink -f "$0")
HERE=${SELF%/*}
exec "${HERE}/usr/bin/mo2manager" "$@"
APPRUN
chmod +x "${APPDIR}/AppRun"

# Create a minimal placeholder icon (appimagetool requires one)
touch "${APPDIR}/mo2manager.png"

# Download appimagetool if not present
APPIMAGETOOL="appimagetool-x86_64.AppImage"
if [ ! -f "$APPIMAGETOOL" ]; then
    echo "Downloading appimagetool..."
    wget -q "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage" -O "$APPIMAGETOOL"
    chmod +x "$APPIMAGETOOL"
fi

# Build AppImage (use --appimage-extract-and-run if FUSE is not available)
echo "Building AppImage..."
if [ -f /dev/fuse ]; then
    ARCH=x86_64 ./"$APPIMAGETOOL" "${APPDIR}" "${APP_NAME}-x86_64.AppImage"
else
    echo "FUSE not available, using extract-and-run mode..."
    ARCH=x86_64 ./"$APPIMAGETOOL" --appimage-extract-and-run "${APPDIR}" "${APP_NAME}-x86_64.AppImage"
fi

# Clean up (keep .build_venv for faster rebuilds)
echo "Cleaning up build artifacts..."
deactivate 2>/dev/null || true
rm -rf build dist *.spec

echo "=========================================="
echo "Build complete!"
echo "AppImage created: ${APP_NAME}-x86_64.AppImage"
echo ""
echo "To run: chmod +x ${APP_NAME}-x86_64.AppImage && ./${APP_NAME}-x86_64.AppImage"
echo "=========================================="

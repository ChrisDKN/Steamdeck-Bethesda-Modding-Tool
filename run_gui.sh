#!/usr/bin/env bash
set -e

# ---------------- CONFIG ----------------
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
GUI_FILE="$PROJECT_DIR/gui.py"
PYTHON_BIN="python3"
# ----------------------------------------

echo "== Skyrim Merger GUI Launcher =="

# 1. Ensure python exists
if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 not found"
    exit 1
fi

# 2. Ensure pip exists (system-level)
if ! $PYTHON_BIN -m pip --version >/dev/null 2>&1; then
    echo "pip not found, installing..."
    sudo steamos-readonly disable || true
    sudo pacman -S --noconfirm python-pip
else
    echo "pip already installed"
fi

# 3. Create virtual environment if missing
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    $PYTHON_BIN -m venv "$VENV_DIR"
else
    echo "Virtual environment already exists"
fi

# 4. Activate virtual environment
source "$VENV_DIR/bin/activate"

# 5. Upgrade pip inside venv (safe to repeat)
python -m pip install --upgrade pip >/dev/null

# 6. Install dependencies if missing
DEPS=("PyQt6" "certifi" "py7zr")
for dep in "${DEPS[@]}"; do
    if ! python -c "import ${dep,,}" >/dev/null 2>&1; then
        echo "Installing $dep..."
        python -m pip install "$dep"
    else
        echo "$dep already installed"
    fi
done

# 7. Run GUI
if [ ! -f "$GUI_FILE" ]; then
    echo "ERROR: gui.py not found at $GUI_FILE"
    exit 1
fi

echo "Launching GUI..."
exec python "$GUI_FILE"

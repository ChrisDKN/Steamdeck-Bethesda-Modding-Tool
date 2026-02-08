#!/usr/bin/env python3
"""
GUI for Skyrim Mod Organizer 2 Data Folder Builder

A Linux GUI application that helps merge MO2 mods into a single Data folder
using hardlinks.
"""

import os
import sys
import json
import shutil
import subprocess
import ssl
import certifi
import urllib.request
import tempfile
import zipfile
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QComboBox,
    QTextEdit, QGroupBox, QMessageBox, QProgressBar, QStackedWidget,
    QInputDialog, QListWidget, QListWidgetItem, QSplitter, QFrame,
    QCheckBox, QAbstractItemView, QDialog, QDialogButtonBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont


def get_clean_env():
    """Get a clean environment for launching external processes like Proton.

    When running inside an AppImage, environment variables like LD_LIBRARY_PATH
    and QT_PLUGIN_PATH are modified to point to the AppImage's internal libraries.
    These can interfere with external applications like Proton/Wine.
    """
    env = os.environ.copy()

    # Check if running inside an AppImage
    if 'APPIMAGE' in env or 'APPDIR' in env:
        # Remove or clean AppImage-specific paths from library paths
        appdir = env.get('APPDIR', '')

        # Clean LD_LIBRARY_PATH
        if 'LD_LIBRARY_PATH' in env:
            paths = env['LD_LIBRARY_PATH'].split(':')
            cleaned = [p for p in paths if appdir not in p and '/tmp/.mount_' not in p]
            if cleaned:
                env['LD_LIBRARY_PATH'] = ':'.join(cleaned)
            else:
                del env['LD_LIBRARY_PATH']

        # Clean QT_PLUGIN_PATH
        if 'QT_PLUGIN_PATH' in env:
            paths = env['QT_PLUGIN_PATH'].split(':')
            cleaned = [p for p in paths if appdir not in p and '/tmp/.mount_' not in p]
            if cleaned:
                env['QT_PLUGIN_PATH'] = ':'.join(cleaned)
            else:
                del env['QT_PLUGIN_PATH']

        # Clean PATH
        if 'PATH' in env:
            paths = env['PATH'].split(':')
            cleaned = [p for p in paths if appdir not in p and '/tmp/.mount_' not in p]
            env['PATH'] = ':'.join(cleaned) if cleaned else '/usr/bin:/bin'

        # Remove AppImage-specific variables
        for var in ['APPDIR', 'APPIMAGE', 'ARGV0', 'OWD']:
            env.pop(var, None)

    return env


def get_app_path():
    """Get the application base path, handling both frozen (PyInstaller) and normal execution."""
    if getattr(sys, 'frozen', False):
        # Running as bundled app (PyInstaller)
        return sys._MEIPASS
    else:
        # Running as script
        return os.path.dirname(os.path.abspath(__file__))


def get_default_game_paths():
    """Return the default game configuration data."""
    home = os.path.expanduser("~")
    steam_common = os.path.join(home, ".local/share/Steam/steamapps/common")
    steam_compat = os.path.join(home, ".local/share/Steam/steamapps/compatdata")
    return {"games": [
        {
            "name": "Skyrim Special Edition",
            "data_path": os.path.join(steam_common, "Skyrim Special Edition/Data"),
            "plugins_path": os.path.join(steam_compat, "489830/pfx/drive_c/users/steamuser/AppData/Local/Skyrim Special Edition"),
            "launcher_name": "SkyrimSELauncher.exe",
            "script_extender_name": "skse64_loader.exe",
            "script_extender_download": "https://skse.silverlock.org/"
        },
        {
            "name": "Skyrim",
            "data_path": os.path.join(steam_common, "Skyrim/Data"),
            "plugins_path": os.path.join(steam_compat, "72850/pfx/drive_c/users/steamuser/AppData/Local/Skyrim"),
            "launcher_name": "SkyrimLauncher.exe",
            "script_extender_name": "skse_loader.exe",
            "script_extender_download": "https://skse.silverlock.org/"
        },
        {
            "name": "Fallout 4",
            "data_path": os.path.join(steam_common, "Fallout 4/Data"),
            "plugins_path": os.path.join(steam_compat, "377160/pfx/drive_c/users/steamuser/AppData/Local/Fallout4"),
            "launcher_name": "Fallout4Launcher.exe",
            "script_extender_name": "f4se_loader.exe",
            "script_extender_download": "https://f4se.silverlock.org/"
        },
        {
            "name": "Fallout 3",
            "data_path": os.path.join(steam_common, "Fallout 3/Data"),
            "plugins_path": os.path.join(steam_compat, "22300/pfx/drive_c/users/steamuser/AppData/Local/Fallout3"),
            "launcher_name": "Fallout3Launcher.exe",
            "script_extender_name": "fose_loader.exe",
            "script_extender_download": "https://fose.silverlock.org/"
        },
        {
            "name": "New Vegas",
            "data_path": os.path.join(steam_common, "Fallout New Vegas/Data"),
            "plugins_path": os.path.join(steam_compat, "22380/pfx/drive_c/users/steamuser/AppData/Local/FalloutNV"),
            "launcher_name": "FalloutNVLauncher.exe",
            "script_extender_name": "nvse_loader.exe",
            "script_extender_download": "https://github.com/xNVSE/NVSE/releases"
        },
        {
            "name": "Oblivion",
            "data_path": os.path.join(steam_common, "Oblivion/Data"),
            "plugins_path": os.path.join(steam_compat, "22330/pfx/drive_c/users/steamuser/AppData/Local/Oblivion"),
            "launcher_name": "OblivionLauncher.exe",
            "script_extender_name": "obse_loader.exe",
            "script_extender_download": "https://obse.silverlock.org/"
        }
    ]}


def get_config_path():
    """Get the config file path - uses user's home directory for writability."""
    user_config_dir = os.path.join(os.path.expanduser("~"), ".config", "mo2manager")
    user_config = os.path.join(user_config_dir, "game_paths.json")

    # If user config exists, use it
    if os.path.exists(user_config):
        return user_config

    # Generate default config
    try:
        os.makedirs(user_config_dir, exist_ok=True)
        with open(user_config, 'w', encoding='utf-8') as f:
            json.dump(get_default_game_paths(), f, indent=4)
        return user_config
    except (OSError, IOError):
        return user_config


def load_game_paths():
    """Load game paths from the JSON config file."""
    config_path = get_config_path()
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("games", [])
        except (json.JSONDecodeError, IOError):
            pass
    return []


def save_game_paths(game_paths):
    """Save game paths list back to the JSON config file."""
    config_path = get_config_path()
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump({"games": game_paths}, f, indent=4)
    except (OSError, IOError):
        pass


def find_game_installs(game_paths):
    """
    Search for installed games by scanning for their launcher_name executable
    across Steam common folders (internal + SD cards).
    Returns a dict mapping game name to the game folder path found.
    """
    scan_roots = []
    home = os.path.expanduser("~")

    # Internal storage: Steam default library
    steam_common = os.path.join(home, ".local/share/Steam/steamapps/common")
    if os.path.isdir(steam_common):
        scan_roots.append(steam_common)

    # SD cards and other mounted media
    media_dir = os.path.join("/run/media", os.path.basename(home))
    if os.path.isdir(media_dir):
        for entry in os.listdir(media_dir):
            media_path = os.path.join(media_dir, entry)
            if os.path.isdir(media_path):
                scan_roots.append(media_path)

    return _scan_for_launchers(game_paths, scan_roots)


def _scan_for_launchers(game_paths, scan_roots):
    """
    Scan the given root directories for launcher_name executables.
    Returns a dict mapping game name to the game folder path found.
    """
    # Build a lookup: lowercase launcher_name -> list of game dicts
    launcher_lookup = {}
    for game in game_paths:
        launcher = game.get("launcher_name", "")
        if launcher:
            launcher_lookup.setdefault(launcher.lower(), []).append(game)

    if not launcher_lookup:
        return {}

    skip_dirs = {'node_modules', '__pycache__', '.git', '.cache', 'Trash',
                 '.build_venv', '.venv', 'venv'}
    found = {}  # game name -> game folder path

    for scan_root in scan_roots:
        for root, dirs, files in os.walk(scan_root):
            # Skip irrelevant directories to keep scanning fast
            dirs[:] = [d for d in dirs if d not in skip_dirs]

            for filename in files:
                lower_name = filename.lower()
                if lower_name in launcher_lookup:
                    game_folder = root  # folder containing the launcher
                    for game in launcher_lookup[lower_name]:
                        game_name = game.get("name", "")
                        if game_name not in found:
                            found[game_name] = game_folder
        # Stop early if all games found
        if len(found) >= len(game_paths):
            break

    return found


def scan_for_mo2_instances():
    """
    Scan ~/.local, /run/media/deck/, and game directories for ModOrganizer.exe instances.
    Returns a list of tuples: (display_name, folder_path)
    """
    instances = []
    seen_paths = set()
    home = os.path.expanduser("~")

    # Collect scan roots: Steam common, SD cards, plus configured game directories
    scan_roots = []

    # Internal storage: Steam default library
    steam_common = os.path.join(home, ".local/share/Steam/steamapps/common")
    if os.path.isdir(steam_common):
        scan_roots.append(steam_common)

    # SD cards and other mounted media
    media_dir = os.path.join("/run/media", os.path.basename(home))
    if os.path.isdir(media_dir):
        for entry in os.listdir(media_dir):
            media_path = os.path.join(media_dir, entry)
            if os.path.isdir(media_path):
                scan_roots.append(media_path)

    # Also scan configured game directories as a fallback
    game_paths = load_game_paths()
    for game in game_paths:
        data_path = game.get("data_path", "")
        if data_path:
            game_folder = os.path.dirname(data_path)
            if os.path.isdir(game_folder):
                scan_roots.append(game_folder)

    skip_dirs = {'node_modules', '__pycache__', '.git', '.cache', 'Trash',
                 '.build_venv', '.venv', 'venv'}

    for scan_root in scan_roots:
        for root, dirs, files in os.walk(scan_root):
            # Skip irrelevant directories to keep scanning fast
            dirs[:] = [d for d in dirs if d not in skip_dirs]

            for filename in files:
                if filename.lower() == "modorganizer.exe":
                    mo2_folder = root
                    if mo2_folder in seen_paths:
                        continue
                    seen_paths.add(mo2_folder)
                    # Create a friendly display name using the parent folder name
                    parent_name = os.path.basename(mo2_folder)
                    grandparent = os.path.basename(os.path.dirname(mo2_folder))
                    display_name = f"{grandparent}/{parent_name}" if grandparent else parent_name
                    instances.append((display_name, mo2_folder))

    # Sort by path for consistent ordering
    instances.sort(key=lambda x: x[1])
    return instances


class DownloadWorker(QThread):
    """Worker thread to download and extract MO2 without blocking the GUI."""
    output_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)  # Download progress percentage
    finished_signal = pyqtSignal(bool, str)

    MO2_DOWNLOAD_URL = "https://github.com/ModOrganizer2/modorganizer/releases/download/v2.5.2/Mod.Organizer-2.5.2.7z"

    def __init__(self, destination_folder, game_data=None):
        super().__init__()
        self.destination_folder = destination_folder
        self.game_data = game_data

    def run(self):
        try:
            # Create destination folder
            os.makedirs(self.destination_folder, exist_ok=True)
            self.output_signal.emit(f"Destination: {self.destination_folder}")

            # Download to temp file
            self.output_signal.emit(f"Downloading Mod Organizer 2...")
            self.output_signal.emit(f"URL: {self.MO2_DOWNLOAD_URL}")

            # Create temp file for download
            temp_file = os.path.join(tempfile.gettempdir(), "Mod.Organizer-2.5.2.7z")

            # Download with progress using SSL context (required for AppImage)
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            request = urllib.request.Request(self.MO2_DOWNLOAD_URL)

            with urllib.request.urlopen(request, context=ssl_context) as response:
                total_size = int(response.headers.get('Content-Length', 0))
                block_size = 8192
                downloaded = 0

                with open(temp_file, 'wb') as f:
                    while True:
                        block = response.read(block_size)
                        if not block:
                            break
                        f.write(block)
                        downloaded += len(block)
                        if total_size > 0:
                            progress = int(downloaded * 100 / total_size)
                            self.progress_signal.emit(min(progress, 100))

            self.output_signal.emit("Download complete!")

            # Extract using py7zr (preferred in AppImage) or system 7z
            self.output_signal.emit("Extracting archive...")
            self.progress_signal.emit(0)  # Reset progress for extraction

            # Prefer py7zr to avoid glibc/library conflicts in AppImage
            try:
                import py7zr
                self.output_signal.emit("Using py7zr for extraction...")
                with py7zr.SevenZipFile(temp_file, mode='r') as archive:
                    archive.extractall(path=self.destination_folder)
                self.output_signal.emit("Extraction complete!")
            except ImportError:
                # Fall back to system 7z with clean environment
                extract_cmd = None
                for cmd in ["7z", "7za", "7zr"]:
                    if shutil.which(cmd):
                        extract_cmd = cmd
                        break

                if not extract_cmd:
                    raise Exception("No 7z extraction tool found. Please install p7zip: sudo pacman -S p7zip")

                self.output_signal.emit(f"Using {extract_cmd} for extraction...")
                # Use clean environment to avoid AppImage library conflicts
                result = subprocess.run(
                    [extract_cmd, "x", "-y", f"-o{self.destination_folder}", temp_file],
                    capture_output=True,
                    text=True,
                    env=get_clean_env()
                )
                if result.returncode != 0:
                    raise Exception(f"Extraction failed: {result.stderr}")
                self.output_signal.emit("Extraction complete!")

            # Clean up temp file
            if os.path.exists(temp_file):
                os.remove(temp_file)
                self.output_signal.emit("Cleaned up temporary files.")

            # Verify ModOrganizer.exe exists
            mo2_exe = os.path.join(self.destination_folder, "ModOrganizer.exe")
            if not os.path.isfile(mo2_exe):
                raise Exception(f"ModOrganizer.exe not found in extracted files")

            self.output_signal.emit(f"ModOrganizer.exe found at: {mo2_exe}")

            # Create ModOrganizer.ini if game_data is provided
            if self.game_data:
                self.output_signal.emit("Creating ModOrganizer.ini...")
                self.create_mo2_ini()

            # Install vcredist into the game's prefix
            if self.game_data:
                self.install_vcredist()

            self.finished_signal.emit(True, self.destination_folder)

        except Exception as e:
            self.output_signal.emit(f"ERROR: {str(e)}")
            self.finished_signal.emit(False, str(e))

    def create_mo2_ini(self):
        """Create the ModOrganizer.ini configuration file."""
        game_name = self.game_data.get("name", "")
        data_path = self.game_data.get("data_path", "")

        # Get game folder (parent of Data folder)
        game_folder = os.path.dirname(data_path) if data_path else ""

        # Convert Linux path to Wine Z: drive path
        # /home/deck/... -> Z:\\home\\deck\\...
        wine_game_path = "Z:" + game_folder.replace("/", "\\\\") if game_folder else ""

        ini_content = f"""[General]
gameName={game_name}
gamePath=@ByteArray({wine_game_path})
selected_profile=@ByteArray(Default)
version=2.5.2
first_start=false

[Settings]
profile_local_inis=false
profile_local_saves=false
style=1809 Dark Mode.qss
"""

        ini_path = os.path.join(self.destination_folder, "ModOrganizer.ini")
        with open(ini_path, 'w', encoding='utf-8') as f:
            f.write(ini_content)

        self.output_signal.emit(f"Created ModOrganizer.ini for {game_name}")
        self.output_signal.emit(f"Game path: {wine_game_path}")

    def install_vcredist(self):
        """Download and install Visual C++ Redistributable into the game's Wine prefix."""
        plugins_path = self.game_data.get("plugins_path", "")
        if not plugins_path:
            self.output_signal.emit("Skipping vcredist: no plugins path configured.")
            return

        pfx_index = plugins_path.find("/pfx/")
        if pfx_index == -1:
            self.output_signal.emit("Skipping vcredist: could not determine Wine prefix.")
            return

        compat_data_path = plugins_path[:pfx_index]
        if not os.path.isdir(compat_data_path):
            self.output_signal.emit(f"Skipping vcredist: compatdata folder not found: {compat_data_path}")
            return

        # Detect Proton version from config_info
        config_info_path = os.path.join(compat_data_path, "config_info")
        proton_path = None

        if os.path.isfile(config_info_path):
            try:
                with open(config_info_path, 'r') as f:
                    lines = f.readlines()
                if len(lines) >= 2:
                    font_path = lines[1].strip()
                    files_index = font_path.find("/files/")
                    if files_index != -1:
                        proton_dir = font_path[:files_index]
                        candidate = os.path.join(proton_dir, "proton")
                        if os.path.isfile(candidate):
                            proton_path = candidate
            except Exception:
                pass

        if not proton_path:
            self.output_signal.emit("Skipping vcredist: could not detect Proton version. Make sure the game has been launched at least once via Steam.")
            return

        proton_name = os.path.basename(os.path.dirname(proton_path))

        # Download vcredist
        vcredist_url = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
        vcredist_file = os.path.join(tempfile.gettempdir(), "vc_redist.x64.exe")

        self.output_signal.emit(f"Downloading Visual C++ Redistributable...")
        try:
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            request = urllib.request.Request(vcredist_url)
            with urllib.request.urlopen(request, context=ssl_context) as response:
                with open(vcredist_file, 'wb') as f:
                    f.write(response.read())
            self.output_signal.emit("Download complete!")
        except Exception as e:
            self.output_signal.emit(f"Failed to download vcredist: {e}")
            return

        # Install vcredist silently into the game's prefix
        self.output_signal.emit(f"Installing vcredist into prefix via {proton_name}...")
        env = get_clean_env()
        env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = os.path.expanduser("~/.local/share/Steam")
        env["STEAM_COMPAT_DATA_PATH"] = compat_data_path

        try:
            result = subprocess.run(
                [proton_path, "run", vcredist_file, "/install", "/quiet", "/norestart"],
                env=env,
                cwd=tempfile.gettempdir(),
                capture_output=True,
                text=True,
                timeout=120
            )
            self.output_signal.emit("vcredist installation complete!")
        except subprocess.TimeoutExpired:
            self.output_signal.emit("vcredist installation timed out (this may be OK - it might still be installing in the background).")
        except Exception as e:
            self.output_signal.emit(f"vcredist installation failed: {e}")
        finally:
            # Clean up
            if os.path.exists(vcredist_file):
                os.remove(vcredist_file)


class BuildWorker(QThread):
    """Worker thread to run the build process without blocking the GUI."""
    output_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, modlist, mods_folder, output_dir, overwrite_folder=None, plugins_dest=None, game_data=None):
        super().__init__()
        self.modlist = modlist
        self.mods_folder = mods_folder
        self.output_dir = output_dir
        self.overwrite_folder = overwrite_folder
        self.plugins_dest = plugins_dest
        self.game_data = game_data

    def run(self):
        import io
        import contextlib

        # Capture stdout to emit as signals
        class OutputCapture(io.StringIO):
            def __init__(self, signal):
                super().__init__()
                self.signal = signal
                self.line_buffer = ""

            def write(self, text):
                self.line_buffer += text
                while '\n' in self.line_buffer:
                    line, self.line_buffer = self.line_buffer.split('\n', 1)
                    if line:
                        self.signal.emit(line)
                return len(text)

            def flush(self):
                if self.line_buffer:
                    self.signal.emit(self.line_buffer)
                    self.line_buffer = ""

        try:
            # Import build_data_folder module
            import build_data_folder

            # Capture output
            output_capture = OutputCapture(self.output_signal)

            with contextlib.redirect_stdout(output_capture):
                # Run the build process
                build_data_folder.build_data_folder(
                    self.modlist,
                    self.mods_folder,
                    self.output_dir,
                    self.overwrite_folder
                )

                # Handle ShaderCache if overwrite folder exists
                if self.overwrite_folder:
                    print()
                    print("=" * 70)
                    print("SHADERCACHE COPY")
                    print("=" * 70)
                    if build_data_folder.copy_shadercache_to_data(self.overwrite_folder, self.output_dir):
                        print("ShaderCache copied successfully!")
                    else:
                        print("No ShaderCache to copy")
                    print("=" * 70)

                # Handle plugins.txt symlinking
                if self.plugins_dest:
                    modlist_dir = os.path.dirname(self.modlist)
                    plugins_source = os.path.join(modlist_dir, 'plugins.txt')

                    if os.path.exists(plugins_source):
                        print()
                        print("=" * 70)
                        print("PLUGINS.TXT SYMLINK")
                        print("=" * 70)
                        print(f"Source:      {plugins_source}")
                        print(f"Destination: {os.path.join(self.plugins_dest, 'plugins.txt')}")

                        # Create destination directory if needed
                        if not os.path.exists(self.plugins_dest):
                            os.makedirs(self.plugins_dest)

                        plugins_dest_file = os.path.join(self.plugins_dest, 'plugins.txt')

                        # Remove existing plugins.txt
                        if os.path.exists(plugins_dest_file) or os.path.islink(plugins_dest_file):
                            os.remove(plugins_dest_file)

                        # Create symlink
                        os.symlink(plugins_source, plugins_dest_file)
                        print("Symlink created successfully!")
                        print("=" * 70)

                # Handle script extender launcher swap
                if self.game_data:
                    launcher_name = self.game_data.get("launcher_name")
                    script_extender_name = self.game_data.get("script_extender_name")

                    if launcher_name and script_extender_name:
                        # Get the game folder (parent of Data folder)
                        game_folder = os.path.dirname(self.output_dir)
                        launcher_path = os.path.join(game_folder, launcher_name)
                        script_extender_path = os.path.join(game_folder, script_extender_name)
                        backup_path = os.path.join(game_folder, launcher_name.replace(".exe", ".bak"))

                        if os.path.exists(script_extender_path):
                            print()
                            print("=" * 70)
                            print("SCRIPT EXTENDER LAUNCHER SWAP")
                            print("=" * 70)
                            print(f"Game folder: {game_folder}")
                            print(f"Launcher: {launcher_name}")
                            print(f"Script Extender: {script_extender_name}")

                            # Backup the original launcher if it exists and backup doesn't
                            if os.path.exists(launcher_path) and not os.path.exists(backup_path):
                                print(f"Backing up {launcher_name} -> {launcher_name.replace('.exe', '.bak')}")
                                shutil.copy2(launcher_path, backup_path)
                            elif os.path.exists(backup_path):
                                print(f"Backup already exists: {launcher_name.replace('.exe', '.bak')}")

                            # Copy script extender to launcher name (overwrite)
                            print(f"Copying {script_extender_name} -> {launcher_name}")
                            shutil.copy2(script_extender_path, launcher_path)
                            print("Script extender launcher swap completed!")
                            print("=" * 70)
                        else:
                            print()
                            print("=" * 70)
                            print("SCRIPT EXTENDER LAUNCHER SWAP - SKIPPED")
                            print("=" * 70)
                            print(f"Script extender not found: {script_extender_path}")
                            print("=" * 70)

            output_capture.flush()
            self.finished_signal.emit(True, "Build completed successfully!")

        except Exception as e:
            import traceback
            self.output_signal.emit(f"ERROR: {str(e)}")
            self.output_signal.emit(traceback.format_exc())
            self.finished_signal.emit(False, f"Build failed: {str(e)}")


class ModlistPanel(QFrame):
    """Panel to display and edit modlist.txt contents."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.modlist_path = None
        self.show_priority = True
        self.display_reversed = False  # Visual only - doesn't affect file
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # Header
        header_layout = QHBoxLayout()
        header_label = QLabel("Mod List")
        header_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        header_layout.addWidget(header_label)

        # Refresh button
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setMaximumWidth(60)
        refresh_btn.clicked.connect(self.load_modlist)
        header_layout.addWidget(refresh_btn)

        layout.addLayout(header_layout)

        # Options row
        options_layout = QHBoxLayout()

        # Show priority checkbox
        self.priority_checkbox = QCheckBox("Show Priority")
        self.priority_checkbox.setChecked(True)
        self.priority_checkbox.stateChanged.connect(self.on_priority_toggle)
        options_layout.addWidget(self.priority_checkbox)

        options_layout.addStretch()

        # Reverse order button
        self.reverse_btn = QPushButton("Reverse Order")
        self.reverse_btn.setMaximumWidth(100)
        self.reverse_btn.clicked.connect(self.reverse_order)
        options_layout.addWidget(self.reverse_btn)

        layout.addLayout(options_layout)

        # Mod list widget with drag and drop
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.list_widget.itemChanged.connect(self.on_item_changed)
        # Enable drag and drop reordering
        self.list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list_widget.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list_widget.model().rowsMoved.connect(self.on_rows_moved)
        layout.addWidget(self.list_widget)

        # Move buttons
        buttons_layout = QHBoxLayout()

        self.move_up_btn = QPushButton("Move Up")
        self.move_up_btn.clicked.connect(self.move_up)
        buttons_layout.addWidget(self.move_up_btn)

        self.move_down_btn = QPushButton("Move Down")
        self.move_down_btn.clicked.connect(self.move_down)
        buttons_layout.addWidget(self.move_down_btn)

        layout.addLayout(buttons_layout)

        # Status label
        self.status_label = QLabel("No modlist loaded")
        self.status_label.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(self.status_label)

    def set_modlist_path(self, path):
        """Set the path to modlist.txt and load it."""
        self.modlist_path = path
        self.load_modlist()

    def load_modlist(self):
        """Load and display the modlist.txt contents."""
        # Block signals while populating to prevent unnecessary saves
        self.list_widget.blockSignals(True)
        self.list_widget.clear()

        if not self.modlist_path or not os.path.isfile(self.modlist_path):
            self.status_label.setText("No modlist loaded")
            self.list_widget.blockSignals(False)
            return

        try:
            with open(self.modlist_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            # Parse mods from file
            mods_data = []
            enabled_count = 0

            for line in lines:
                line = line.rstrip('\n\r')
                if not line.strip():
                    continue

                # Skip separator lines (starting with *)
                if line.strip().startswith('*'):
                    continue

                if line.startswith('+'):
                    mod_name = line[1:].strip()
                    # Skip separator mods (pseudo mods used by MO2)
                    if mod_name.endswith('_separator'):
                        continue
                    mods_data.append({'name': mod_name, 'enabled': True})
                    enabled_count += 1
                elif line.startswith('-'):
                    mod_name = line[1:].strip()
                    # Skip separator mods (pseudo mods used by MO2)
                    if mod_name.endswith('_separator'):
                        continue
                    mods_data.append({'name': mod_name, 'enabled': False})

            # If display is reversed, show in reverse order (but file order is preserved)
            if self.display_reversed:
                mods_data = list(reversed(mods_data))

            # Populate the list widget
            for mod in mods_data:
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, mod['name'])
                item.setCheckState(Qt.CheckState.Checked if mod['enabled'] else Qt.CheckState.Unchecked)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                self.list_widget.addItem(item)

            # Update display text with priority numbers
            self.update_display_text()

            view_mode = " (reversed view)" if self.display_reversed else ""
            self.status_label.setText(f"{enabled_count}/{len(mods_data)} mods enabled{view_mode}")

        except Exception as e:
            self.status_label.setText(f"Error: {str(e)}")
        finally:
            self.list_widget.blockSignals(False)

    def update_display_text(self):
        """Update the display text for all items based on priority setting.

        Priority is calculated from the bottom of the file (bottom = 0 = highest priority).
        This matches MO2's behavior where mods at the bottom win conflicts.
        """
        self.list_widget.blockSignals(True)
        total_count = self.list_widget.count()
        for i in range(total_count):
            item = self.list_widget.item(i)
            mod_name = item.data(Qt.ItemDataRole.UserRole)
            # Calculate priority based on file position, not display position
            if self.display_reversed:
                # In reversed view, item 0 in display is the last in file (priority 0)
                priority = i
            else:
                # In normal view, item 0 in display is first in file (highest priority number)
                priority = total_count - 1 - i
            if self.show_priority:
                item.setText(f"[{priority}] {mod_name}")
            else:
                item.setText(mod_name)
        self.list_widget.blockSignals(False)

    def on_priority_toggle(self, state):
        """Handle priority checkbox toggle."""
        self.show_priority = state == Qt.CheckState.Checked.value
        self.update_display_text()

    def reverse_order(self):
        """Toggle reversed visual display (does not modify the file)."""
        self.display_reversed = not self.display_reversed
        self.load_modlist()  # Reload with new display order

    def on_rows_moved(self):
        """Handle drag and drop reordering."""
        self.update_display_text()
        self.save_modlist()

    def on_item_changed(self, item):
        """Handle checkbox state changes."""
        self.save_modlist()

    def move_up(self):
        """Move the selected mod up in the list (higher priority)."""
        current_row = self.list_widget.currentRow()
        if current_row <= 0:
            return

        # Block signals to prevent multiple saves
        self.list_widget.blockSignals(True)

        # Take the item and insert it above
        item = self.list_widget.takeItem(current_row)
        self.list_widget.insertItem(current_row - 1, item)
        self.list_widget.setCurrentRow(current_row - 1)

        self.list_widget.blockSignals(False)
        self.update_display_text()
        self.save_modlist()

    def move_down(self):
        """Move the selected mod down in the list (lower priority)."""
        current_row = self.list_widget.currentRow()
        if current_row < 0 or current_row >= self.list_widget.count() - 1:
            return

        # Block signals to prevent multiple saves
        self.list_widget.blockSignals(True)

        # Take the item and insert it below
        item = self.list_widget.takeItem(current_row)
        self.list_widget.insertItem(current_row + 1, item)
        self.list_widget.setCurrentRow(current_row + 1)

        self.list_widget.blockSignals(False)
        self.update_display_text()
        self.save_modlist()

    def save_modlist(self):
        """Save the current list back to modlist.txt."""
        if not self.modlist_path:
            return

        try:
            # Collect items in display order
            items_data = []
            for i in range(self.list_widget.count()):
                item = self.list_widget.item(i)
                mod_name = item.data(Qt.ItemDataRole.UserRole)
                is_enabled = item.checkState() == Qt.CheckState.Checked
                items_data.append({'name': mod_name, 'enabled': is_enabled})

            # If display is reversed, reverse back to get file order
            if self.display_reversed:
                items_data = list(reversed(items_data))

            # Write to file
            lines = []
            for data in items_data:
                prefix = '+' if data['enabled'] else '-'
                lines.append(f"{prefix}{data['name']}\n")

            with open(self.modlist_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)

            # Update status
            enabled_count = sum(1 for d in items_data if d['enabled'])
            view_mode = " (reversed view)" if self.display_reversed else ""
            self.status_label.setText(f"{enabled_count}/{len(items_data)} mods enabled (saved){view_mode}")

        except Exception as e:
            self.status_label.setText(f"Save error: {str(e)}")


class PluginsPanel(QFrame):
    """Panel to display and edit plugins.txt contents."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.plugins_path = None
        self.show_priority = True
        self.display_reversed = False  # Visual only - doesn't affect file
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # Header
        header_layout = QHBoxLayout()
        header_label = QLabel("Plugin List")
        header_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        header_layout.addWidget(header_label)

        # Refresh button
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setMaximumWidth(60)
        refresh_btn.clicked.connect(self.load_plugins)
        header_layout.addWidget(refresh_btn)

        layout.addLayout(header_layout)

        # Options row
        options_layout = QHBoxLayout()

        # Show priority checkbox
        self.priority_checkbox = QCheckBox("Show Priority")
        self.priority_checkbox.setChecked(True)
        self.priority_checkbox.stateChanged.connect(self.on_priority_toggle)
        options_layout.addWidget(self.priority_checkbox)

        options_layout.addStretch()

        # Reverse order button
        self.reverse_btn = QPushButton("Reverse Order")
        self.reverse_btn.setMaximumWidth(100)
        self.reverse_btn.clicked.connect(self.reverse_order)
        options_layout.addWidget(self.reverse_btn)

        layout.addLayout(options_layout)

        # Plugin list widget with drag and drop
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.list_widget.itemChanged.connect(self.on_item_changed)
        # Enable drag and drop reordering
        self.list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list_widget.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list_widget.model().rowsMoved.connect(self.on_rows_moved)
        layout.addWidget(self.list_widget)

        # Move buttons
        buttons_layout = QHBoxLayout()

        self.move_up_btn = QPushButton("Move Up")
        self.move_up_btn.clicked.connect(self.move_up)
        buttons_layout.addWidget(self.move_up_btn)

        self.move_down_btn = QPushButton("Move Down")
        self.move_down_btn.clicked.connect(self.move_down)
        buttons_layout.addWidget(self.move_down_btn)

        layout.addLayout(buttons_layout)

        # Status label
        self.status_label = QLabel("No plugins loaded")
        self.status_label.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(self.status_label)

    def set_plugins_path(self, path):
        """Set the path to plugins.txt and load it."""
        self.plugins_path = path
        self.load_plugins()

    def load_plugins(self):
        """Load and display the plugins.txt contents."""
        # Block signals while populating to prevent unnecessary saves
        self.list_widget.blockSignals(True)
        self.list_widget.clear()

        if not self.plugins_path or not os.path.isfile(self.plugins_path):
            self.status_label.setText("No plugins loaded")
            self.list_widget.blockSignals(False)
            return

        try:
            with open(self.plugins_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            # Parse plugins from file
            plugins_data = []
            enabled_count = 0

            for line in lines:
                line = line.rstrip('\n\r')
                if not line.strip():
                    continue

                # Skip comment lines
                if line.strip().startswith('#'):
                    continue

                # Check if plugin is enabled (starts with *)
                if line.startswith('*'):
                    plugin_name = line[1:].strip()
                    plugins_data.append({'name': plugin_name, 'enabled': True})
                    enabled_count += 1
                else:
                    plugin_name = line.strip()
                    plugins_data.append({'name': plugin_name, 'enabled': False})

            # If display is reversed, show in reverse order (but file order is preserved)
            if self.display_reversed:
                plugins_data = list(reversed(plugins_data))

            # Populate the list widget
            for plugin in plugins_data:
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, plugin['name'])
                item.setCheckState(Qt.CheckState.Checked if plugin['enabled'] else Qt.CheckState.Unchecked)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                self.list_widget.addItem(item)

            # Update display text with priority numbers
            self.update_display_text()

            view_mode = " (reversed view)" if self.display_reversed else ""
            self.status_label.setText(f"{enabled_count}/{len(plugins_data)} plugins enabled{view_mode}")

        except Exception as e:
            self.status_label.setText(f"Error: {str(e)}")
        finally:
            self.list_widget.blockSignals(False)

    def update_display_text(self):
        """Update the display text for all items based on priority setting.

        Priority is calculated from the top of the file (top = 0 = loads first).
        For plugins, lower numbers load first.
        """
        self.list_widget.blockSignals(True)
        total_count = self.list_widget.count()
        for i in range(total_count):
            item = self.list_widget.item(i)
            plugin_name = item.data(Qt.ItemDataRole.UserRole)
            # Calculate priority based on file position
            if self.display_reversed:
                # In reversed view, item 0 in display is the last in file
                priority = total_count - 1 - i
            else:
                # In normal view, item 0 in display is first in file (priority 0)
                priority = i
            if self.show_priority:
                item.setText(f"[{priority}] {plugin_name}")
            else:
                item.setText(plugin_name)
        self.list_widget.blockSignals(False)

    def on_priority_toggle(self, state):
        """Handle priority checkbox toggle."""
        self.show_priority = state == Qt.CheckState.Checked.value
        self.update_display_text()

    def reverse_order(self):
        """Toggle reversed visual display (does not modify the file)."""
        self.display_reversed = not self.display_reversed
        self.load_plugins()  # Reload with new display order

    def on_rows_moved(self):
        """Handle drag and drop reordering."""
        self.update_display_text()
        self.save_plugins()

    def on_item_changed(self, item):
        """Handle checkbox state changes."""
        self.save_plugins()

    def move_up(self):
        """Move the selected plugin up in the list."""
        current_row = self.list_widget.currentRow()
        if current_row <= 0:
            return

        # Block signals to prevent multiple saves
        self.list_widget.blockSignals(True)

        # Take the item and insert it above
        item = self.list_widget.takeItem(current_row)
        self.list_widget.insertItem(current_row - 1, item)
        self.list_widget.setCurrentRow(current_row - 1)

        self.list_widget.blockSignals(False)
        self.update_display_text()
        self.save_plugins()

    def move_down(self):
        """Move the selected plugin down in the list."""
        current_row = self.list_widget.currentRow()
        if current_row < 0 or current_row >= self.list_widget.count() - 1:
            return

        # Block signals to prevent multiple saves
        self.list_widget.blockSignals(True)

        # Take the item and insert it below
        item = self.list_widget.takeItem(current_row)
        self.list_widget.insertItem(current_row + 1, item)
        self.list_widget.setCurrentRow(current_row + 1)

        self.list_widget.blockSignals(False)
        self.update_display_text()
        self.save_plugins()

    def save_plugins(self):
        """Save the current list back to plugins.txt."""
        if not self.plugins_path:
            return

        try:
            # Collect items in display order
            items_data = []
            for i in range(self.list_widget.count()):
                item = self.list_widget.item(i)
                plugin_name = item.data(Qt.ItemDataRole.UserRole)
                is_enabled = item.checkState() == Qt.CheckState.Checked
                items_data.append({'name': plugin_name, 'enabled': is_enabled})

            # If display is reversed, reverse back to get file order
            if self.display_reversed:
                items_data = list(reversed(items_data))

            # Write to file
            lines = []
            for data in items_data:
                if data['enabled']:
                    lines.append(f"*{data['name']}\n")
                else:
                    lines.append(f"{data['name']}\n")

            with open(self.plugins_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)

            # Update status
            enabled_count = sum(1 for d in items_data if d['enabled'])
            view_mode = " (reversed view)" if self.display_reversed else ""
            self.status_label.setText(f"{enabled_count}/{len(items_data)} plugins enabled (saved){view_mode}")

        except Exception as e:
            self.status_label.setText(f"Save error: {str(e)}")


class MO2MergerGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bethesda Modding Tool for Steam Deck / Linux")
        self.setMinimumSize(1000, 800)

        # Store paths
        self.mo2_path = ""
        self.mods_folder = ""
        self.overwrite_folder = ""
        self.profiles_folder = ""
        self.selected_profile = ""

        self.init_ui()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setSpacing(10)

        # Create a splitter to allow resizing between left panel and modlist
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel (main controls)
        left_panel = QWidget()
        layout = QVBoxLayout(left_panel)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)

        # MO2 Location Group
        mo2_group = QGroupBox("Mod Organizer 2 Location")
        mo2_layout = QVBoxLayout()

        # Scan for MO2 instances
        self.mo2_instances = scan_for_mo2_instances()

        # MO2 instance selector
        mo2_select_layout = QHBoxLayout()
        mo2_select_layout.addWidget(QLabel("Instance:"))
        self.mo2_combo = QComboBox()
        self.mo2_combo.setMinimumWidth(300)

        # Add found instances
        for display_name, folder_path in self.mo2_instances:
            self.mo2_combo.addItem(display_name, folder_path)

        # Add manual option
        self.mo2_combo.addItem("Manual...", None)
        self.mo2_combo.currentIndexChanged.connect(self.on_mo2_combo_changed)
        mo2_select_layout.addWidget(self.mo2_combo)

        # Rescan button
        rescan_btn = QPushButton("Rescan")
        rescan_btn.setToolTip("Scan /home/ for Mod Organizer 2 installations")
        rescan_btn.clicked.connect(self.rescan_mo2_instances)
        mo2_select_layout.addWidget(rescan_btn)

        mo2_layout.addLayout(mo2_select_layout)

        # Full path label (shows the complete path of selected instance)
        self.mo2_path_label = QLabel("Path: Not selected")
        self.mo2_path_label.setStyleSheet("color: gray; font-size: 11px;")
        self.mo2_path_label.setWordWrap(True)
        mo2_layout.addWidget(self.mo2_path_label)

        # Instance action buttons row
        instance_btn_layout = QHBoxLayout()

        # Run MO2 button
        self.run_mo2_btn = QPushButton("Run MO2")
        self.run_mo2_btn.setEnabled(False)
        self.run_mo2_btn.setToolTip("Launch ModOrganizer.exe using the game's Proton version")
        self.run_mo2_btn.clicked.connect(self.run_mo2)
        instance_btn_layout.addWidget(self.run_mo2_btn)

        # Add Instance button
        self.add_instance_btn = QPushButton("Add Instance")
        self.add_instance_btn.setToolTip("Download and install a new Mod Organizer 2 instance")
        self.add_instance_btn.clicked.connect(self.add_mo2_instance)
        instance_btn_layout.addWidget(self.add_instance_btn)

        # Open Instance Folder button
        self.open_instance_btn = QPushButton("Open Folder")
        self.open_instance_btn.setEnabled(False)
        self.open_instance_btn.setToolTip("Open the game folder for the selected MO2 instance")
        self.open_instance_btn.clicked.connect(self.open_instance_folder)
        instance_btn_layout.addWidget(self.open_instance_btn)

        mo2_layout.addLayout(instance_btn_layout)

        # Script Extender buttons row
        se_layout = QHBoxLayout()
        se_layout.addWidget(QLabel("Script Extender:"))

        self.se_download_btn = QPushButton("Download Page")
        self.se_download_btn.setEnabled(False)
        self.se_download_btn.setToolTip("Open the script extender download page in your browser")
        self.se_download_btn.clicked.connect(self.open_script_extender_download)
        se_layout.addWidget(self.se_download_btn)

        self.se_install_btn = QPushButton("Install from Zip")
        self.se_install_btn.setEnabled(False)
        self.se_install_btn.setToolTip("Install a script extender from a downloaded zip file to the game's root directory")
        self.se_install_btn.clicked.connect(self.install_script_extender)
        se_layout.addWidget(self.se_install_btn)

        self.se_uninstall_btn = QPushButton("Uninstall")
        self.se_uninstall_btn.setEnabled(False)
        self.se_uninstall_btn.setToolTip("Remove previously installed script extender files")
        self.se_uninstall_btn.clicked.connect(self.uninstall_script_extender)
        se_layout.addWidget(self.se_uninstall_btn)

        se_layout.addStretch()
        mo2_layout.addLayout(se_layout)

        # Script Extender status label
        self.se_status_label = QLabel("")
        mo2_layout.addWidget(self.se_status_label)

        # Manual path input (shown when "Manual..." is selected or no instances found)
        self.mo2_manual_layout = QHBoxLayout()
        self.mo2_path_edit = QLineEdit()
        self.mo2_path_edit.setPlaceholderText("Enter or browse for Mod Organizer 2 folder...")
        self.mo2_path_edit.textChanged.connect(self.on_mo2_path_changed)
        mo2_browse_btn = QPushButton("Browse...")
        mo2_browse_btn.clicked.connect(self.browse_mo2_folder)
        self.mo2_manual_layout.addWidget(self.mo2_path_edit)
        self.mo2_manual_layout.addWidget(mo2_browse_btn)
        mo2_layout.addLayout(self.mo2_manual_layout)

        # Status labels for mods and overwrite folders
        self.mods_status_label = QLabel("Mods folder: Not found")
        self.overwrite_status_label = QLabel("Overwrite folder: Not found")
        mo2_layout.addWidget(self.mods_status_label)
        mo2_layout.addWidget(self.overwrite_status_label)

        mo2_group.setLayout(mo2_layout)
        layout.addWidget(mo2_group)

        # Set initial state based on found instances
        if self.mo2_instances:
            # Auto-select first instance
            self.mo2_combo.setCurrentIndex(0)
            self.mo2_path_edit.setText(self.mo2_instances[0][1])
            self.mo2_path_label.setText(f"Path: {self.mo2_instances[0][1]}")
            self.mo2_path_edit.setVisible(False)
            # Hide browse button too
            for i in range(self.mo2_manual_layout.count()):
                widget = self.mo2_manual_layout.itemAt(i).widget()
                if widget:
                    widget.setVisible(False)
        else:
            # No instances found, show manual input
            self.mo2_combo.setCurrentIndex(0)  # "Manual..."
            self.mo2_path_label.setText("Path: No instances found - enter path manually")

        # Profile Selection Group
        profile_group = QGroupBox("Profile Selection")
        profile_layout = QVBoxLayout()

        self.profile_combo = QComboBox()
        self.profile_combo.setEnabled(False)
        self.profile_combo.currentTextChanged.connect(self.on_profile_changed)
        profile_layout.addWidget(self.profile_combo)

        self.modlist_status_label = QLabel("modlist.txt: Not found")
        self.plugins_status_label = QLabel("plugins.txt: Not found")
        profile_layout.addWidget(self.modlist_status_label)
        profile_layout.addWidget(self.plugins_status_label)

        profile_group.setLayout(profile_layout)
        layout.addWidget(profile_group)

        # Output Locations Group
        output_group = QGroupBox("Output Locations")
        output_layout = QVBoxLayout()

        # Game selection dropdown
        self.game_paths = load_game_paths()
        game_select_layout = QHBoxLayout()
        game_select_layout.addWidget(QLabel("Game:"))
        self.game_combo = QComboBox()
        self.game_combo.setMinimumWidth(200)

        # Add games from config (only those that are installed)
        for game in self.game_paths:
            data_path = game.get("data_path", "")
            if data_path:
                game_folder = os.path.dirname(data_path)
                if os.path.isdir(game_folder):
                    self.game_combo.addItem(game["name"], game)

        # Add "Custom..." option
        self.game_combo.addItem("Custom...", None)
        self.game_combo.currentIndexChanged.connect(self.on_game_changed)
        game_select_layout.addWidget(self.game_combo)

        # Winecfg button
        self.winecfg_btn = QPushButton("Winecfg")
        self.winecfg_btn.setToolTip("Open Wine configuration for the selected game's prefix")
        self.winecfg_btn.clicked.connect(self.run_winecfg)
        game_select_layout.addWidget(self.winecfg_btn)

        # Protontricks button
        self.winetricks_btn = QPushButton("Protontricks")
        self.winetricks_btn.setToolTip("Open Protontricks (winetricks) for the selected game's prefix")
        self.winetricks_btn.clicked.connect(self.run_winetricks)
        game_select_layout.addWidget(self.winetricks_btn)

        # Run EXE in game prefix button
        self.game_run_exe_btn = QPushButton("Run EXE")
        self.game_run_exe_btn.setToolTip("Run an executable in the selected game's Wine prefix")
        self.game_run_exe_btn.clicked.connect(self.run_exe_in_game_prefix)
        game_select_layout.addWidget(self.game_run_exe_btn)

        # Change Prefix button
        self.change_prefix_btn = QPushButton("Change Prefix")
        self.change_prefix_btn.setToolTip("Select a different wine prefix for the selected game")
        self.change_prefix_btn.clicked.connect(self.change_game_prefix)
        game_select_layout.addWidget(self.change_prefix_btn)

        # Downgrade button (Fallout 3 only)
        self.downgrade_btn = QPushButton("Downgrade")
        self.downgrade_btn.setToolTip("Downgrade Fallout 3 using the Updated Unofficial Fallout 3 Patch patcher")
        self.downgrade_btn.clicked.connect(self.run_downgrade)
        self.downgrade_btn.setVisible(False)
        game_select_layout.addWidget(self.downgrade_btn)

        game_select_layout.addStretch()
        output_layout.addLayout(game_select_layout)

        # Data folder output
        data_output_layout = QHBoxLayout()
        data_output_layout.addWidget(QLabel("Data Folder:"))
        self.data_output_edit = QLineEdit()
        self.data_output_edit.setPlaceholderText("Select output location for merged Data folder...")
        self.data_output_edit.textChanged.connect(self.update_build_button)
        data_output_browse_btn = QPushButton("Browse...")
        data_output_browse_btn.clicked.connect(self.browse_data_output)
        data_output_layout.addWidget(self.data_output_edit)
        data_output_layout.addWidget(data_output_browse_btn)
        output_layout.addLayout(data_output_layout)

        # plugins.txt output
        plugins_output_layout = QHBoxLayout()
        plugins_output_layout.addWidget(QLabel("plugins.txt:"))
        self.plugins_output_edit = QLineEdit()
        self.plugins_output_edit.setPlaceholderText("Select location for plugins.txt symlink...")
        plugins_output_browse_btn = QPushButton("Browse...")
        plugins_output_browse_btn.clicked.connect(self.browse_plugins_output)
        plugins_output_layout.addWidget(self.plugins_output_edit)
        plugins_output_layout.addWidget(plugins_output_browse_btn)
        output_layout.addLayout(plugins_output_layout)

        # Set initial state - show paths from first game if available
        if self.game_paths:
            self.data_output_edit.setText(self.game_paths[0].get("data_path", ""))
            self.plugins_output_edit.setText(self.game_paths[0].get("plugins_path", ""))
            self.downgrade_btn.setVisible(self.game_paths[0].get("name") == "Fallout 3")

        output_group.setLayout(output_layout)
        layout.addWidget(output_group)

        # Buttons layout
        buttons_layout = QHBoxLayout()

        # Build Button
        self.build_btn = QPushButton("Build Data Folder")
        self.build_btn.setEnabled(False)
        self.build_btn.setMinimumHeight(40)
        self.build_btn.clicked.connect(self.start_build)
        self.build_btn.setToolTip(
            "Build the merged Data folder from all enabled mods.\n"
            "Will create the DataFolder mod automatically if it doesn't exist."
        )
        buttons_layout.addWidget(self.build_btn)

        # Restore Data Folder Button
        self.restore_datafolder_btn = QPushButton("Restore Data Folder")
        self.restore_datafolder_btn.setEnabled(False)
        self.restore_datafolder_btn.setMinimumHeight(40)
        self.restore_datafolder_btn.clicked.connect(self.restore_datafolder)
        self.restore_datafolder_btn.setToolTip(
            "Delete the Data folder and move contents from DataFolder mod back.\n"
            "Removes DataFolder entry from modlist.txt.\n"
            "Only available when DataFolder mod exists."
        )
        buttons_layout.addWidget(self.restore_datafolder_btn)

        layout.addLayout(buttons_layout)

        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Output Log Group
        log_group = QGroupBox("Build Output")
        log_layout = QVBoxLayout()

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Monospace", 9))
        log_layout.addWidget(self.log_text)

        log_group.setLayout(log_layout)
        layout.addWidget(log_group)

        # Add left panel to splitter
        splitter.addWidget(left_panel)

        # Create a vertical splitter for the two right panels (modlist and plugins)
        right_splitter = QSplitter(Qt.Orientation.Vertical)

        # Create and add the modlist panel
        self.modlist_panel = ModlistPanel()
        right_splitter.addWidget(self.modlist_panel)

        # Create and add the plugins panel
        self.plugins_panel = PluginsPanel()
        right_splitter.addWidget(self.plugins_panel)

        # Set equal sizes for modlist and plugins panels
        right_splitter.setSizes([400, 400])

        # Add right splitter to main splitter
        splitter.addWidget(right_splitter)

        # Set initial splitter sizes (left panel larger than right panels)
        splitter.setSizes([600, 400])

        # Add splitter to main layout
        main_layout.addWidget(splitter)

        # Trigger initial validation now that all UI elements exist
        if self.mo2_path:
            self.validate_mo2_folder()

    def on_mo2_combo_changed(self, index):
        """Handle MO2 instance selection change."""
        folder_path = self.mo2_combo.currentData()

        if folder_path is None:  # "Manual..." option
            # Show manual input fields
            self.mo2_path_edit.setVisible(True)
            for i in range(self.mo2_manual_layout.count()):
                widget = self.mo2_manual_layout.itemAt(i).widget()
                if widget:
                    widget.setVisible(True)
            self.mo2_path_edit.clear()
            self.mo2_path_edit.setFocus()
            self.mo2_path_label.setText("Path: Enter path manually")
        else:
            # Hide manual input fields and set path
            self.mo2_path_edit.setVisible(False)
            for i in range(self.mo2_manual_layout.count()):
                widget = self.mo2_manual_layout.itemAt(i).widget()
                if widget:
                    widget.setVisible(False)
            self.mo2_path_edit.setText(folder_path)
            self.mo2_path_label.setText(f"Path: {folder_path}")

    def rescan_mo2_instances(self):
        """Rescan for MO2 instances and update the combo box."""
        # Remember current selection if possible
        current_path = self.mo2_combo.currentData()

        # Rescan
        self.mo2_instances = scan_for_mo2_instances()

        # Update combo box
        self.mo2_combo.blockSignals(True)
        self.mo2_combo.clear()

        for display_name, folder_path in self.mo2_instances:
            self.mo2_combo.addItem(display_name, folder_path)

        self.mo2_combo.addItem("Manual...", None)

        # Try to restore previous selection
        restored = False
        if current_path:
            for i in range(self.mo2_combo.count()):
                if self.mo2_combo.itemData(i) == current_path:
                    self.mo2_combo.setCurrentIndex(i)
                    restored = True
                    break

        self.mo2_combo.blockSignals(False)

        # Update UI based on results
        if self.mo2_instances and not restored:
            self.mo2_combo.setCurrentIndex(0)
            self.on_mo2_combo_changed(0)
        elif not self.mo2_instances:
            # No instances found, show manual input
            self.mo2_combo.setCurrentIndex(0)
            self.on_mo2_combo_changed(0)

        # Show message about scan results
        if self.mo2_instances:
            QMessageBox.information(
                self,
                "Scan Complete",
                f"Found {len(self.mo2_instances)} Mod Organizer 2 installation(s)."
            )
        else:
            QMessageBox.information(
                self,
                "Scan Complete",
                "No Mod Organizer 2 installations found.\n"
                "Please enter the path manually."
            )

    def browse_mo2_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Mod Organizer 2 Folder",
            os.path.expanduser("~")
        )
        if folder:
            # Switch to manual mode if not already
            manual_index = self.mo2_combo.count() - 1
            if self.mo2_combo.currentIndex() != manual_index:
                self.mo2_combo.blockSignals(True)
                self.mo2_combo.setCurrentIndex(manual_index)
                self.mo2_combo.blockSignals(False)
                # Show manual input fields
                self.mo2_path_edit.setVisible(True)
                for i in range(self.mo2_manual_layout.count()):
                    widget = self.mo2_manual_layout.itemAt(i).widget()
                    if widget:
                        widget.setVisible(True)
            self.mo2_path_edit.setText(folder)

    def run_mo2(self):
        """Launch ModOrganizer.exe using the game's Proton version and prefix."""
        game_data = self.game_combo.currentData()
        if not game_data:
            QMessageBox.warning(self, "Error", "No game selected. Please select a game first.")
            return

        mo2_exe = os.path.join(self.mo2_path, "ModOrganizer.exe")
        if not os.path.isfile(mo2_exe):
            QMessageBox.warning(self, "Error", f"ModOrganizer.exe not found at:\n{mo2_exe}")
            return

        # Detect proton and prefix from the game's compatdata
        plugins_path = game_data.get("plugins_path", "")
        if not plugins_path:
            QMessageBox.warning(self, "Error", "No plugins path configured for this game.")
            return

        pfx_index = plugins_path.find("/pfx/")
        if pfx_index == -1:
            QMessageBox.warning(self, "Error", "Could not determine Wine prefix from plugins path.")
            return

        compat_data_path = plugins_path[:pfx_index]

        if not os.path.isdir(compat_data_path):
            QMessageBox.warning(self, "Error", f"Compatdata folder not found:\n{compat_data_path}")
            return

        # Detect which Proton version was used by reading config_info
        config_info_path = os.path.join(compat_data_path, "config_info")
        proton_path = None

        if os.path.isfile(config_info_path):
            try:
                with open(config_info_path, 'r') as f:
                    lines = f.readlines()
                if len(lines) >= 2:
                    font_path = lines[1].strip()
                    files_index = font_path.find("/files/")
                    if files_index != -1:
                        proton_dir = font_path[:files_index]
                        candidate = os.path.join(proton_dir, "proton")
                        if os.path.isfile(candidate):
                            proton_path = candidate
            except Exception:
                pass

        if not proton_path:
            QMessageBox.warning(
                self, "Error",
                f"Could not detect Proton version for {game_data['name']}.\n\n"
                f"The config_info file was not found or could not be parsed at:\n"
                f"{config_info_path}\n\n"
                "Make sure the game has been launched at least once via Steam."
            )
            return

        # Set up environment (clean AppImage paths to avoid conflicts with Proton)
        env = get_clean_env()
        env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = os.path.expanduser("~/.local/share/Steam")
        env["STEAM_COMPAT_DATA_PATH"] = compat_data_path

        proton_name = os.path.basename(os.path.dirname(proton_path))

        # Launch MO2 via Proton (non-blocking)
        try:
            subprocess.Popen([proton_path, "run", mo2_exe], env=env, cwd=self.mo2_path)
            self.append_log(f"Launched ModOrganizer.exe via {proton_name}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to launch ModOrganizer.exe:\n{str(e)}")

    def open_script_extender_download(self):
        """Open the script extender download page for the selected game."""
        game_data = self.game_combo.currentData()
        if not game_data:
            QMessageBox.warning(self, "Error", "No game selected.")
            return

        url = game_data.get("script_extender_download", "")
        if not url:
            QMessageBox.warning(
                self,
                "Error",
                f"No script extender download URL configured for {game_data.get('name', 'this game')}."
            )
            return

        subprocess.Popen(["xdg-open", url], env=get_clean_env())

    def install_script_extender(self):
        """Install a script extender from a user-selected zip file to the game's root directory."""
        game_data = self.game_combo.currentData()
        if not game_data:
            QMessageBox.warning(self, "Error", "No game selected.")
            return

        data_path = game_data.get("data_path", "")
        if not data_path:
            QMessageBox.warning(self, "Error", "No data path configured for this game.")
            return

        game_root = os.path.dirname(data_path)
        if not os.path.isdir(game_root):
            QMessageBox.warning(
                self,
                "Error",
                f"Game root directory not found:\n{game_root}"
            )
            return

        expected_exe = game_data.get("script_extender_name", "")

        # Ask user to select the archive file
        archive_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Script Extender Archive",
            os.path.expanduser("~"),
            "Archives (*.zip *.7z);;Zip Files (*.zip);;7z Files (*.7z);;All Files (*)"
        )

        if not archive_path:
            return

        try:
            # Extract to a temp directory first so we can validate and strip root folder
            temp_dir = tempfile.mkdtemp(prefix="se_install_")

            try:
                if archive_path.lower().endswith(".zip"):
                    with zipfile.ZipFile(archive_path, 'r') as zf:
                        zf.extractall(temp_dir)
                else:
                    # Use py7zr or system 7z, falling back if py7zr fails
                    # (py7zr doesn't support all filters, e.g. BCJ2)
                    extracted = False
                    try:
                        import py7zr
                        with py7zr.SevenZipFile(archive_path, mode='r') as archive:
                            archive.extractall(path=temp_dir)
                        extracted = True
                    except Exception:
                        pass
                    if not extracted:
                        extract_cmd = None
                        for cmd in ["7z", "7za", "7zr"]:
                            if shutil.which(cmd):
                                extract_cmd = cmd
                                break
                        if not extract_cmd:
                            raise Exception("No 7z extraction tool found. Please install p7zip: sudo pacman -S p7zip")
                        result = subprocess.run(
                            [extract_cmd, "x", "-y", f"-o{temp_dir}", archive_path],
                            capture_output=True, text=True, env=get_clean_env()
                        )
                        if result.returncode != 0:
                            raise Exception(f"Extraction failed: {result.stderr}")

                # Determine the actual content root (strip single root folder if present)
                top_entries = os.listdir(temp_dir)
                if len(top_entries) == 1 and os.path.isdir(os.path.join(temp_dir, top_entries[0])):
                    content_root = os.path.join(temp_dir, top_entries[0])
                else:
                    content_root = temp_dir

                # Validate the archive contains the expected script extender exe
                if expected_exe:
                    found_exe = False
                    for dirpath, dirnames, filenames in os.walk(content_root):
                        if any(f.lower() == expected_exe.lower() for f in filenames):
                            found_exe = True
                            break

                    if not found_exe:
                        reply = QMessageBox.warning(
                            self,
                            "Wrong Script Extender",
                            f"This archive does not contain '{expected_exe}' which is the expected "
                            f"script extender for {game_data.get('name', 'this game')}.\n\n"
                            f"Are you sure you want to install it anyway?",
                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                            QMessageBox.StandardButton.No
                        )
                        if reply != QMessageBox.StandardButton.Yes:
                            return

                # Check if restore data folder should run first
                data_output_path = self.data_output_edit.text() if hasattr(self, 'data_output_edit') else ""
                datafolder_exists = bool(
                    self.mods_folder and
                    os.path.isdir(os.path.join(self.mods_folder, "DataFolder"))
                )
                can_restore = bool(
                    self.mods_folder and
                    self.profiles_folder and
                    self.selected_profile and
                    os.path.isfile(os.path.join(self.profiles_folder, self.selected_profile, "modlist.txt")) and
                    data_output_path and
                    datafolder_exists
                )

                if can_restore:
                    self.restore_datafolder()

                # Copy extracted files to game root and track installed paths
                installed_files = []
                for dirpath, dirnames, filenames in os.walk(content_root):
                    rel_dir = os.path.relpath(dirpath, content_root)
                    dest_dir = os.path.join(game_root, rel_dir) if rel_dir != '.' else game_root
                    os.makedirs(dest_dir, exist_ok=True)
                    for filename in filenames:
                        src_file = os.path.join(dirpath, filename)
                        dst_file = os.path.join(dest_dir, filename)
                        shutil.copy2(src_file, dst_file)
                        installed_files.append(dst_file)

                # Save manifest of installed files
                manifest_path = self.get_se_manifest_path(game_data)
                if manifest_path:
                    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
                    with open(manifest_path, 'w', encoding='utf-8') as f:
                        json.dump({"game": game_data.get("name", ""), "files": installed_files}, f, indent=4)

                self.append_log(f"Script extender installed to: {game_root}")
                self.append_log(f"Installed {len(installed_files)} files")
                self.update_build_button()
                QMessageBox.information(
                    self,
                    "Success",
                    f"Script extender installed successfully to:\n{game_root}\n\n"
                    f"{len(installed_files)} files installed.\n\n"
                    f"Data folder has also been restored. You will need to re-run Build Data Folder."
                )

            finally:
                # Clean up temp directory
                shutil.rmtree(temp_dir, ignore_errors=True)

        except zipfile.BadZipFile:
            QMessageBox.warning(self, "Error", "The selected file is not a valid zip archive.")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to install script extender:\n{str(e)}")

    def get_se_manifest_path(self, game_data):
        """Get the path to the script extender install manifest for a game."""
        if not game_data:
            return None
        game_name = game_data.get("name", "").replace(" ", "_").lower()
        if not game_name:
            return None
        config_dir = os.path.join(os.path.expanduser("~"), ".config", "mo2manager")
        return os.path.join(config_dir, f"se_installed_{game_name}.json")

    def uninstall_script_extender(self):
        """Remove previously installed script extender files using the saved manifest."""
        game_data = self.game_combo.currentData()
        if not game_data:
            QMessageBox.warning(self, "Error", "No game selected.")
            return

        manifest_path = self.get_se_manifest_path(game_data)
        if not manifest_path or not os.path.isfile(manifest_path):
            QMessageBox.warning(self, "Error", "No script extender installation found for this game.")
            return

        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            QMessageBox.warning(self, "Error", f"Failed to read install manifest:\n{str(e)}")
            return

        files = manifest.get("files", [])
        if not files:
            QMessageBox.warning(self, "Error", "Install manifest contains no files.")
            os.remove(manifest_path)
            self.update_build_button()
            return

        # Check if restore data folder should run first
        data_path = self.data_output_edit.text() if hasattr(self, 'data_output_edit') else ""
        datafolder_exists = bool(
            self.mods_folder and
            os.path.isdir(os.path.join(self.mods_folder, "DataFolder"))
        )
        can_restore = bool(
            self.mods_folder and
            self.profiles_folder and
            self.selected_profile and
            os.path.isfile(os.path.join(self.profiles_folder, self.selected_profile, "modlist.txt")) and
            data_path and
            datafolder_exists
        )

        msg = (f"This will remove {len(files)} files installed for "
               f"{game_data.get('name', 'this game')}.")
        if can_restore:
            msg += "\n\nThe Data folder will be restored first before removing script extender files."
        msg += "\n\nAre you sure?"

        reply = QMessageBox.question(
            self,
            "Uninstall Script Extender",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Restore data folder first if available (silently, no extra dialogs)
        if can_restore:
            data_path = self.data_output_edit.text()
            datafolder_source = os.path.join(self.mods_folder, "DataFolder")
            modlist_path = os.path.join(self.profiles_folder, self.selected_profile, "modlist.txt")
            self._restore_datafolder_internal(data_path, datafolder_source, modlist_path)

        removed = 0
        missing = 0
        for filepath in files:
            if os.path.isfile(filepath):
                try:
                    os.remove(filepath)
                    removed += 1
                except OSError:
                    pass
            else:
                missing += 1

        # Clean up empty directories left behind
        data_path = game_data.get("data_path", "")
        game_root = os.path.dirname(data_path) if data_path else ""
        if game_root:
            for filepath in sorted(files, reverse=True):
                dirpath = os.path.dirname(filepath)
                while dirpath and dirpath != game_root and os.path.isdir(dirpath):
                    try:
                        os.rmdir(dirpath)  # Only removes empty dirs
                    except OSError:
                        break
                    dirpath = os.path.dirname(dirpath)

        # Restore launcher .bak if it exists
        launcher_restored = False
        launcher_name = game_data.get("launcher_name", "")
        if launcher_name and game_root:
            launcher_path = os.path.join(game_root, launcher_name)
            backup_path = os.path.join(game_root, launcher_name.replace(".exe", ".bak"))
            if os.path.exists(backup_path):
                if os.path.exists(launcher_path):
                    os.remove(launcher_path)
                os.rename(backup_path, launcher_path)
                self.append_log(f"Restored launcher: {launcher_name.replace('.exe', '.bak')} -> {launcher_name}")
                launcher_restored = True

        # Remove the manifest
        os.remove(manifest_path)
        self.update_build_button()

        self.append_log(f"Script extender uninstalled: {removed} files removed, {missing} already missing")
        detail = f"{removed} files removed."
        if missing:
            detail += f"\n{missing} files were already missing."
        if launcher_restored:
            detail += f"\n\nOriginal launcher restored."
        if can_restore:
            detail += f"\n\nData folder has been restored. You will need to re-run Build Data Folder."
        QMessageBox.information(self, "Uninstall Complete",
                                f"Script extender uninstalled.\n\n{detail}")

    def _update_game_data_path(self, game_name, game_folder):
        """Update data_path in config to reflect where the game was actually found."""
        new_data_path = os.path.join(game_folder, "Data")
        for game in self.game_paths:
            if game.get("name") == game_name:
                game["data_path"] = new_data_path
                break
        save_game_paths(self.game_paths)
        self.append_log(f"Updated data_path for {game_name}: {new_data_path}")

        # Update the game combo's stored data and rebuild it to reflect changes
        self._refresh_game_combo()

    def _update_game_plugins_path(self, game_name, new_plugins_path):
        """Update plugins_path in config to reflect a custom wine prefix."""
        for game in self.game_paths:
            if game.get("name") == game_name:
                game["plugins_path"] = new_plugins_path
                break
        save_game_paths(self.game_paths)
        self.append_log(f"Updated plugins_path for {game_name}: {new_plugins_path}")
        self._refresh_game_combo()

    def _refresh_game_combo(self):
        """Rebuild the game combo box from self.game_paths and update output fields."""
        current_name = self.game_combo.currentText()
        self.game_combo.blockSignals(True)
        self.game_combo.clear()
        for game in self.game_paths:
            data_path = game.get("data_path", "")
            if data_path:
                game_folder = os.path.dirname(data_path)
                if os.path.isdir(game_folder):
                    self.game_combo.addItem(game["name"], game)
        self.game_combo.addItem("Custom...", None)
        # Restore previous selection
        for i in range(self.game_combo.count()):
            if self.game_combo.itemText(i) == current_name:
                self.game_combo.setCurrentIndex(i)
                break
        self.game_combo.blockSignals(False)
        # Update output fields to match current selection
        game_data = self.game_combo.currentData()
        if game_data:
            self.data_output_edit.setText(game_data.get("data_path", ""))
            self.plugins_output_edit.setText(game_data.get("plugins_path", ""))

    def _start_mo2_download(self, folder, selected_game_data):
        """Start the MO2 download/install worker for a given folder and game."""
        self.log_text.clear()
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.add_instance_btn.setEnabled(False)

        self.download_worker = DownloadWorker(folder, selected_game_data)
        self.download_worker.output_signal.connect(self.append_log)
        self.download_worker.progress_signal.connect(self.progress_bar.setValue)
        self.download_worker.finished_signal.connect(self.download_finished)
        self.download_worker.start()

    def add_mo2_instance(self):
        """Download and install a new Mod Organizer 2 instance."""
        if not self.game_paths:
            QMessageBox.warning(self, "Error", "No games configured in game_paths.json")
            return

        # Scan for installed games by launcher_name across all locations
        self.append_log("Scanning for installed games...")
        installed_games = find_game_installs(self.game_paths)

        # Build list of available games with their detected folders
        available_games = []
        game_folder_map = {}  # game name -> detected game folder
        for game in self.game_paths:
            game_name = game.get("name", "")
            if game_name in installed_games:
                available_games.append(game)
                game_folder_map[game_name] = installed_games[game_name]

        game_names = [game["name"] for game in available_games]

        # Build a custom dialog with game dropdown + Custom Location button
        dialog = QDialog(self)
        dialog.setWindowTitle("Select Game")
        layout = QVBoxLayout(dialog)

        layout.addWidget(QLabel("Select the game for this MO2 instance:"))

        combo = QComboBox()
        for name in game_names:
            combo.addItem(name)
        layout.addWidget(combo)

        btn_layout = QHBoxLayout()
        custom_btn = QPushButton("Custom Location...")
        custom_btn.setToolTip("Browse to a game install folder not listed above")
        btn_layout.addWidget(custom_btn)
        btn_layout.addStretch()
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_layout.addWidget(button_box)
        layout.addLayout(btn_layout)

        # Disable OK if no games were detected
        ok_btn = button_box.button(QDialogButtonBox.StandardButton.Ok)
        if not game_names:
            ok_btn.setEnabled(False)
            combo.setVisible(False)
            layout.insertWidget(0, QLabel("No installed games were auto-detected.\nUse Custom Location to browse to your game folder."))

        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)

        # Track whether user clicked Custom Location
        custom_result = {}

        def on_custom_clicked():
            folder = QFileDialog.getExistingDirectory(
                dialog,
                "Select Game Install Folder",
                os.path.expanduser("~"),
                QFileDialog.Option.ShowDirsOnly
            )
            if not folder:
                return

            self.append_log(f"Scanning {folder} for game launchers...")
            found = _scan_for_launchers(self.game_paths, [folder])

            if not found:
                QMessageBox.warning(
                    dialog,
                    "No Game Detected",
                    f"No supported game launcher was found in:\n\n{folder}\n\n"
                    "Make sure you selected the game's install folder\n"
                    "(the folder containing the game's launcher .exe)."
                )
                return

            if len(found) == 1:
                name, gfolder = next(iter(found.items()))
            else:
                names = list(found.keys())
                name, ok = QInputDialog.getItem(
                    dialog, "Multiple Games Detected",
                    "Multiple games were found. Select one:",
                    names, 0, False
                )
                if not ok or not name:
                    return
                gfolder = found[name]

            # Ask about wine prefix
            prefix_reply = QMessageBox.question(
                dialog,
                "Wine Prefix",
                f"Game detected: {name}\n\n"
                "Would you like to use a custom wine prefix?\n\n"
                "Select 'Yes' to browse to a custom prefix folder,\n"
                "or 'No' to use the default Steam prefix.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            custom_plugins_path = None
            if prefix_reply == QMessageBox.StandardButton.Yes:
                prefix_folder = QFileDialog.getExistingDirectory(
                    dialog,
                    "Select Wine Prefix Folder (the folder containing pfx/)",
                    os.path.expanduser("~"),
                    QFileDialog.Option.ShowDirsOnly
                )
                if not prefix_folder:
                    return

                # Verify the selected folder has a pfx subdirectory
                pfx_path = os.path.join(prefix_folder, "pfx")
                if not os.path.isdir(pfx_path):
                    QMessageBox.warning(
                        dialog,
                        "Invalid Prefix",
                        f"The selected folder does not contain a 'pfx' subdirectory:\n\n"
                        f"{prefix_folder}\n\n"
                        "Please select the folder that contains the 'pfx' folder."
                    )
                    return

                # Build new plugins_path using the suffix from the default config
                game_cfg = None
                for g in self.game_paths:
                    if g.get("name") == name:
                        game_cfg = g
                        break
                if game_cfg:
                    default_pp = game_cfg.get("plugins_path", "")
                    pfx_index = default_pp.find("/pfx/")
                    if pfx_index != -1:
                        suffix = default_pp[pfx_index:]  # e.g. /pfx/drive_c/users/steamuser/AppData/Local/...
                        custom_plugins_path = prefix_folder + suffix

            custom_result["game_name"] = name
            custom_result["game_folder"] = gfolder
            custom_result["plugins_path"] = custom_plugins_path
            dialog.accept()

        custom_btn.clicked.connect(on_custom_clicked)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        # Determine game name and folder from either the dropdown or custom path
        if custom_result:
            selected_game = custom_result["game_name"]
            game_folder = custom_result["game_folder"]
        else:
            selected_game = combo.currentText()
            game_folder = game_folder_map[selected_game]

        # Find the selected game data
        selected_game_data = None
        for game in self.game_paths:
            if game["name"] == selected_game:
                selected_game_data = game
                break

        # Update data_path in config to match detected location
        self._update_game_data_path(selected_game, game_folder)

        # Update plugins_path if a custom wine prefix was selected
        if custom_result and custom_result.get("plugins_path"):
            self._update_game_plugins_path(selected_game, custom_result["plugins_path"])

        # Create subfolder named "<game name> MO2"
        folder = os.path.join(game_folder, f"{selected_game} MO2")

        # Check if folder already exists
        if os.path.exists(folder):
            QMessageBox.warning(
                self,
                "Folder Exists",
                f"The folder already exists:\n\n{folder}\n\n"
                "You will need remove/backup the existing folder in the game directory first."
            )
            return

        # Confirm installation
        msg = f"This will download and install Mod Organizer 2 to:\n\n"
        msg += f"{folder}\n\n"
        msg += f"Game: {selected_game}\n"
        msg += "Download size: ~50 MB\n\n"
        msg += "Continue?"

        reply = QMessageBox.question(
            self,
            "Install Mod Organizer 2",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        self._start_mo2_download(folder, selected_game_data)

    def open_instance_folder(self):
        """Open the selected MO2 instance's game folder in the file manager."""
        if self.mo2_path and os.path.isdir(self.mo2_path):
            game_folder = os.path.dirname(self.mo2_path)
            subprocess.Popen(["xdg-open", game_folder], env=get_clean_env())

    def download_finished(self, success, result):
        """Handle download completion."""
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 0)  # Reset to indeterminate
        self.add_instance_btn.setEnabled(True)

        if success:
            QMessageBox.information(
                self,
                "Installation Complete",
                f"Mod Organizer 2 installed successfully!\n\n"
                f"Location: {result}\n\n"
                f"Click 'Rescan' to detect the new instance."
            )
            # Automatically rescan for instances
            self.rescan_mo2_instances()
        else:
            QMessageBox.critical(
                self,
                "Installation Failed",
                f"Failed to install Mod Organizer 2:\n\n{result}"
            )

    def on_mo2_path_changed(self, path):
        self.mo2_path = path
        # Update path label when manually entering a path
        if hasattr(self, 'mo2_path_label'):
            if path:
                self.mo2_path_label.setText(f"Path: {path}")
            else:
                self.mo2_path_label.setText("Path: Enter path manually")
        self.validate_mo2_folder()

    def validate_mo2_folder(self):
        # Check if UI is fully initialized
        if not hasattr(self, 'profile_combo'):
            return

        path = self.mo2_path

        # Reset status
        self.mods_folder = ""
        self.overwrite_folder = ""
        self.profiles_folder = ""

        if not path or not os.path.isdir(path):
            self.mods_status_label.setText("Mods folder: Not found")
            self.mods_status_label.setStyleSheet("color: red;")
            self.overwrite_status_label.setText("Overwrite folder: Not found")
            self.overwrite_status_label.setStyleSheet("color: red;")
            self.profile_combo.clear()
            self.profile_combo.setEnabled(False)
            self.update_build_button()
            return

        # Auto-detect game from MO2 folder name (e.g., "Skyrim Special Edition MO2")
        self.auto_detect_game(None)

        # Check for mods folder
        mods_path = os.path.join(path, "mods")
        if os.path.isdir(mods_path):
            self.mods_folder = mods_path
            mod_count = len([d for d in os.listdir(mods_path) if os.path.isdir(os.path.join(mods_path, d))])
            self.mods_status_label.setText(f"Mods folder: Found ({mod_count} mods)")
            self.mods_status_label.setStyleSheet("color: green;")
        else:
            self.mods_status_label.setText("Mods folder: Not found")
            self.mods_status_label.setStyleSheet("color: red;")

        # Check for overwrite folder
        overwrite_path = os.path.join(path, "overwrite")
        if os.path.isdir(overwrite_path):
            self.overwrite_folder = overwrite_path
            self.overwrite_status_label.setText("Overwrite folder: Found")
            self.overwrite_status_label.setStyleSheet("color: green;")
        else:
            self.overwrite_status_label.setText("Overwrite folder: Not found (optional)")
            self.overwrite_status_label.setStyleSheet("color: orange;")

        # Check for profiles folder and populate dropdown
        profiles_path = os.path.join(path, "profiles")
        if os.path.isdir(profiles_path):
            self.profiles_folder = profiles_path
            profiles = [d for d in os.listdir(profiles_path)
                       if os.path.isdir(os.path.join(profiles_path, d))]

            self.profile_combo.clear()
            self.profile_combo.setEnabled(True)

            if len(profiles) == 0:
                self.profile_combo.addItem("No profiles found")
                self.profile_combo.setEnabled(False)
            elif len(profiles) == 1:
                self.profile_combo.addItem(profiles[0])
                self.selected_profile = profiles[0]
            else:
                self.profile_combo.addItems(sorted(profiles))
                self.selected_profile = sorted(profiles)[0]

            self.validate_profile()
        else:
            self.profile_combo.clear()
            self.profile_combo.addItem("Profiles folder not found")
            self.profile_combo.setEnabled(False)
            self.modlist_status_label.setText("modlist.txt: Not found")
            self.modlist_status_label.setStyleSheet("color: red;")
            self.plugins_status_label.setText("plugins.txt: Not found")
            self.plugins_status_label.setStyleSheet("color: red;")

        self.update_build_button()

    def on_profile_changed(self, profile_name):
        self.selected_profile = profile_name
        self.validate_profile()
        self.update_build_button()

    def validate_profile(self):
        if not self.profiles_folder or not self.selected_profile:
            return

        profile_path = os.path.join(self.profiles_folder, self.selected_profile)

        # Check for modlist.txt
        modlist_path = os.path.join(profile_path, "modlist.txt")
        if os.path.isfile(modlist_path):
            self.modlist_status_label.setText(f"modlist.txt: Found")
            self.modlist_status_label.setStyleSheet("color: green;")
            # Update the modlist panel with the new modlist path
            self.modlist_panel.set_modlist_path(modlist_path)
        else:
            self.modlist_status_label.setText("modlist.txt: Not found")
            self.modlist_status_label.setStyleSheet("color: red;")
            # Clear the modlist panel
            self.modlist_panel.set_modlist_path(None)

        # Check for plugins.txt
        plugins_path = os.path.join(profile_path, "plugins.txt")
        if os.path.isfile(plugins_path):
            self.plugins_status_label.setText(f"plugins.txt: Found")
            self.plugins_status_label.setStyleSheet("color: green;")
            # Update the plugins panel with the new plugins path
            self.plugins_panel.set_plugins_path(plugins_path)
        else:
            self.plugins_status_label.setText("plugins.txt: Not found")
            self.plugins_status_label.setStyleSheet("color: red;")
            # Clear the plugins panel
            self.plugins_panel.set_plugins_path(None)

    def auto_detect_game(self, profile_path):
        """
        Auto-detect the game based on the MO2 instance folder name.
        Instance folders follow the format "<game name> MO2" (e.g., "Skyrim Special Edition MO2").
        """
        if not self.mo2_path:
            return

        folder_name = os.path.basename(self.mo2_path)

        # Match against game names - folder should be "<game name> MO2"
        for game in self.game_paths:
            game_name = game.get("name", "")
            if not game_name:
                continue
            expected_folder = f"{game_name} MO2"
            if folder_name.lower() == expected_folder.lower():
                # Found a match - select it in the combo box
                for i in range(self.game_combo.count()):
                    if self.game_combo.itemText(i) == game_name:
                        self.game_combo.blockSignals(True)
                        self.game_combo.setCurrentIndex(i)
                        self.game_combo.blockSignals(False)
                        # Update the output paths
                        self.data_output_edit.setText(game.get("data_path", ""))
                        self.plugins_output_edit.setText(game.get("plugins_path", ""))
                        # Update downgrade button visibility
                        self.downgrade_btn.setVisible(game_name == "Fallout 3")
                        self.update_build_button()
                        return
                return

    def browse_data_output(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Output Location for Data Folder",
            os.path.expanduser("~")
        )
        if folder:
            self.data_output_edit.setText(folder)
            # Switch to custom if user browses and path doesn't match current game
            game_data = self.game_combo.currentData()
            if game_data and folder != game_data.get("data_path", ""):
                custom_index = self.game_combo.count() - 1
                self.game_combo.blockSignals(True)
                self.game_combo.setCurrentIndex(custom_index)
                self.game_combo.blockSignals(False)
            self.update_build_button()

    def on_game_changed(self, index):
        """Handle game selection change - updates both Data and plugins.txt paths."""
        game_data = self.game_combo.currentData()
        if game_data is None:  # Custom option
            self.data_output_edit.clear()
            self.plugins_output_edit.clear()
        else:
            self.data_output_edit.setText(game_data.get("data_path", ""))
            self.plugins_output_edit.setText(game_data.get("plugins_path", ""))

        # Show Downgrade button only for Fallout 3
        is_fallout3 = game_data is not None and game_data.get("name") == "Fallout 3"
        self.downgrade_btn.setVisible(is_fallout3)

        self.update_build_button()

    def run_winecfg(self):
        """Launch winecfg for the selected game's Wine prefix using its Proton version."""
        game_data = self.game_combo.currentData()
        if game_data is None:
            QMessageBox.warning(self, "Error", "No game selected. Please select a game first.")
            return

        plugins_path = game_data.get("plugins_path", "")
        if not plugins_path:
            QMessageBox.warning(self, "Error", "No plugins path configured for this game.")
            return

        # Extract compatdata path from plugins_path
        # e.g. .../compatdata/489830/pfx/drive_c/... -> .../compatdata/489830
        pfx_index = plugins_path.find("/pfx/")
        if pfx_index == -1:
            QMessageBox.warning(self, "Error", "Could not determine Wine prefix from plugins path.")
            return

        compat_data_path = plugins_path[:pfx_index]

        if not os.path.isdir(compat_data_path):
            QMessageBox.warning(self, "Error", f"Compatdata folder not found:\n{compat_data_path}")
            return

        # Detect which Proton version was used by reading config_info
        config_info_path = os.path.join(compat_data_path, "config_info")
        proton_path = None

        if os.path.isfile(config_info_path):
            try:
                with open(config_info_path, 'r') as f:
                    lines = f.readlines()
                if len(lines) >= 2:
                    # Line 2 contains a path like .../common/Proton 9.0 (Beta)/files/share/fonts/
                    # Extract the Proton install dir (everything up to and including the dir before /files/)
                    font_path = lines[1].strip()
                    files_index = font_path.find("/files/")
                    if files_index != -1:
                        proton_dir = font_path[:files_index]
                        candidate = os.path.join(proton_dir, "proton")
                        if os.path.isfile(candidate):
                            proton_path = candidate
            except Exception:
                pass

        if not proton_path:
            QMessageBox.warning(
                self, "Error",
                f"Could not detect Proton version for {game_data['name']}.\n\n"
                f"The config_info file was not found or could not be parsed at:\n"
                f"{config_info_path}\n\n"
                "Make sure the game has been launched at least once via Steam."
            )
            return

        # Set up environment for Proton
        env = get_clean_env()
        env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = os.path.expanduser("~/.local/share/Steam")
        env["STEAM_COMPAT_DATA_PATH"] = compat_data_path

        proton_name = os.path.basename(os.path.dirname(proton_path))

        try:
            subprocess.Popen([proton_path, "run", "winecfg"], env=env, cwd=compat_data_path)
            self.append_log(f"Launched winecfg for {game_data['name']} via {proton_name}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to launch winecfg:\n{str(e)}")

    def run_winetricks(self):
        """Launch protontricks GUI for the selected game."""
        game_data = self.game_combo.currentData()
        if game_data is None:
            QMessageBox.warning(self, "Error", "No game selected. Please select a game first.")
            return

        plugins_path = game_data.get("plugins_path", "")
        if not plugins_path:
            QMessageBox.warning(self, "Error", "No plugins path configured for this game.")
            return

        # Extract app ID from compatdata path
        # e.g. .../compatdata/489830/pfx/drive_c/... -> 489830
        pfx_index = plugins_path.find("/pfx/")
        if pfx_index == -1:
            QMessageBox.warning(self, "Error", "Could not determine Wine prefix from plugins path.")
            return

        compat_data_path = plugins_path[:pfx_index]
        app_id = os.path.basename(compat_data_path)

        # Find protontricks (native or flatpak)
        protontricks_cmd = None
        if shutil.which("protontricks"):
            protontricks_cmd = ["protontricks"]
        elif shutil.which("flatpak"):
            # Check if protontricks flatpak is installed
            try:
                result = subprocess.run(
                    ["flatpak", "list", "--columns=application"],
                    capture_output=True, text=True, timeout=5
                )
                if "com.github.Matoking.protontricks" in result.stdout:
                    protontricks_cmd = ["flatpak", "run", "com.github.Matoking.protontricks"]
            except Exception:
                pass

        if not protontricks_cmd:
            QMessageBox.warning(
                self, "Error",
                "protontricks not found.\n\n"
                "Install it using one of these methods:\n"
                "  flatpak install com.github.Matoking.protontricks\n"
                "  pip install protontricks\n"
                "  sudo pacman -S protontricks"
            )
            return

        env = get_clean_env()
        # Suppress "Failed to load module canberra-gtk-module" warning
        gtk_modules = env.get("GTK_MODULES", "")
        if gtk_modules:
            env["GTK_MODULES"] = ":".join(
                m for m in gtk_modules.split(":") if "canberra" not in m
            ) or ""
        env.pop("GTK3_MODULES", None)

        try:
            subprocess.Popen(protontricks_cmd + [app_id, "--gui"], env=env)
            self.append_log(f"Launched protontricks for {game_data['name']} (App ID: {app_id})")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to launch protontricks:\n{str(e)}")

    def change_game_prefix(self):
        """Let the user select a different wine prefix for the currently selected game."""
        game_data = self.game_combo.currentData()
        if game_data is None:
            QMessageBox.warning(self, "Error", "No game selected. Please select a game first.")
            return

        game_name = game_data.get("name", "")
        current_pp = game_data.get("plugins_path", "")
        pfx_index = current_pp.find("/pfx/")
        if pfx_index == -1:
            QMessageBox.warning(self, "Error", "Could not determine prefix suffix from current plugins path.")
            return
        suffix = current_pp[pfx_index:]  # e.g. /pfx/drive_c/users/steamuser/AppData/Local/...

        prefix_folder = QFileDialog.getExistingDirectory(
            self,
            f"Select Wine Prefix Folder for {game_name} (the folder containing pfx/)",
            os.path.expanduser("~"),
            QFileDialog.Option.ShowDirsOnly
        )
        if not prefix_folder:
            return

        pfx_path = os.path.join(prefix_folder, "pfx")
        if not os.path.isdir(pfx_path):
            QMessageBox.warning(
                self,
                "Invalid Prefix",
                f"The selected folder does not contain a 'pfx' subdirectory:\n\n"
                f"{prefix_folder}\n\n"
                "Please select the folder that contains the 'pfx' folder."
            )
            return

        new_plugins_path = prefix_folder + suffix
        self._update_game_plugins_path(game_name, new_plugins_path)

    def run_exe_in_game_prefix(self):
        """Run an executable in the selected game's Wine prefix using its Proton version."""
        game_data = self.game_combo.currentData()
        if game_data is None:
            QMessageBox.warning(self, "Error", "No game selected. Please select a game first.")
            return

        plugins_path = game_data.get("plugins_path", "")
        if not plugins_path:
            QMessageBox.warning(self, "Error", "No plugins path configured for this game.")
            return

        # Extract compatdata path from plugins_path
        pfx_index = plugins_path.find("/pfx/")
        if pfx_index == -1:
            QMessageBox.warning(self, "Error", "Could not determine Wine prefix from plugins path.")
            return

        compat_data_path = plugins_path[:pfx_index]

        if not os.path.isdir(compat_data_path):
            QMessageBox.warning(self, "Error", f"Compatdata folder not found:\n{compat_data_path}")
            return

        # Detect which Proton version was used by reading config_info
        config_info_path = os.path.join(compat_data_path, "config_info")
        proton_path = None

        if os.path.isfile(config_info_path):
            try:
                with open(config_info_path, 'r') as f:
                    lines = f.readlines()
                if len(lines) >= 2:
                    font_path = lines[1].strip()
                    files_index = font_path.find("/files/")
                    if files_index != -1:
                        proton_dir = font_path[:files_index]
                        candidate = os.path.join(proton_dir, "proton")
                        if os.path.isfile(candidate):
                            proton_path = candidate
            except Exception:
                pass

        if not proton_path:
            QMessageBox.warning(
                self, "Error",
                f"Could not detect Proton version for {game_data['name']}.\n\n"
                f"The config_info file was not found or could not be parsed at:\n"
                f"{config_info_path}\n\n"
                "Make sure the game has been launched at least once via Steam."
            )
            return

        # Ask user to select an executable
        exe_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Executable to Run",
            os.path.expanduser("~"),
            "Executables (*.exe *.msi);;All Files (*)"
        )

        if not exe_path:
            return

        # Set up environment for Proton
        env = get_clean_env()
        env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = os.path.expanduser("~/.local/share/Steam")
        env["STEAM_COMPAT_DATA_PATH"] = compat_data_path

        proton_name = os.path.basename(os.path.dirname(proton_path))
        exe_name = os.path.basename(exe_path)

        try:
            self.append_log(f"Launching {exe_name} via {proton_name} in {game_data['name']} prefix...")
            subprocess.Popen(
                [proton_path, "run", exe_path],
                env=env,
                cwd=os.path.dirname(exe_path)
            )
            self.append_log(f"Using prefix: {compat_data_path}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to launch executable:\n{str(e)}")

    def run_downgrade(self):
        """Downgrade Fallout 3 using the Updated Unofficial Fallout 3 Patch patcher."""
        game_data = self.game_combo.currentData()
        if game_data is None or game_data.get("name") != "Fallout 3":
            return

        data_path = game_data.get("data_path", "")
        if not data_path:
            QMessageBox.warning(self, "Error", "No data path configured for Fallout 3.")
            return

        game_dir = os.path.dirname(data_path)
        patcher_exe = os.path.join(game_dir, "Patcher.exe")

        # If Patcher.exe doesn't exist, ask user to provide the zip
        if not os.path.isfile(patcher_exe):
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setWindowTitle("Downgrade Patcher Not Found")
            msg.setText(
                "Patcher.exe was not found in the Fallout 3 directory.\n\n"
                "You need to download the Updated Unofficial Fallout 3 Patch patcher from Nexus Mods, "
                "then select the downloaded zip file."
            )
            msg.addButton("Open Download Page", QMessageBox.ButtonRole.ActionRole)
            select_btn = msg.addButton("Select Zip File", QMessageBox.ButtonRole.AcceptRole)
            msg.addButton(QMessageBox.StandardButton.Cancel)
            msg.exec()

            clicked = msg.clickedButton()
            if clicked is None or clicked.text() == "Cancel":
                return

            if clicked.text() == "Open Download Page":
                subprocess.Popen(["xdg-open", "https://www.nexusmods.com/fallout3/mods/24913"], env=get_clean_env())
                # After opening the page, ask again to select the zip
                zip_path, _ = QFileDialog.getOpenFileName(
                    self,
                    "Select Downloaded Patcher Zip File",
                    os.path.expanduser("~/Downloads"),
                    "Archives (*.zip *.7z);;All Files (*)"
                )
            else:
                zip_path, _ = QFileDialog.getOpenFileName(
                    self,
                    "Select Downloaded Patcher Zip File",
                    os.path.expanduser("~/Downloads"),
                    "Archives (*.zip *.7z);;All Files (*)"
                )

            if not zip_path:
                return

            # Extract archive to game directory
            try:
                if zip_path.lower().endswith(".7z"):
                    import py7zr
                    with py7zr.SevenZipFile(zip_path, 'r') as sz:
                        names = [n.lower() for n in sz.getnames()]
                        if not any(n.endswith("patcher.exe") for n in names):
                            QMessageBox.warning(
                                self, "Error",
                                "The selected archive does not contain Patcher.exe.\n\n"
                                "Download the correct file from:\n"
                                "https://www.nexusmods.com/fallout3/mods/24913"
                            )
                            return
                        sz.extractall(game_dir)
                else:
                    with zipfile.ZipFile(zip_path, 'r') as zf:
                        names = [n.lower() for n in zf.namelist()]
                        if not any(n.endswith("patcher.exe") for n in names):
                            QMessageBox.warning(
                                self, "Error",
                                "The selected archive does not contain Patcher.exe.\n\n"
                                "Download the correct file from:\n"
                                "https://www.nexusmods.com/fallout3/mods/24913"
                            )
                            return
                        zf.extractall(game_dir)
                self.append_log(f"Extracted patcher files to {game_dir}")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to extract archive:\n{str(e)}")
                return

            # Re-check for Patcher.exe after extraction
            if not os.path.isfile(patcher_exe):
                QMessageBox.warning(self, "Error", "Patcher.exe still not found after extraction.")
                return

        # Detect Proton version from config_info
        plugins_path = game_data.get("plugins_path", "")
        pfx_index = plugins_path.find("/pfx/")
        if pfx_index == -1:
            QMessageBox.warning(self, "Error", "Could not determine Wine prefix from plugins path.")
            return

        compat_data_path = plugins_path[:pfx_index]
        config_info_path = os.path.join(compat_data_path, "config_info")
        proton_path = None

        if os.path.isfile(config_info_path):
            try:
                with open(config_info_path, 'r') as f:
                    lines = f.readlines()
                if len(lines) >= 2:
                    font_path = lines[1].strip()
                    files_index = font_path.find("/files/")
                    if files_index != -1:
                        proton_dir = font_path[:files_index]
                        candidate = os.path.join(proton_dir, "proton")
                        if os.path.isfile(candidate):
                            proton_path = candidate
            except Exception:
                pass

        if not proton_path:
            QMessageBox.warning(
                self, "Error",
                "Could not detect Proton version for Fallout 3.\n\n"
                "Make sure the game has been launched at least once via Steam."
            )
            return

        # Run Patcher.exe via Proton
        env = get_clean_env()
        env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = os.path.expanduser("~/.local/share/Steam")
        env["STEAM_COMPAT_DATA_PATH"] = compat_data_path

        proton_name = os.path.basename(os.path.dirname(proton_path))

        try:
            self.append_log(f"Running Fallout 3 downgrade patcher via {proton_name}...")
            subprocess.Popen(
                [proton_path, "run", patcher_exe],
                env=env,
                cwd=game_dir
            )
            self.append_log(f"Using prefix: {compat_data_path}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to launch patcher:\n{str(e)}")

    def browse_plugins_output(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Location for plugins.txt",
            os.path.expanduser("~")
        )
        if folder:
            self.plugins_output_edit.setText(folder)
            # Switch to custom if user browses and path doesn't match current game
            game_data = self.game_combo.currentData()
            if game_data and folder != game_data.get("plugins_path", ""):
                custom_index = self.game_combo.count() - 1
                self.game_combo.blockSignals(True)
                self.game_combo.setCurrentIndex(custom_index)
                self.game_combo.blockSignals(False)

    def update_build_button(self):
        # Update Script Extender buttons (created early, so always safe to check)
        if hasattr(self, 'se_download_btn'):
            game_data = self.game_combo.currentData() if hasattr(self, 'game_combo') else None
            has_se_download = bool(game_data and game_data.get("script_extender_download"))
            self.se_download_btn.setEnabled(has_se_download)
            has_se_name = bool(game_data and game_data.get("script_extender_name"))
            self.se_install_btn.setEnabled(has_se_name)
            has_manifest = bool(game_data and self.get_se_manifest_path(game_data) and
                                os.path.isfile(self.get_se_manifest_path(game_data)))
            self.se_uninstall_btn.setEnabled(has_manifest)

            # Update script extender status label
            if hasattr(self, 'se_status_label'):
                se_name = game_data.get("script_extender_name", "") if game_data else ""
                if se_name:
                    data_path = game_data.get("data_path", "")
                    game_folder = os.path.dirname(data_path) if data_path else ""
                    se_path = os.path.join(game_folder, se_name) if game_folder else ""
                    if se_path and os.path.isfile(se_path):
                        self.se_status_label.setText(f"Script Extender: {se_name} found")
                        self.se_status_label.setStyleSheet("color: green;")
                    else:
                        self.se_status_label.setText(f"Script Extender: {se_name} not found")
                        self.se_status_label.setStyleSheet("color: orange;")
                else:
                    self.se_status_label.setText("")

        # Check if build_btn exists (might be called during init)
        if not hasattr(self, 'build_btn'):
            return

        # Check if DataFolder mod exists in mods folder
        datafolder_exists = bool(
            self.mods_folder and
            os.path.isdir(os.path.join(self.mods_folder, "DataFolder"))
        )

        # Check if all required paths are valid for build
        # If DataFolder doesn't exist, it will be created automatically during build
        data_path = self.data_output_edit.text()
        can_build = bool(
            self.mods_folder and
            self.profiles_folder and
            self.selected_profile and
            os.path.isfile(os.path.join(self.profiles_folder, self.selected_profile, "modlist.txt")) and
            data_path and
            (datafolder_exists or (os.path.isdir(data_path) and os.listdir(data_path)))  # DataFolder exists OR Data folder has contents to create it
        )
        self.build_btn.setEnabled(can_build)

        # Check if DataFolder can be restored
        # Requires: DataFolder mod exists, Data folder path specified, modlist.txt exists
        can_restore_datafolder = bool(
            self.mods_folder and
            self.profiles_folder and
            self.selected_profile and
            os.path.isfile(os.path.join(self.profiles_folder, self.selected_profile, "modlist.txt")) and
            data_path and
            datafolder_exists  # DataFolder must exist to restore
        )
        self.restore_datafolder_btn.setEnabled(can_restore_datafolder)

        # Check if Run MO2 button can be enabled
        # Requires: MO2 path valid, ModOrganizer.exe exists, game selected
        can_run_mo2 = bool(
            self.mo2_path and
            os.path.isfile(os.path.join(self.mo2_path, "ModOrganizer.exe")) and
            self.game_combo.currentData()  # Game selected
        )
        self.run_mo2_btn.setEnabled(can_run_mo2)

        # Open Folder: just needs a valid MO2 path
        if hasattr(self, 'open_instance_btn'):
            self.open_instance_btn.setEnabled(bool(self.mo2_path and os.path.isdir(self.mo2_path)))

    def start_build(self):
        # Get paths
        modlist_path = os.path.join(self.profiles_folder, self.selected_profile, "modlist.txt")
        data_output = self.data_output_edit.text()
        plugins_dest = self.plugins_output_edit.text()
        datafolder_dest = os.path.join(self.mods_folder, "DataFolder")
        needs_datafolder_creation = not os.path.isdir(datafolder_dest)

        # Confirm with user
        msg = f"Ready to build Data folder:\n\n"
        msg += f"Modlist: {modlist_path}\n"
        msg += f"Mods folder: {self.mods_folder}\n"
        msg += f"Overwrite folder: {self.overwrite_folder if self.overwrite_folder else 'None'}\n"
        msg += f"Output: {data_output}\n"
        msg += f"plugins.txt destination: {plugins_dest if plugins_dest else 'None'}\n\n"
        if needs_datafolder_creation:
            msg += "DataFolder mod does not exist and will be created first.\n"
            msg += "This will move Data folder contents to MO2 mods/DataFolder.\n\n"
        msg += "This will delete any existing Data folder at the output location.\n"
        msg += "Continue?"

        reply = QMessageBox.question(
            self,
            "Confirm Build",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Create DataFolder mod first if it doesn't exist
        if needs_datafolder_creation:
            if not self._create_datafolder_mod_internal(data_output, datafolder_dest, modlist_path):
                return

        # Handle existing Data folder deletion
        if os.path.exists(data_output):
            self.log_text.clear()
            self.append_log(f"Deleting existing Data folder: {data_output}")
            try:
                shutil.rmtree(data_output)
                self.append_log("Deleted.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete existing Data folder:\n{str(e)}")
                return

        # Clear log and start build
        self.log_text.clear()
        self.build_btn.setEnabled(False)
        self.progress_bar.setVisible(True)

        # Get current game data for script extender swap
        game_data = self.game_combo.currentData()

        self.worker = BuildWorker(
            modlist=modlist_path,
            mods_folder=self.mods_folder,
            output_dir=data_output,
            overwrite_folder=self.overwrite_folder if self.overwrite_folder else None,
            plugins_dest=plugins_dest if plugins_dest else None,
            game_data=game_data
        )
        self.worker.output_signal.connect(self.append_log)
        self.worker.finished_signal.connect(self.build_finished)
        self.worker.start()

    def append_log(self, text):
        self.log_text.append(text)
        # Auto-scroll to bottom
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def build_finished(self, success, message):
        self.progress_bar.setVisible(False)
        self.update_build_button()  # Re-evaluate button states

        if success:
            QMessageBox.information(self, "Build Complete", message)
        else:
            QMessageBox.warning(self, "Build Failed", message)

    def _create_datafolder_mod_internal(self, data_path, datafolder_dest, modlist_path):
        """
        Create the initial DataFolder mod by moving game Data folder contents
        to MO2 mods folder and adding it to modlist.txt.
        Returns True on success, False on failure.
        """
        self.log_text.clear()
        self.progress_bar.setVisible(True)
        self.build_btn.setEnabled(False)

        try:
            # Create the DataFolder directory
            os.makedirs(datafolder_dest)
            self.append_log(f"Created: {datafolder_dest}")

            # Move all contents from Data folder to DataFolder mod
            self.append_log(f"Moving contents from {data_path}...")
            moved_count = 0

            for item in os.listdir(data_path):
                src = os.path.join(data_path, item)
                dst = os.path.join(datafolder_dest, item)
                shutil.move(src, dst)
                moved_count += 1
                if moved_count % 10 == 0:
                    self.append_log(f"  Moved {moved_count} items...")

            self.append_log(f"Moved {moved_count} items total")

            # Update modlist.txt: remove * entries and add +DataFolder
            self.append_log(f"Updating modlist.txt...")

            # Read existing modlist
            with open(modlist_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            # Remove any lines starting with * (separator lines)
            original_count = len(lines)
            lines = [line for line in lines if not line.strip().startswith('*')]
            removed_count = original_count - len(lines)
            if removed_count > 0:
                self.append_log(f"  Removed {removed_count} separator entries (lines starting with *)")

            # Check if DataFolder is already in the list
            datafolder_entry = "+DataFolder\n"
            has_datafolder = any(line.strip() in ("+DataFolder", "-DataFolder") for line in lines)

            if has_datafolder:
                self.append_log("  DataFolder already in modlist.txt, skipping add...")
            else:
                # Add at the bottom (before any empty lines at the end)
                # Find the last non-empty line
                insert_pos = len(lines)
                for i in range(len(lines) - 1, -1, -1):
                    if lines[i].strip():
                        insert_pos = i + 1
                        break

                lines.insert(insert_pos, datafolder_entry)
                self.append_log(f"  Added '+DataFolder' to modlist.txt")

            # Write updated modlist
            with open(modlist_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)

            self.append_log("")
            self.append_log("=" * 50)
            self.append_log("DataFolder mod created successfully!")
            self.append_log("=" * 50)
            return True

        except Exception as e:
            self.append_log(f"ERROR: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to create DataFolder mod:\n{str(e)}")
            return False

        finally:
            self.progress_bar.setVisible(False)
            self.update_build_button()

    def restore_datafolder(self):
        """
        Restore the Data folder by deleting it and moving contents from
        DataFolder mod back to the game's Data folder location.
        Also removes the DataFolder entry from modlist.txt.
        """
        data_path = self.data_output_edit.text()
        datafolder_source = os.path.join(self.mods_folder, "DataFolder")
        modlist_path = os.path.join(self.profiles_folder, self.selected_profile, "modlist.txt")

        # Count files to restore
        file_count = sum(len(files) for _, _, files in os.walk(datafolder_source))

        # Confirm with user
        msg = f"This will restore the original Data folder:\n\n"
        msg += f"Source: {datafolder_source}\n"
        msg += f"Destination: {data_path}\n"
        msg += f"Files to restore: {file_count}\n\n"
        msg += "This will:\n"
        msg += "1. Delete the existing Data folder (if present)\n"
        msg += "2. Move all contents from mods/DataFolder back to the Data folder\n"
        msg += "3. Delete the empty DataFolder mod directory\n"
        msg += "4. Remove the DataFolder entry from modlist.txt\n\n"
        msg += "Continue?"

        reply = QMessageBox.question(
            self,
            "Restore Data Folder",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        success, moved_count, launcher_restored = self._restore_datafolder_internal(data_path, datafolder_source, modlist_path)

        if success:
            success_msg = f"Data folder restored successfully!\n\n"
            success_msg += f"Moved {moved_count} items to:\n{data_path}\n\n"
            success_msg += f"DataFolder mod removed from mods folder and modlist.txt"
            if launcher_restored:
                success_msg += f"\n\nOriginal launcher restored."

            QMessageBox.information(
                self,
                "Success",
                success_msg
            )

    def _restore_datafolder_internal(self, data_path, datafolder_source, modlist_path):
        """
        Internal method to restore the Data folder without showing confirmation dialogs.
        Returns (success, moved_count, launcher_restored).
        """
        self.log_text.clear()
        self.progress_bar.setVisible(True)
        self.restore_datafolder_btn.setEnabled(False)
        self.build_btn.setEnabled(False)

        try:
            # Delete existing Data folder if it exists
            if os.path.exists(data_path):
                self.append_log(f"Deleting existing Data folder: {data_path}")
                shutil.rmtree(data_path)
                self.append_log("Deleted.")

            # Create the Data folder
            os.makedirs(data_path)
            self.append_log(f"Created: {data_path}")

            # Move all contents from DataFolder mod to Data folder
            self.append_log(f"Moving contents from {datafolder_source}...")
            moved_count = 0

            for item in os.listdir(datafolder_source):
                src = os.path.join(datafolder_source, item)
                dst = os.path.join(data_path, item)
                shutil.move(src, dst)
                moved_count += 1
                if moved_count % 10 == 0:
                    self.append_log(f"  Moved {moved_count} items...")

            self.append_log(f"Moved {moved_count} items total")

            # Remove the now-empty DataFolder directory
            self.append_log(f"Removing empty DataFolder mod directory...")
            os.rmdir(datafolder_source)
            self.append_log("Removed.")

            # Update modlist.txt: remove DataFolder entry
            self.append_log(f"Updating modlist.txt...")

            # Read existing modlist
            with open(modlist_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            # Remove any lines containing DataFolder (+ or -)
            original_count = len(lines)
            lines = [line for line in lines if line.strip() not in ("+DataFolder", "-DataFolder")]
            removed_count = original_count - len(lines)

            if removed_count > 0:
                self.append_log(f"  Removed {removed_count} DataFolder entry/entries from modlist.txt")
            else:
                self.append_log("  No DataFolder entry found in modlist.txt")

            # Write updated modlist
            with open(modlist_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)

            # Restore original launcher from backup
            game_data = self.game_combo.currentData()
            launcher_restored = False
            if game_data:
                launcher_name = game_data.get("launcher_name")
                if launcher_name:
                    game_folder = os.path.dirname(data_path)
                    launcher_path = os.path.join(game_folder, launcher_name)
                    backup_path = os.path.join(game_folder, launcher_name.replace(".exe", ".bak"))

                    if os.path.exists(backup_path):
                        self.append_log("")
                        self.append_log("=" * 50)
                        self.append_log("RESTORING ORIGINAL LAUNCHER")
                        self.append_log("=" * 50)
                        self.append_log(f"Game folder: {game_folder}")

                        # Delete the current launcher (script extender copy)
                        if os.path.exists(launcher_path):
                            self.append_log(f"Deleting: {launcher_name}")
                            os.remove(launcher_path)

                        # Rename .bak back to .exe
                        self.append_log(f"Restoring: {launcher_name.replace('.exe', '.bak')} -> {launcher_name}")
                        os.rename(backup_path, launcher_path)
                        self.append_log("Original launcher restored!")
                        launcher_restored = True

            self.append_log("")
            self.append_log("=" * 50)
            self.append_log("Data folder restored successfully!")
            self.append_log("=" * 50)

            return True, moved_count, launcher_restored

        except Exception as e:
            self.append_log(f"ERROR: {str(e)}")
            QMessageBox.critical(self, "Error", f"Failed to restore Data folder:\n{str(e)}")
            return False, 0, False

        finally:
            self.progress_bar.setVisible(False)
            self.update_build_button()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = MO2MergerGUI()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

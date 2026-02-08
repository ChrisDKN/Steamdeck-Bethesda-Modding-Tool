"""
Business logic, utility functions, and worker threads for the MO2 Manager GUI.
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

from PyQt6.QtCore import QThread, pyqtSignal

import build_json


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


def get_prefix_from_plugins_path(plugins_path):
    """Extract the Wine prefix path from a full plugins_path.

    For example, given:
      /home/deck/.local/share/Steam/steamapps/compatdata/377160/pfx/drive_c/users/steamuser/AppData/Local/Fallout4
    Returns:
      /home/deck/.local/share/Steam/steamapps/compatdata/377160
    """
    pfx_index = plugins_path.find("/pfx/")
    if pfx_index != -1:
        return plugins_path[:pfx_index]
    return plugins_path


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
            json.dump(build_json.get_default_game_paths(), f, indent=4)
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


def detect_proton_path(plugins_path):
    """Detect the Proton binary path from a game's plugins_path.

    Args:
        plugins_path: Full path like
            .../compatdata/489830/pfx/drive_c/users/steamuser/AppData/Local/...

    Returns:
        tuple: (proton_path, compat_data_path) on success

    Raises:
        ValueError: with descriptive message if detection fails
    """
    if not plugins_path:
        raise ValueError("No plugins path configured for this game.")

    pfx_index = plugins_path.find("/pfx/")
    if pfx_index == -1:
        raise ValueError("Could not determine Wine prefix from plugins path.")

    compat_data_path = plugins_path[:pfx_index]

    if not os.path.isdir(compat_data_path):
        raise ValueError(f"Compatdata folder not found:\n{compat_data_path}")

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
        raise ValueError(
            f"Could not detect Proton version.\n\n"
            f"The config_info file was not found or could not be parsed at:\n"
            f"{config_info_path}\n\n"
            "Make sure the game has been launched at least once via Steam."
        )

    return proton_path, compat_data_path


def get_se_manifest_path(game_data):
    """Get the path to the script extender install manifest for a game."""
    if not game_data:
        return None
    game_name = game_data.get("name", "").replace(" ", "_").lower()
    if not game_name:
        return None
    config_dir = os.path.join(os.path.expanduser("~"), ".config", "mo2manager")
    return os.path.join(config_dir, f"se_installed_{game_name}.json")


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
        is_goty = game_name == "Fallout 3 GOTY"
        # MO2 doesn't recognize "GOTY" variants; use the base game name
        if is_goty:
            game_name = "Fallout 3"
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
{"game_edition=Game Of The Year\n" if is_goty else "game_edition=Regular\n" if game_name == "Fallout 3" else ""}
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

        try:
            proton_path, compat_data_path = detect_proton_path(plugins_path)
        except ValueError as e:
            self.output_signal.emit(f"Skipping vcredist: {e}")
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

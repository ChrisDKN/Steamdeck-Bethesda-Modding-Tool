#!/usr/bin/env python3
"""
A Linux GUI application that helps merge MO2 mods into a single Data folder
using hardlinks.
"""

import os
import sys
import json
import shutil
import subprocess
import tempfile
import zipfile

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QComboBox,
    QTextEdit, QGroupBox, QMessageBox, QProgressBar,
    QInputDialog, QListWidget, QListWidgetItem,
    QDialog, QDialogButtonBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

import utils
import build_json


class InstancePanel(QWidget):
    """Left sidebar panel showing all discovered MO2 instances as clickable items."""

    instance_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.instances = []
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        header = QLabel("MO2 Instances")
        header.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(header)

        self.list_widget = QListWidget()
        self.list_widget.currentItemChanged.connect(self._on_item_changed)
        layout.addWidget(self.list_widget)

        self.path_label = QLabel("No instance selected")
        self.path_label.setStyleSheet("color: gray; font-size: 11px;")
        self.path_label.setWordWrap(True)
        layout.addWidget(self.path_label)

        btn_layout = QHBoxLayout()

        self.rescan_btn = QPushButton("Rescan")
        self.rescan_btn.setToolTip("Scan for MO2 installations")
        btn_layout.addWidget(self.rescan_btn)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setToolTip("Refresh mod lists, plugin lists, and folder status")
        btn_layout.addWidget(self.refresh_btn)

        self.add_btn = QPushButton("Add Instance")
        self.add_btn.setToolTip("Download and install a new MO2 instance")
        btn_layout.addWidget(self.add_btn)

        layout.addLayout(btn_layout)

    def set_instances(self, instances):
        """Populate the list with (display_name, folder_path) tuples."""
        self.instances = instances
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        for display_name, folder_path in instances:
            item = QListWidgetItem(display_name)
            item.setData(Qt.ItemDataRole.UserRole, folder_path)
            self.list_widget.addItem(item)
        self.list_widget.blockSignals(False)

    def _on_item_changed(self, current, previous):
        """Handle list selection change."""
        if current:
            folder_path = current.data(Qt.ItemDataRole.UserRole)
            self.path_label.setText(f"Path: {folder_path}")
            self.instance_selected.emit(folder_path)

    def select_by_path(self, path):
        """Select the instance matching the given path, if any."""
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == path:
                self.list_widget.setCurrentItem(item)
                return True
        return False

    def current_path(self):
        """Return the folder_path of the currently selected instance, or None."""
        item = self.list_widget.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None


class MO2MergerGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bethesda Modding Tool for Steam Deck / Linux")
        self.setMinimumSize(860, 800)

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

        # Instance panel (left sidebar)
        self.mo2_instances = utils.scan_for_mo2_instances()
        self.instance_panel = InstancePanel()
        self.instance_panel.setMaximumWidth(280)
        self.instance_panel.set_instances(self.mo2_instances)
        self.instance_panel.instance_selected.connect(self.on_instance_selected)
        self.instance_panel.rescan_btn.clicked.connect(self.rescan_mo2_instances)
        self.instance_panel.refresh_btn.clicked.connect(self.refresh_gui)
        self.instance_panel.add_btn.clicked.connect(self.add_mo2_instance)
        main_layout.addWidget(self.instance_panel)

        # Main controls panel
        main_controls = QWidget()
        layout = QVBoxLayout(main_controls)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)

        # MO2 Location Group
        mo2_group = QGroupBox("Mod Organizer 2 Location")
        mo2_layout = QVBoxLayout()

        # Instance action buttons row
        instance_btn_layout = QHBoxLayout()

        # Run MO2 button
        self.run_mo2_btn = QPushButton("Run MO2")
        self.run_mo2_btn.setEnabled(False)
        self.run_mo2_btn.setToolTip("Launch ModOrganizer.exe using the game's Proton version")
        self.run_mo2_btn.clicked.connect(self.run_mo2)
        instance_btn_layout.addWidget(self.run_mo2_btn)

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

        # MGE XE buttons row (Morrowind only)
        mge_layout = QHBoxLayout()
        mge_layout.addWidget(QLabel("MGE XE:"))

        self.mge_download_btn = QPushButton("Download Page")
        self.mge_download_btn.setEnabled(False)
        self.mge_download_btn.setToolTip("Open the MGE XE download page in your browser")
        self.mge_download_btn.clicked.connect(self.open_mge_xe_download)
        mge_layout.addWidget(self.mge_download_btn)

        self.mge_install_btn = QPushButton("Install from Zip")
        self.mge_install_btn.setEnabled(False)
        self.mge_install_btn.setToolTip("Install MGE XE from a downloaded zip file")
        self.mge_install_btn.clicked.connect(self.install_mge_xe)
        mge_layout.addWidget(self.mge_install_btn)

        mge_layout.addStretch()

        # Wrap in a widget so we can show/hide the whole row
        self.mge_row_widget = QWidget()
        self.mge_row_widget.setLayout(mge_layout)
        self.mge_row_widget.setVisible(False)
        mo2_layout.addWidget(self.mge_row_widget)

        # Code Patch buttons row (Morrowind only)
        mcp_layout = QHBoxLayout()
        mcp_layout.addWidget(QLabel("Code Patch:"))

        self.mcp_download_btn = QPushButton("Download Page")
        self.mcp_download_btn.setEnabled(False)
        self.mcp_download_btn.setToolTip("Open the Morrowind Code Patch download page in your browser")
        self.mcp_download_btn.clicked.connect(self.open_code_patch_download)
        mcp_layout.addWidget(self.mcp_download_btn)

        self.mcp_install_btn = QPushButton("Install from Zip")
        self.mcp_install_btn.setEnabled(False)
        self.mcp_install_btn.setToolTip("Install Morrowind Code Patch from a downloaded zip file and run it")
        self.mcp_install_btn.clicked.connect(self.install_code_patch)
        mcp_layout.addWidget(self.mcp_install_btn)

        mcp_layout.addStretch()

        self.mcp_row_widget = QWidget()
        self.mcp_row_widget.setLayout(mcp_layout)
        self.mcp_row_widget.setVisible(False)
        mo2_layout.addWidget(self.mcp_row_widget)

        # Status labels for mods and overwrite folders
        self.mods_status_label = QLabel("Mods folder: Not found")
        self.overwrite_status_label = QLabel("Overwrite folder: Not found")
        mo2_layout.addWidget(self.mods_status_label)
        mo2_layout.addWidget(self.overwrite_status_label)

        mo2_group.setLayout(mo2_layout)
        layout.addWidget(mo2_group)

        # Set initial state based on found instances
        if self.mo2_instances:
            self.mo2_path = self.mo2_instances[0][1]
            self.instance_panel.list_widget.setCurrentRow(0)
        else:
            self.instance_panel.path_label.setText("No instances found - use Add Instance")

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
        self.game_paths = utils.load_game_paths()
        game_select_layout = QHBoxLayout()
        game_select_layout.addWidget(QLabel("Game:"))
        self.game_combo = QComboBox()
        self.game_combo.setMinimumWidth(200)

        # Add games from config (only those that are installed)
        for game in self.game_paths:
            data_path = game.get("data_path", "")
            if data_path:
                game_folder = game.get("game_root") or os.path.dirname(data_path)
                if os.path.isdir(game_folder):
                    self.game_combo.addItem(game["name"], game)

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
        self.data_output_edit.editingFinished.connect(self._validate_data_path)
        data_output_browse_btn = QPushButton("Browse...")
        data_output_browse_btn.clicked.connect(self.browse_data_output)
        data_output_layout.addWidget(self.data_output_edit)
        data_output_layout.addWidget(data_output_browse_btn)
        output_layout.addLayout(data_output_layout)

        # Wine prefix display
        plugins_output_layout = QHBoxLayout()
        plugins_output_layout.addWidget(QLabel("Wine Prefix:"))
        self.plugins_output_edit = QLineEdit()
        self.plugins_output_edit.setPlaceholderText("Wine prefix location (eg. ~/.local/share/Steam/steamapps/compatdata/72850)")
        self.plugins_output_edit.setReadOnly(True)
        self.change_prefix_btn = QPushButton("Change Prefix")
        self.change_prefix_btn.setToolTip("Select a different Wine prefix folder (the folder containing pfx/)")
        self.change_prefix_btn.clicked.connect(self.change_game_prefix)
        plugins_output_layout.addWidget(self.plugins_output_edit)
        plugins_output_layout.addWidget(self.change_prefix_btn)
        output_layout.addLayout(plugins_output_layout)

        # Set initial state - show paths from first game if available
        if self.game_paths:
            self.data_output_edit.setText(self.game_paths[0].get("data_path", ""))
            self.plugins_output_edit.setText(utils.get_prefix_from_plugins_path(self.game_paths[0].get("prefix_path", "")))
            self.downgrade_btn.setVisible(self.game_paths[0].get("name") in ("Fallout 3", "Fallout 3 GOTY"))

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

        # Add main controls panel to layout
        main_layout.addWidget(main_controls)

        # Trigger initial validation now that all UI elements exist
        if self.mo2_path:
            self.validate_mo2_folder()

    def on_instance_selected(self, folder_path):
        """Handle instance selection from the InstancePanel."""
        if folder_path:
            self.mo2_path = folder_path
            self.validate_mo2_folder()

    def rescan_mo2_instances(self):
        """Rescan for MO2 instances and update the instance panel."""
        current_path = self.instance_panel.current_path()

        self.mo2_instances = utils.scan_for_mo2_instances()
        self.instance_panel.set_instances(self.mo2_instances)

        # Try to restore previous selection
        restored = False
        if current_path:
            restored = self.instance_panel.select_by_path(current_path)

        if self.mo2_instances and not restored:
            self.instance_panel.list_widget.setCurrentRow(0)
        elif not self.mo2_instances:
            self.instance_panel.path_label.setText("No instances found - use Add Instance")

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
                "Use 'Add Instance' to install one."
            )

    def refresh_gui(self):
        """Refresh the GUI: re-validate MO2 folder, reload mod list and plugin list."""
        self.validate_mo2_folder()
        self.append_log("GUI refreshed.")

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

        try:
            proton_path, compat_data_path = utils.detect_proton_path(game_data.get("prefix_path", ""))
        except ValueError as e:
            QMessageBox.warning(self, "Error", str(e))
            return

        env = utils.get_clean_env()
        env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = os.path.expanduser("~/.local/share/Steam")
        env["STEAM_COMPAT_DATA_PATH"] = compat_data_path

        # Newer MO2 builds (e.g. for Oblivion Remastered) crash with
        # "free(): unaligned chunk detected in tcache 2" due to glibc
        # allocator conflicts under Proton. Clearing LD_PRELOAD fixes this.
        if game_data.get("mo2_download_url"):
            env.pop("LD_PRELOAD", None)

        proton_name = os.path.basename(os.path.dirname(proton_path))

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

        subprocess.Popen(["xdg-open", url], env=utils.get_clean_env())

    def open_mge_xe_download(self):
        """Open the MGE XE download page in the browser."""
        game_data = self.game_combo.currentData()
        if not game_data:
            QMessageBox.warning(self, "Error", "No game selected.")
            return

        url = game_data.get("mge_xe_download", "")
        if not url:
            QMessageBox.warning(self, "Error", "No MGE XE download URL configured.")
            return

        subprocess.Popen(["xdg-open", url], env=utils.get_clean_env())

    def install_mge_xe(self):
        """Install MGE XE from a zip: root files go to game root, Data Files go to MO2 mods/mge_xe."""
        game_data = self.game_combo.currentData()
        if not game_data:
            QMessageBox.warning(self, "Error", "No game selected.")
            return

        game_root = game_data.get("game_root", "")
        if not game_root or not os.path.isdir(game_root):
            QMessageBox.warning(self, "Error", f"Game root directory not found:\n{game_root}")
            return

        if not self.mods_folder or not os.path.isdir(self.mods_folder):
            QMessageBox.warning(self, "Error", "MO2 mods folder not found. Please select an MO2 instance first.")
            return

        archive_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select MGE XE Archive",
            os.path.expanduser("~"),
            "Archives (*.zip *.7z);;Zip Files (*.zip);;7z Files (*.7z);;All Files (*)"
        )

        if not archive_path:
            return

        try:
            temp_dir = tempfile.mkdtemp(prefix="mge_xe_install_")

            try:
                if archive_path.lower().endswith(".zip"):
                    with zipfile.ZipFile(archive_path, 'r') as zf:
                        zf.extractall(temp_dir)
                else:
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
                            capture_output=True, text=True, env=utils.get_clean_env()
                        )
                        if result.returncode != 0:
                            raise Exception(f"Extraction failed: {result.stderr}")

                # Strip single root folder if present
                top_entries = os.listdir(temp_dir)
                if len(top_entries) == 1 and os.path.isdir(os.path.join(temp_dir, top_entries[0])):
                    content_root = os.path.join(temp_dir, top_entries[0])
                else:
                    content_root = temp_dir

                # Separate "Data Files" from everything else
                data_files_src = None
                for entry in os.listdir(content_root):
                    if entry.lower() == "data files" and os.path.isdir(os.path.join(content_root, entry)):
                        data_files_src = os.path.join(content_root, entry)
                        break

                # Copy everything except Data Files to game root
                root_count = 0
                for item in os.listdir(content_root):
                    if item.lower() == "data files":
                        continue
                    src = os.path.join(content_root, item)
                    dst = os.path.join(game_root, item)
                    if os.path.isdir(src):
                        if os.path.exists(dst):
                            shutil.rmtree(dst)
                        shutil.copytree(src, dst)
                    else:
                        shutil.copy2(src, dst)
                    root_count += 1

                self.append_log(f"Copied {root_count} items to game root: {game_root}")

                # Copy Data Files contents to mods/mge_xe
                data_count = 0
                if data_files_src:
                    mge_mod_path = os.path.join(self.mods_folder, "mge_xe")
                    os.makedirs(mge_mod_path, exist_ok=True)

                    for item in os.listdir(data_files_src):
                        src = os.path.join(data_files_src, item)
                        dst = os.path.join(mge_mod_path, item)
                        if os.path.isdir(src):
                            if os.path.exists(dst):
                                shutil.rmtree(dst)
                            shutil.copytree(src, dst)
                        else:
                            shutil.copy2(src, dst)
                        data_count += 1

                    self.append_log(f"Copied {data_count} items to mods/mge_xe: {mge_mod_path}")

                    # Add mge_xe to modlist.txt
                    if self.profiles_folder and self.selected_profile:
                        modlist_path = os.path.join(self.profiles_folder, self.selected_profile, "modlist.txt")
                        if os.path.isfile(modlist_path):
                            with open(modlist_path, 'r', encoding='utf-8') as f:
                                lines = f.readlines()

                            mge_entry = "+mge_xe\n"
                            has_mge = any(line.strip() in ("+mge_xe", "-mge_xe") for line in lines)

                            if not has_mge:
                                # Add at the bottom before trailing empty lines
                                insert_pos = len(lines)
                                for i in range(len(lines) - 1, -1, -1):
                                    if lines[i].strip():
                                        insert_pos = i + 1
                                        break

                                lines.insert(insert_pos, mge_entry)
                                with open(modlist_path, 'w', encoding='utf-8') as f:
                                    f.writelines(lines)
                                self.append_log("Added '+mge_xe' to modlist.txt")
                            else:
                                self.append_log("mge_xe already in modlist.txt, skipping")

                self.update_build_button()
                QMessageBox.information(
                    self,
                    "Success",
                    f"MGE XE installed successfully.\n\n"
                    f"{root_count} items copied to game root.\n"
                    f"{data_count} items copied to mods/mge_xe."
                )

            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

        except zipfile.BadZipFile:
            QMessageBox.warning(self, "Error", "The selected file is not a valid zip archive.")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to install MGE XE:\n{str(e)}")

    def open_code_patch_download(self):
        """Open the Morrowind Code Patch download page in the browser."""
        game_data = self.game_combo.currentData()
        if not game_data:
            QMessageBox.warning(self, "Error", "No game selected.")
            return

        url = game_data.get("code_patch_download", "")
        if not url:
            QMessageBox.warning(self, "Error", "No Code Patch download URL configured.")
            return

        subprocess.Popen(["xdg-open", url], env=utils.get_clean_env())

    def install_code_patch(self):
        """Install Morrowind Code Patch from a zip: extract to game root and run the patcher."""
        game_data = self.game_combo.currentData()
        if not game_data:
            QMessageBox.warning(self, "Error", "No game selected.")
            return

        game_root = game_data.get("game_root", "")
        if not game_root or not os.path.isdir(game_root):
            QMessageBox.warning(self, "Error", f"Game root directory not found:\n{game_root}")
            return

        archive_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Morrowind Code Patch Archive",
            os.path.expanduser("~"),
            "Archives (*.zip *.7z);;Zip Files (*.zip);;7z Files (*.7z);;All Files (*)"
        )

        if not archive_path:
            return

        try:
            temp_dir = tempfile.mkdtemp(prefix="mcp_install_")

            try:
                if archive_path.lower().endswith(".zip"):
                    with zipfile.ZipFile(archive_path, 'r') as zf:
                        zf.extractall(temp_dir)
                else:
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
                            capture_output=True, text=True, env=utils.get_clean_env()
                        )
                        if result.returncode != 0:
                            raise Exception(f"Extraction failed: {result.stderr}")

                # Strip single root folder if present
                top_entries = os.listdir(temp_dir)
                if len(top_entries) == 1 and os.path.isdir(os.path.join(temp_dir, top_entries[0])):
                    content_root = os.path.join(temp_dir, top_entries[0])
                else:
                    content_root = temp_dir

                # Copy everything to game root
                file_count = 0
                for item in os.listdir(content_root):
                    src = os.path.join(content_root, item)
                    dst = os.path.join(game_root, item)
                    if os.path.isdir(src):
                        if os.path.exists(dst):
                            shutil.rmtree(dst)
                        shutil.copytree(src, dst)
                    else:
                        shutil.copy2(src, dst)
                    file_count += 1

                self.append_log(f"Copied {file_count} items to game root: {game_root}")

            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

            # Run Morrowind Code Patch.exe via Proton
            patcher_exe = os.path.join(game_root, "Morrowind Code Patch.exe")
            if not os.path.isfile(patcher_exe):
                QMessageBox.warning(
                    self,
                    "Warning",
                    f"Files extracted but 'Morrowind Code Patch.exe' not found in:\n{game_root}"
                )
                return

            try:
                proton_path, compat_data_path = utils.detect_proton_path(game_data.get("prefix_path", ""))
            except ValueError as e:
                QMessageBox.warning(self, "Error", f"Files extracted but could not detect Proton:\n{str(e)}")
                return

            env = utils.get_clean_env()
            env["STEAM_COMPAT_CLIENT_INSTALL_PATH"] = os.path.expanduser("~/.local/share/Steam")
            env["STEAM_COMPAT_DATA_PATH"] = compat_data_path

            proton_name = os.path.basename(os.path.dirname(proton_path))

            try:
                self.append_log(f"Running Morrowind Code Patch via {proton_name}...")
                subprocess.Popen(
                    [proton_path, "run", patcher_exe],
                    env=env,
                    cwd=game_root
                )
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to launch Morrowind Code Patch:\n{str(e)}")

        except zipfile.BadZipFile:
            QMessageBox.warning(self, "Error", "The selected file is not a valid zip archive.")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to install Code Patch:\n{str(e)}")

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

        game_root = game_data.get("launcher_location") or game_data.get("game_root") or os.path.dirname(data_path)
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
                            capture_output=True, text=True, env=utils.get_clean_env()
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
                manifest_path = utils.get_se_manifest_path(game_data)
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

    def uninstall_script_extender(self):
        """Remove previously installed script extender files using the saved manifest."""
        game_data = self.game_combo.currentData()
        if not game_data:
            QMessageBox.warning(self, "Error", "No game selected.")
            return

        manifest_path = utils.get_se_manifest_path(game_data)
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
        game_root = game_data.get("game_root") or (os.path.dirname(data_path) if data_path else "")
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
        launcher_dir = game_data.get("launcher_location") or game_root
        if launcher_name and launcher_dir:
            launcher_path = os.path.join(launcher_dir, launcher_name)
            backup_path = os.path.join(launcher_dir, launcher_name.replace(".exe", ".bak"))
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

    def _update_game_data_path(self, game_name, new_data_path):
        """Update data_path in config for the given game."""
        for game in self.game_paths:
            if game.get("name") == game_name:
                if game.get("data_path") == new_data_path:
                    return
                game["data_path"] = new_data_path
                break
        utils.save_game_paths(self.game_paths)
        self.append_log(f"Updated data_path for {game_name}: {new_data_path}")
        self._refresh_game_combo()

    def _update_game_prefix_path(self, game_name, new_prefix_path):
        """Update prefix_path in config to reflect a custom wine prefix."""
        for game in self.game_paths:
            if game.get("name") == game_name:
                if game.get("prefix_path") == new_prefix_path:
                    return
                game["prefix_path"] = new_prefix_path
                break
        utils.save_game_paths(self.game_paths)
        self.append_log(f"Updated prefix_path for {game_name}: {new_prefix_path}")
        self._refresh_game_combo()

    def _update_game_plugins_path(self, game_name, new_plugins_path):
        """Update plugins_path in config to reflect a custom wine prefix."""
        for game in self.game_paths:
            if game.get("name") == game_name:
                if game.get("plugins_path") == new_plugins_path:
                    return
                game["plugins_path"] = new_plugins_path
                break
        utils.save_game_paths(self.game_paths)
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
                game_folder = game.get("game_root") or os.path.dirname(data_path)
                if os.path.isdir(game_folder):
                    self.game_combo.addItem(game["name"], game)
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
            self.plugins_output_edit.setText(utils.get_prefix_from_plugins_path(game_data.get("prefix_path", "")))

    def _start_mo2_download(self, folder, selected_game_data):
        """Start the MO2 download/install worker for a given folder and game."""
        local_archive = None
        mo2_download_url = selected_game_data.get("mo2_download_url")
        if mo2_download_url:
            # Game requires a manually downloaded MO2 version (e.g. OneDrive link)
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setWindowTitle("Manual MO2 Download Required")
            msg.setText(
                f"{selected_game_data.get('name', 'This game')} requires a specific version of "
                "Mod Organizer 2 that must be downloaded manually.\n\n"
                "Download the MO2 archive from the link, then select the downloaded file."
            )
            msg.addButton("Open Download Page", QMessageBox.ButtonRole.ActionRole)
            select_btn = msg.addButton("Select Archive", QMessageBox.ButtonRole.AcceptRole)
            msg.addButton(QMessageBox.StandardButton.Cancel)
            msg.exec()

            clicked = msg.clickedButton()
            if clicked is None or clicked.text() == "Cancel":
                return

            if clicked.text() == "Open Download Page":
                subprocess.Popen(["xdg-open", mo2_download_url], env=utils.get_clean_env())

            local_archive, _ = QFileDialog.getOpenFileName(
                self,
                "Select Downloaded MO2 Archive",
                os.path.expanduser("~/Downloads"),
                "Archives (*.zip *.7z);;All Files (*)"
            )
            if not local_archive:
                return

        self.log_text.clear()
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.instance_panel.add_btn.setEnabled(False)

        self.download_worker = utils.DownloadWorker(folder, selected_game_data, local_archive=local_archive)
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
        installed_games = utils.find_game_installs(self.game_paths)

        # If both Fallout 3 and Fallout 3 GOTY were found (same launcher),
        # keep only Fallout 3 — the version dialog later handles the choice
        if "Fallout 3" in installed_games and "Fallout 3 GOTY" in installed_games:
            del installed_games["Fallout 3 GOTY"]

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
            found = utils._scan_for_launchers(self.game_paths, [folder])

            if not found:
                QMessageBox.warning(
                    dialog,
                    "No Game Detected",
                    f"No supported game launcher was found in:\n\n{folder}\n\n"
                    "Make sure you selected the game's install folder\n"
                    "(the folder containing the game's launcher .exe)."
                )
                return

            # If both Fallout 3 and Fallout 3 GOTY were found (same launcher),
            # keep only Fallout 3 — the version dialog later handles the choice
            if "Fallout 3" in found and "Fallout 3 GOTY" in found:
                del found["Fallout 3 GOTY"]

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
            custom_prefix_path = None
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

                # Build new prefix_path and plugins_path using suffixes from the default config
                game_cfg = None
                for g in self.game_paths:
                    if g.get("name") == name:
                        game_cfg = g
                        break
                if game_cfg:
                    # Build custom prefix_path
                    default_prefix = game_cfg.get("prefix_path", "")
                    pfx_index = default_prefix.find("/pfx/")
                    if pfx_index != -1:
                        prefix_suffix = default_prefix[pfx_index:]
                        custom_prefix_path = prefix_folder + prefix_suffix

                    # Build custom plugins_path (only for games where plugins.txt
                    # lives in the wine prefix, detected by /pfx/ in the path)
                    default_pp = game_cfg.get("plugins_path", "")
                    pp_pfx_index = default_pp.find("/pfx/")
                    if pp_pfx_index != -1:
                        suffix = default_pp[pp_pfx_index:]
                        custom_plugins_path = prefix_folder + suffix

            custom_result["game_name"] = name
            custom_result["game_folder"] = gfolder
            custom_result["plugins_path"] = custom_plugins_path
            custom_result["prefix_path"] = custom_prefix_path
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

        # If Fallout 3 is selected, ask which version the user has
        if selected_game == "Fallout 3":
            version_dialog = QMessageBox(self)
            version_dialog.setWindowTitle("Fallout 3 Version")
            version_dialog.setText(
                "Which version of Fallout 3 do you have?\n\n"
                "The GOTY edition uses a different Steam ID (22370)\n"
                "and requires a different wine prefix."
            )
            normal_btn = version_dialog.addButton("Standard (22300)", QMessageBox.ButtonRole.AcceptRole)
            goty_btn = version_dialog.addButton("GOTY (22370)", QMessageBox.ButtonRole.AcceptRole)
            version_dialog.addButton(QMessageBox.StandardButton.Cancel)
            version_dialog.exec()

            clicked = version_dialog.clickedButton()
            if clicked == goty_btn:
                selected_game = "Fallout 3 GOTY"
                # Update custom_result if it was a custom location flow
                if custom_result:
                    custom_result["game_name"] = selected_game
            elif clicked != normal_btn:
                # User cancelled
                return

        # Find the selected game data
        selected_game_data = None
        for game in self.game_paths:
            if game["name"] == selected_game:
                selected_game_data = game
                break

        # Derive actual game root from the detected game_folder.
        # game_folder from the launcher scan points to where the launcher exe is,
        # which may differ from game_root (e.g. Oblivion Remastered's launcher is
        # in a nested Binaries/Win64 subdirectory).
        actual_game_root = game_folder
        if selected_game_data:
            default_launcher_loc = selected_game_data.get("launcher_location", "")
            default_game_root = selected_game_data.get("game_root", "")
            if default_launcher_loc and default_game_root and default_launcher_loc != default_game_root:
                try:
                    launcher_rel = os.path.relpath(default_launcher_loc, default_game_root)
                except ValueError:
                    launcher_rel = ""
                if launcher_rel and launcher_rel != "." and game_folder.endswith(launcher_rel):
                    actual_game_root = game_folder[:-len(launcher_rel)].rstrip(os.sep)

        # Update game_root and launcher_location to reflect the detected location
        if selected_game_data:
            selected_game_data["game_root"] = actual_game_root
            selected_game_data["launcher_location"] = game_folder

        # Build the correct data_path using data_subpath
        data_subpath = selected_game_data.get("data_subpath", "Data") if selected_game_data else "Data"
        self._update_game_data_path(selected_game, os.path.join(actual_game_root, data_subpath))

        # For games where plugins_path is inside the game folder (not a wine
        # prefix), rebuild it relative to the actual game root.
        if selected_game_data:
            default_pp = selected_game_data.get("default_plugins_path", "")
            if default_pp and "/pfx/" not in default_pp:
                default_game_root = selected_game_data.get("game_root", "")
                if default_game_root:
                    try:
                        pp_rel = os.path.relpath(default_pp, default_game_root)
                    except ValueError:
                        pp_rel = ""
                    if pp_rel and pp_rel != ".":
                        new_pp = os.path.join(actual_game_root, pp_rel)
                        self._update_game_plugins_path(selected_game, new_pp)

        # Update prefix_path and plugins_path: use custom prefix if provided, otherwise reset to default
        if custom_result and custom_result.get("prefix_path"):
            self._update_game_prefix_path(selected_game, custom_result["prefix_path"])
        if custom_result and custom_result.get("plugins_path"):
            self._update_game_plugins_path(selected_game, custom_result["plugins_path"])
        elif custom_result and selected_game_data:
            default_pp = selected_game_data.get("default_plugins_path", "")
            # Only fall back to default_plugins_path for prefix-based paths
            if default_pp and "/pfx/" in default_pp:
                self._update_game_plugins_path(selected_game, default_pp)

        # Create subfolder named "<game name> MO2"
        folder = os.path.join(actual_game_root, f"{selected_game} MO2")

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
            subprocess.Popen(["xdg-open", game_folder], env=utils.get_clean_env())

    def download_finished(self, success, result):
        """Handle download completion."""
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 0)  # Reset to indeterminate
        self.instance_panel.add_btn.setEnabled(True)

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
        else:
            self.modlist_status_label.setText("modlist.txt: Not found")
            self.modlist_status_label.setStyleSheet("color: red;")

        # Check for plugins.txt
        plugins_path = os.path.join(profile_path, "plugins.txt")
        if os.path.isfile(plugins_path):
            self.plugins_status_label.setText(f"plugins.txt: Found")
            self.plugins_status_label.setStyleSheet("color: green;")
        else:
            self.plugins_status_label.setText("plugins.txt: Not found")
            self.plugins_status_label.setStyleSheet("color: red;")

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
                        self.plugins_output_edit.setText(utils.get_prefix_from_plugins_path(game.get("prefix_path", "")))
                        # Update downgrade button visibility
                        self.downgrade_btn.setVisible(game_name in ("Fallout 3", "Fallout 3 GOTY"))
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
            self._validate_data_path()
            self.update_build_button()

    def on_game_changed(self, index):
        """Handle game selection change - updates both Data and plugins.txt paths."""
        game_data = self.game_combo.currentData()
        if game_data:
            self.data_output_edit.setText(game_data.get("data_path", ""))
            self.plugins_output_edit.setText(utils.get_prefix_from_plugins_path(game_data.get("prefix_path", "")))

        # Show Downgrade button only for Fallout 3
        is_fallout3 = game_data is not None and game_data.get("name") in ("Fallout 3", "Fallout 3 GOTY")
        self.downgrade_btn.setVisible(is_fallout3)

        self.update_build_button()

    def run_winecfg(self):
        """Launch winecfg for the selected game's Wine prefix using its Proton version."""
        game_data = self.game_combo.currentData()
        if game_data is None:
            QMessageBox.warning(self, "Error", "No game selected. Please select a game first.")
            return

        try:
            proton_path, compat_data_path = utils.detect_proton_path(game_data.get("prefix_path", ""))
        except ValueError as e:
            QMessageBox.warning(self, "Error", str(e))
            return

        env = utils.get_clean_env()
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

        prefix_path = game_data.get("prefix_path", "")
        if not prefix_path:
            QMessageBox.warning(self, "Error", "No prefix path configured for this game.")
            return

        # Extract app ID from compatdata path
        compat_data_path = utils.get_prefix_from_plugins_path(prefix_path)
        app_id = os.path.basename(compat_data_path)

        if not app_id.isdigit():
            QMessageBox.warning(
                self, "Error",
                f"Cannot launch protontricks for a custom prefix.\n\n"
                f"Protontricks requires a numeric Steam App ID, but the prefix folder "
                f"name is '{app_id}'.\n\n"
                f"Protontricks only works with standard Steam prefixes "
                f"(e.g. compatdata/377160)."
            )
            return

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

        env = utils.get_clean_env()
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

        # Build new prefix_path from the default to get the suffix
        default_prefix = game_data.get("prefix_path", "")
        pfx_index = default_prefix.find("/pfx/")
        if pfx_index != -1:
            prefix_suffix = default_prefix[pfx_index:]
            new_prefix_path = prefix_folder + prefix_suffix
        else:
            new_prefix_path = prefix_folder

        # Update prefix_path always
        self._update_game_prefix_path(game_name, new_prefix_path)

        # Update plugins_path too (only for games where plugins.txt is in the
        # wine prefix — detected by /pfx/ in the path)
        default_pp = game_data.get("default_plugins_path", game_data.get("plugins_path", ""))
        pp_pfx_index = default_pp.find("/pfx/")
        if pp_pfx_index != -1:
            plugins_suffix = default_pp[pp_pfx_index:]
            new_plugins_path = prefix_folder + plugins_suffix
            self._update_game_plugins_path(game_name, new_plugins_path)

    def run_exe_in_game_prefix(self):
        """Run an executable in the selected game's Wine prefix using its Proton version."""
        game_data = self.game_combo.currentData()
        if game_data is None:
            QMessageBox.warning(self, "Error", "No game selected. Please select a game first.")
            return

        try:
            proton_path, compat_data_path = utils.detect_proton_path(game_data.get("prefix_path", ""))
        except ValueError as e:
            QMessageBox.warning(self, "Error", str(e))
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
        env = utils.get_clean_env()
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
        if game_data is None or game_data.get("name") not in ("Fallout 3", "Fallout 3 GOTY"):
            return

        data_path = game_data.get("data_path", "")
        if not data_path:
            QMessageBox.warning(self, "Error", "No data path configured for Fallout 3.")
            return

        game_dir = game_data.get("game_root") or os.path.dirname(data_path)
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
                subprocess.Popen(["xdg-open", "https://www.nexusmods.com/fallout3/mods/24913"], env=utils.get_clean_env())
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

        # Detect Proton version
        try:
            proton_path, compat_data_path = utils.detect_proton_path(game_data.get("prefix_path", ""))
        except ValueError as e:
            QMessageBox.warning(self, "Error", str(e))
            return

        # Run Patcher.exe via Proton
        env = utils.get_clean_env()
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

    def _validate_data_path(self):
        """Validate the Data folder path and update config.

        The path must end with '<game folder>/Data' (e.g. 'Fallout 4/Data').
        The expected suffix is derived from the default data_path for the
        selected game. If invalid, revert to default.
        """
        path = self.data_output_edit.text().rstrip("/")
        game_data = self.game_combo.currentData()
        if not game_data:
            return

        game_name = game_data.get("name", "")

        # Get the expected suffix from the default config (e.g. "Fallout 4/Data")
        defaults = build_json.get_default_game_paths()
        default_path = ""
        expected_suffix = ""
        for g in defaults["games"]:
            if g.get("name") == game_name:
                default_path = g.get("data_path", "")
                # Use data_subpath if available (handles deeply nested paths like OR)
                data_subpath = g.get("data_subpath", "")
                if data_subpath:
                    expected_suffix = data_subpath
                else:
                    # Fallback: extract last 2 components
                    parts = default_path.rsplit("/", 2)
                    if len(parts) >= 2:
                        expected_suffix = parts[-2] + "/" + parts[-1]
                break

        if not expected_suffix or not path.endswith(expected_suffix):
            self.data_output_edit.blockSignals(True)
            self.data_output_edit.setText(default_path)
            self.data_output_edit.blockSignals(False)
            self._update_game_data_path(game_name, default_path)
        else:
            self._update_game_data_path(game_name, path)

    def update_build_button(self):
        # Update Script Extender buttons (created early, so always safe to check)
        if hasattr(self, 'se_download_btn'):
            game_data = self.game_combo.currentData() if hasattr(self, 'game_combo') else None
            has_se_download = bool(game_data and game_data.get("script_extender_download"))
            self.se_download_btn.setEnabled(has_se_download)
            has_se_name = bool(game_data and game_data.get("script_extender_name"))
            self.se_install_btn.setEnabled(has_se_name)
            has_manifest = bool(game_data and utils.get_se_manifest_path(game_data) and
                                os.path.isfile(utils.get_se_manifest_path(game_data)))
            self.se_uninstall_btn.setEnabled(has_manifest)

            # Update script extender status label
            if hasattr(self, 'se_status_label'):
                se_name = game_data.get("script_extender_name", "") if game_data else ""
                if se_name:
                    game_folder = game_data.get("launcher_location") or game_data.get("game_root") or (os.path.dirname(game_data.get("data_path", "")) if game_data.get("data_path") else "")
                    se_path = os.path.join(game_folder, se_name) if game_folder else ""
                    if se_path and os.path.isfile(se_path):
                        self.se_status_label.setText(f"Script Extender: {se_name} found")
                        self.se_status_label.setStyleSheet("color: green;")
                    else:
                        self.se_status_label.setText(f"Script Extender: {se_name} not found")
                        self.se_status_label.setStyleSheet("color: orange;")
                else:
                    self.se_status_label.setText("")

        # Update MGE XE buttons (Morrowind only)
        if hasattr(self, 'mge_row_widget'):
            game_data = self.game_combo.currentData() if hasattr(self, 'game_combo') else None
            has_mge = bool(game_data and game_data.get("mge_xe_download"))
            self.mge_row_widget.setVisible(has_mge)
            if has_mge:
                self.mge_download_btn.setEnabled(True)
                self.mge_install_btn.setEnabled(bool(self.mods_folder))

        # Update Code Patch buttons (Morrowind only)
        if hasattr(self, 'mcp_row_widget'):
            game_data = self.game_combo.currentData() if hasattr(self, 'game_combo') else None
            has_mcp = bool(game_data and game_data.get("code_patch_download"))
            self.mcp_row_widget.setVisible(has_mcp)
            if has_mcp:
                self.mcp_download_btn.setEnabled(True)
                self.mcp_install_btn.setEnabled(True)

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
        game_data = self.game_combo.currentData()
        plugins_dest = game_data.get("plugins_path", "") if game_data else ""
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

        self.worker = utils.BuildWorker(
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
                    game_folder = game_data.get("launcher_location") or game_data.get("game_root") or os.path.dirname(data_path)
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

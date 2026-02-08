import os

def get_default_game_paths():
    """Return the default game configuration data."""
    home = os.path.expanduser("~")
    steam_common = os.path.join(home, ".local/share/Steam/steamapps/common")
    steam_compat = os.path.join(home, ".local/share/Steam/steamapps/compatdata")
    pfx_path = "pfx/drive_c/users/steamuser/AppData/Local"
    return {"games": [
        {
            "name": "Skyrim Special Edition",
            "data_path": os.path.join(steam_common, "Skyrim Special Edition/Data"),
            "plugins_path": os.path.join(steam_compat, "489830", pfx_path, "Skyrim Special Edition"),
            "default_plugins_path": os.path.join(steam_compat, "489830", pfx_path, "Skyrim Special Edition"),
            "launcher_name": "SkyrimSELauncher.exe",
            "script_extender_name": "skse64_loader.exe",
            "script_extender_download": "https://skse.silverlock.org/"
        },
        {
            "name": "Skyrim",
            "data_path": os.path.join(steam_common, "Skyrim/Data"),
            "plugins_path": os.path.join(steam_compat, "72850", pfx_path, "Skyrim"),
            "default_plugins_path": os.path.join(steam_compat, "72850", pfx_path, "Skyrim"),
            "launcher_name": "SkyrimLauncher.exe",
            "script_extender_name": "skse_loader.exe",
            "script_extender_download": "https://skse.silverlock.org/"
        },
        {
            "name": "Fallout 4",
            "data_path": os.path.join(steam_common, "Fallout 4/Data"),
            "plugins_path": os.path.join(steam_compat, "377160", pfx_path, "Fallout4"),
            "default_plugins_path": os.path.join(steam_compat, "377160", pfx_path, "Fallout4"),
            "launcher_name": "Fallout4Launcher.exe",
            "script_extender_name": "f4se_loader.exe",
            "script_extender_download": "https://f4se.silverlock.org/"
        },
        {
            "name": "Fallout 3",
            "data_path": os.path.join(steam_common, "Fallout 3/Data"),
            "plugins_path": os.path.join(steam_compat, "22300", pfx_path, "Fallout3"),
            "default_plugins_path": os.path.join(steam_compat, "22300", pfx_path, "Fallout3"),
            "launcher_name": "Fallout3Launcher.exe",
            "script_extender_name": "fose_loader.exe",
            "script_extender_download": "https://fose.silverlock.org/"
        },
        {
            "name": "Fallout 3 GOTY",
            "data_path": os.path.join(steam_common, "Fallout 3 goty/Data"),
            "plugins_path": os.path.join(steam_compat, "22370", pfx_path, "Fallout3"),
            "default_plugins_path": os.path.join(steam_compat, "22370", pfx_path, "Fallout3"),
            "launcher_name": "Fallout3Launcher.exe",
            "script_extender_name": "fose_loader.exe",
            "script_extender_download": "https://fose.silverlock.org/"
        },
        {
            "name": "New Vegas",
            "data_path": os.path.join(steam_common, "Fallout New Vegas/Data"),
            "plugins_path": os.path.join(steam_compat, "22380", pfx_path, "FalloutNV"),
            "default_plugins_path": os.path.join(steam_compat, "22380", pfx_path, "FalloutNV"),
            "launcher_name": "FalloutNVLauncher.exe",
            "script_extender_name": "nvse_loader.exe",
            "script_extender_download": "https://github.com/xNVSE/NVSE/releases"
        },
        {
            "name": "Oblivion",
            "data_path": os.path.join(steam_common, "Oblivion/Data"),
            "plugins_path": os.path.join(steam_compat, "22330", pfx_path, "Oblivion"),
            "default_plugins_path": os.path.join(steam_compat, "22330", pfx_path, "Oblivion"),
            "launcher_name": "OblivionLauncher.exe",
            "script_extender_name": "obse_loader.exe",
            "script_extender_download": "https://obse.silverlock.org/"
        }
    ]}
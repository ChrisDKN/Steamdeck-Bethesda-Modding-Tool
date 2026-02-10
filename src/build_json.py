import os
import utils

def get_default_game_paths():
    """Return the default game configuration data."""
    home = os.path.expanduser("~")
    steam_common = os.path.join(home, ".local/share/Steam/steamapps/common")
    steam_compat = os.path.join(home, ".local/share/Steam/steamapps/compatdata")
    pfx_path = "pfx/drive_c/users/steamuser/AppData/Local"

    return {"games": [
        {
            "name": "Skyrim Special Edition",
            "prefix_path": os.path.join(steam_compat, utils.get_steam_id("Skyrim Special Edition"), pfx_path),
            "data_path": os.path.join(steam_common, "Skyrim Special Edition/Data"),
            "plugins_path": os.path.join(steam_compat, utils.get_steam_id("Skyrim Special Edition"), pfx_path, "Skyrim Special Edition"),
            "default_plugins_path": os.path.join(steam_compat, utils.get_steam_id("Skyrim Special Edition"), pfx_path, "Skyrim Special Edition"),
            "launcher_name": "SkyrimSELauncher.exe",
            "launcher_location": os.path.join(steam_common, "Skyrim Special Edition"),
            "game_root": os.path.join(steam_common, "Skyrim Special Edition"),
            "data_subpath": "Data",
            "script_extender_name": "skse64_loader.exe",
            "script_extender_download": "https://skse.silverlock.org/"
        },
        {
            "name": "Skyrim",
            "prefix_path": os.path.join(steam_compat, utils.get_steam_id("Skyrim"), pfx_path),
            "data_path": os.path.join(steam_common, "Skyrim/Data"),
            "plugins_path": os.path.join(steam_compat, utils.get_steam_id("Skyrim"), pfx_path, "Skyrim"),
            "default_plugins_path": os.path.join(steam_compat, utils.get_steam_id("Skyrim"), pfx_path, "Skyrim"),
            "launcher_name": "SkyrimLauncher.exe",
            "launcher_location": os.path.join(steam_common, "Skyrim"),
            "game_root": os.path.join(steam_common, "Skyrim"),
            "data_subpath": "Data",
            "script_extender_name": "skse_loader.exe",
            "script_extender_download": "https://skse.silverlock.org/"
        },
        {
            "name": "Fallout 4",
            "prefix_path": os.path.join(steam_compat, utils.get_steam_id("Fallout 4"), pfx_path),
            "data_path": os.path.join(steam_common, "Fallout 4/Data"),
            "plugins_path": os.path.join(steam_compat, utils.get_steam_id("Fallout 4"), pfx_path, "Fallout4"),
            "default_plugins_path": os.path.join(steam_compat, utils.get_steam_id("Fallout 4"), pfx_path, "Fallout4"),
            "launcher_name": "Fallout4Launcher.exe",
            "launcher_location": os.path.join(steam_common, "Fallout 4"),
            "game_root": os.path.join(steam_common, "Fallout 4"),
            "data_subpath": "Data",
            "script_extender_name": "f4se_loader.exe",
            "script_extender_download": "https://f4se.silverlock.org/"
        },
        {
            "name": "Fallout London",
            "prefix_path": os.path.join(steam_compat, "folon", pfx_path),
            "data_path": os.path.join(steam_common, "Fallout London/Data"),
            "plugins_path": os.path.join(steam_compat, "folon", pfx_path, "Fallout4"),
            "default_plugins_path": os.path.join(steam_compat, "folon", pfx_path, "Fallout4"),
            "launcher_name": "Fallout4Launcher.exe",
            "launcher_location": os.path.join(steam_common, "Fallout London"),
            "game_root": os.path.join(steam_common, "Fallout London"),
            "data_subpath": "Data",
            "script_extender_name": "f4se_loader.exe",
            "script_extender_download": "https://f4se.silverlock.org/"
        },
        {
            "name": "Fallout 3",
            "prefix_path": os.path.join(steam_compat, utils.get_steam_id("Fallout 3"), pfx_path),
            "data_path": os.path.join(steam_common, "Fallout 3/Data"),
            "plugins_path": os.path.join(steam_compat, utils.get_steam_id("Fallout 3"), pfx_path, "Fallout3"),
            "default_plugins_path": os.path.join(steam_compat, utils.get_steam_id("Fallout 3"), pfx_path, "Fallout3"),
            "launcher_name": "Fallout3Launcher.exe",
            "launcher_location": os.path.join(steam_common, "Fallout 3"),
            "game_root": os.path.join(steam_common, "Fallout 3"),
            "data_subpath": "Data",
            "script_extender_name": "fose_loader.exe",
            "script_extender_download": "https://fose.silverlock.org/"
        },
        {
            "name": "Fallout 3 GOTY",
            "prefix_path": os.path.join(steam_compat, utils.get_steam_id("Fallout 3 GOTY"), pfx_path),
            "data_path": os.path.join(steam_common, "Fallout 3 goty/Data"),
            "plugins_path": os.path.join(steam_compat, utils.get_steam_id("Fallout 3 GOTY"), pfx_path, "Fallout3"),
            "default_plugins_path": os.path.join(steam_compat, utils.get_steam_id("Fallout 3 GOTY"), pfx_path, "Fallout3"),
            "launcher_name": "Fallout3Launcher.exe",
            "launcher_location": os.path.join(steam_common, "Fallout 3 goty"),
            "game_root": os.path.join(steam_common, "Fallout 3 goty"),
            "data_subpath": "Data",
            "script_extender_name": "fose_loader.exe",
            "script_extender_download": "https://fose.silverlock.org/"
        },
        {
            "name": "New Vegas",
            "prefix_path": os.path.join(steam_compat, utils.get_steam_id("New Vegas"), pfx_path),
            "data_path": os.path.join(steam_common, "Fallout New Vegas/Data"),
            "plugins_path": os.path.join(steam_compat, utils.get_steam_id("New Vegas"), pfx_path, "FalloutNV"),
            "default_plugins_path": os.path.join(steam_compat, utils.get_steam_id("New Vegas"), pfx_path, "FalloutNV"),
            "launcher_name": "FalloutNVLauncher.exe",
            "launcher_location": os.path.join(steam_common, "Fallout New Vegas"),
            "game_root": os.path.join(steam_common, "Fallout New Vegas"),
            "data_subpath": "Data",
            "script_extender_name": "nvse_loader.exe",
            "script_extender_download": "https://github.com/xNVSE/NVSE/releases"
        },
        {
            "name": "Oblivion",
            "prefix_path": os.path.join(steam_compat, utils.get_steam_id("Oblivion"), pfx_path),
            "data_path": os.path.join(steam_common, "Oblivion/Data"),
            "plugins_path": os.path.join(steam_compat, utils.get_steam_id("Oblivion"), pfx_path, "Oblivion"),
            "default_plugins_path": os.path.join(steam_compat, utils.get_steam_id("Oblivion"), pfx_path, "Oblivion"),
            "launcher_name": "OblivionLauncher.exe",
            "launcher_location": os.path.join(steam_common, "Oblivion"),
            "game_root": os.path.join(steam_common, "Oblivion"),
            "data_subpath": "Data",
            "script_extender_name": "obse_loader.exe",
            "script_extender_download": "https://obse.silverlock.org/"
        },
        {
            "name": "Oblivion Remastered",
            "prefix_path": os.path.join(steam_compat, utils.get_steam_id("Oblivion Remastered"), pfx_path),
            "data_path": os.path.join(steam_common, "Oblivion Remastered/OblivionRemastered/Content"),
            "plugins_path": os.path.join(steam_common, "Oblivion Remastered/OblivionRemastered/Content/Dev/ObvData/Data"),
            "default_plugins_path": os.path.join(steam_common, "Oblivion Remastered/OblivionRemastered/Content/Dev/ObvData/Data"),
            "launcher_name": "OblivionRemastered-Win64-Shipping.exe",
            "launcher_location": os.path.join(steam_common, "Oblivion Remastered/OblivionRemastered/Binaries/Win64"),
            "game_root": os.path.join(steam_common, "Oblivion Remastered"),
            "data_subpath": "OblivionRemastered/Content",
            "script_extender_name": "obse64_loader.exe",
            "script_extender_download": "https://www.nexusmods.com/oblivionremastered/mods/282",
            "mo2_download_url": "https://onedrive.live.com/?redeem=aHR0cHM6Ly8xZHJ2Lm1zL3UvYy8zNzEyNzJjNDlhMzdjYzRhL0VkR21OTHFrNDNoQmxfX3BEZ2dXb0NjQlJUOFQxTl9oZC1vM0hrZFdBRHFQdEE&cid=371272C49A37CC4A&id=371272C49A37CC4A%21sba34a6d1e3a4417897ffe90e0816a027&parId=371272C49A37CC4A%21148600&o=OneUp"
        },
        {
            "name": "Morrowind",
            "prefix_path": os.path.join(steam_compat, utils.get_steam_id("Morrowind"), pfx_path),
            "data_path": os.path.join(steam_common, "Morrowind/Data Files"),
            "plugins_path": os.path.join(steam_compat, utils.get_steam_id("Morrowind"), pfx_path, "Morrowind"),
            "default_plugins_path": os.path.join(steam_compat, utils.get_steam_id("Morrowind"), pfx_path, "Morrowind"),
            "launcher_name": "Morrowind Launcher.exe",
            "launcher_location": os.path.join(steam_common, "Morrowind"),
            "game_root": os.path.join(steam_common, "Morrowind"),
            "data_subpath": "Data Files",
            "script_extender_name": "MWSE-Update.exe",
            "script_extender_download": "https://www.nexusmods.com/morrowind/mods/45468",
            "mge_xe_download": "https://www.nexusmods.com/morrowind/mods/41102",
            "code_patch_download": "https://www.nexusmods.com/morrowind/mods/19510"
        }
    ]}
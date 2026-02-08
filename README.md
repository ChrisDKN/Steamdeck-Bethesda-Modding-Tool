# Bethesda Game Modding on the Steam Deck

This tool allows you to easily set up and run **Mod Organiser 2** to manage your mods and plugins on the Steam Deck.

### Key Features

- **Automatic Data folder building** via hard linking all required files set by `modlist.txt`. This bypasses Mod Organiser's virtual file system, which is very slow on the Steam Deck. Boot times are much faster with larger mod lists, and you don't need to load MO2 every time you launch the game. You only need to rebuild the Data folder when you make a change within Mod Organiser (takes only a few seconds).
- **Script Extender integration** — replaces the default launcher exe with the script extender exe, so hitting Play in Steam/Gaming Mode launches the game with script extender automatically without having to open Mod Organiser every time

---

## Supported Games

- Skyrim Special Edition
- Skyrim
- Fallout 4
- Fallout 3
- Fallout New Vegas
- Oblivion

---

## Not Currently Supported

- Morrowind - Needs testing
- Oblivion Remastered - Needs testing
- Any other game that Mod organiser supports - Might add support in the future

---

## Usage

1. **Download the AppImage** from releases. Make sure it is executable by right-clicking > *Properties* > *Permissions* > tick *Allow executing file as program*.

2. **Install the game** and run it once before proceeding to allow it to generate the files it needs. You can exit at the title screen.

   > **Note:** If running Fallout 3, you will need to downgrade the game first before proceeding (see [Downgrading Fallout 3](#downgrading-fallout-3) below).

3. **Add an instance** in the application and select where you want the folder to go. It will create a folder within that location — this is where your Mod Organiser 2 and mods are stored.

4. **Install Script Extender** (optional) — there is an option to download the script extender version for the selected game, then install it using the app.

5. **Run MO2** — select the instance in the application and click *Run MO2*. MO2 will run using the same Proton version and prefix the game uses. Add and manage your mods and plugins as you normally would.

   > We do **not** run the game via Mod Organiser 2 anymore — it is only used to manage mods. If using mods like Pandora Behaviour Engine or BethINI, you would still add and run those via MO2 as usual.

6. **Build Data Folder** — click *Build Data Folder* in the application. This will:
   - Create a `DataFolder` mod at the bottom of your load order that moves current files from the game's Data folder into MO2's mods folder (needed for a clean build).
   - Read `modlist.txt` and hard link all needed files to the game's Data folder.
   - Copy (not hard link) the `Shadercache` folder if using Community Shaders for Skyrim, since it writes new shaders to the Data folder.
   - Back up the game's default launcher and replace it with the script extender exe (if it exists).
   - Symlink `plugins.txt` to the correct location within the prefix used by the game.

7. **Play the game** through Steam/Gaming Mode as normal. Since we are not using MO2's virtual file system, the game should boot and load much faster (especially noticeable with larger mod lists).

8. **Restore Data Folder** — click *Restore Data Folder* to undo the build and restore the game back to normal. Installing or uninstalling script extender via the application will also trigger this.

> **Repeat for other games** — create a new instance for each game. The application auto-detects games installed in the Steam common folder as well as games on SD cards. See [Custom Locations](#custom-locations) if your game is installed elsewhere.

---

## When You Add/Remove/Change a Mod

Whenever you make a change within Mod Organiser, you need to click **Build Data Folder** again.

---

## Adding Wine DLL Overrides

Some mods may require Wine DLL overrides to function (rare but possible). Instead of using the `WINEDLLOVERRIDES` launch argument in Steam, the app provides a **Run Winecfg** button:

1. Click *Run Winecfg*.
2. Go to the **Libraries** tab.
3. Add an override and set it to native/builtin/both (most DLL overrides use *both*).

This removes the need for a Steam launch argument — the game will launch with the DLL override applied.

---

## Installing Windows Dependencies

You can run **Protontricks** or directly run an `.exe` if a mod requires a Windows dependency that is not already in the prefix.

---

## Downgrading Fallout 3

Fallout 3 must be downgraded to use the latest version of script extender.

1. Select the Fallout 3 instance — a **Downgrade** button will appear in the application.
2. It will provide a link to the patcher on Nexus Mods.
3. Download the patcher, then select the downloaded `.zip` file in the application.
4. The app will auto-extract it to the game directory and run the exe. Patching should only take a couple of seconds.

---

## Custom Locations

If the game is not in the default Steam common folder or on an SD card:

1. **Add an instance** and select *Custom Location*.
2. Find and select the game folder — the app should auto-detect what game it is.
3. When asked if you want to use a custom prefix location, select **Yes**.
4. Locate the Wine prefix used by the game (the folder containing the `pfx` folder).

> The config in `~/.config/MO2Manager/` will update with the custom locations. If you need to move anything, you can edit this file or create a new instance.

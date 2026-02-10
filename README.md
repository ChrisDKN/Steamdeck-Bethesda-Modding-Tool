# Bethesda Game Modding on the Steam Deck

This tool allows you to easily set up and run **Mod Organiser 2** to manage your mods and plugins on the Steam Deck. 

I was originally frustrated with how slow a heavily modded Skyrim loads on the Steam Deck and discovered the reason is Mod organiser's virtual file system doesn't play nicely with the kernal and/or proton

The solution is to make our own Virtual file system by using the modlist.txt that Mo2 creates and hard linking the required files to the Data directory. The hardlinked files take up no space and also load much faster than the files created by Mod organisers VFS.

### Key Features
- **Easy Mod Organiser 2 Install** One click Mo2 install. Each game gets it's own instance. You can easily run Mod organiser through this application. No messing about adding Mo2 to steam or creating a new prefix for it. Just click run Mo2 and it will use the prefix and proton version the game you have selected uses to run it. 
- **Faster game load times** via hard linking all required files set by `modlist.txt`. This bypasses Mod Organiser's virtual file system, which is very slow on the Steam Deck. Boot times are much faster with larger mod lists, and you don't need to load MO2 every time you launch the game. You only need to rebuild the Data folder when you make a change within Mod Organiser (takes only a few seconds).
- **Script Extender integration** — replaces the default launcher exe with the script extender exe, so hitting Play in Steam/Gaming Mode launches the game with script extender automatically without having to open Mod Organiser every time or adding the script extender exe as a separate game.

---

## Supported Games

- Skyrim Special Edition
- Skyrim
- Fallout 4
- [Fallout London*](#Fallout-London)
- Fallout 3
- Fallout 3 Goty Edition
- Fallout New Vegas
- Oblivion
- Oblivion Remastered - **Needs testing**

---

## Not Currently Supported

- Morrowind - Added but broken
- Any other game that Mod organiser supports - Might add support in the future

---

## Usage

1. **Download the AppImage** from releases. Make sure it is executable by right-clicking > *Properties* > *Permissions* > tick *Allow executing file as program*. Alternatively you can download the repo and use run_gui.sh

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

Whenever you make a change within Mod Organiser, you need to click **Build Data Folder** again to see any changes in game.

---

## Adding Wine DLL Overrides

Some mods may require Wine DLL overrides to function (rare but possible). Instead of using the `WINEDLLOVERRIDES` launch argument in Steam, the app provides a **Run Winecfg** button:

1. Click *Run Winecfg*.
2. Go to the **Libraries** tab.
3. Add an override and set it to native/builtin/both (most DLL overrides use *both*).

This removes the need for a Steam launch argument — the game will launch with the DLL override applied. You can still use the steam launch argument if you prefer.

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

If the game is not in the default Steam common folder or on an SD card or if you are not using SteamOS:

1. **Add an instance** and select *Custom Location*.
2. Find and select the game folder — the app should auto-detect what game it is.
3. When asked if you want to use a custom prefix location, select **Yes**.
4. Locate the Wine prefix used by the game (the folder containing the `pfx` folder).

> The config in `~/.config/MO2Manager/` will update with the custom locations. If you need to move anything, you can edit this file or create a new instance.

---

## Fallout London

The application supports Fallout London but does not install it. I will explain the basics of installing Fallout London first in such a way that we can also still play Fallout 4 along side it. It's a bit of a manual process but it's not too bad.

1. Create a folder in "/home/deck/.local/share/Steam/steamapps/common/" called Fallout London
2. Open the Steam client Console by entering steam://open/console in your web browser (in the url bar)
3. In the steam client you will see a console tab (where store,library,community are)
4. You need to enter these **1 at a time** you **can't** paste them all at the same time but you don't have to wait for one to finish before entering the other.
   > There will be no progress bar, but will download about 40gb of Data
   > We are doing this because this is the version Fallout London requires to work
   > download_depot 377160 377161 7497069378349273908
   > download_depot 377160 377163 5819088023757897745
   > download_depot 377160 377162 5847529232406005096
   > download_depot 377160 377164 2178106366609958945
   > download_depot 377160 435870 1691678129192680960
   > download_depot 377160 435871 5106118861901111234
   > download_depot 377160 435880 1255562923187931216
   > download_depot 377160 435881 1207717296920736193
   > download_depot 377160 435882 8482181819175811242
   > download_depot 377160 480630 5527412439359349504
   > download_depot 377160 480631 6588493486198824788
   > download_depot 377160 393885 5000262035721758737
   > download_depot 377160 490650 4873048792354485093
   > download_depot 377160 393895 7677765994120765493
5. The files will be sent to "/home/deck/.local/share/Steam/ubuntu12_32/steamapps/content/app_377160/"
6. Make sure they are all fully downloaded before proceeding,
7. Move the contents of each folder to the Fallout London folder we made earlier. There should be 14 in total
8. Right click the Fallout4Launcher.exe in the Fallout London folder and add to steam
9. in steam, search for the Fallout4Launcher.exe we just added and right click > properties
   > Rename it to Fallout London
   > add this launch option STEAM_COMPAT_DATA_PATH="/home/deck/.local/share/Steam/steamapps/compatdata/folon" %command%
   > In the compatibility tab set it to proton 10
   > Go to "/home/deck/.local/share/Steam/steamapps/compatdata/"
   > Create an empty folder called folon
   > Our launch exe and prefix should now be separate from the main Fallout 4 folder and we can use this to launch Fallout london
10. Run the unmodded game once to allow the prefix to build and for the files/registry to be generated
11. You will need to download the Fallout London files using the heroic launcher.
   > You will need a gog account as well as heroic launcher from the discover store,
   > Redeem Fallout London while logged in to your gog account
   > Log into your gog account on the heroic launcher
   > download Fallout London
12. Move the files from the heroic download location to the Fallout London folder we made earlier
   > Mine were in /home/deck/Games/Heroic/ but yours may be different
13. You can now add a Fallout London instance in the application
   > Run Mo2 once > refresh the UI and build data folder (Double check the output locations are correct)
14. Launch Fallout London via the non steam game we made earlier


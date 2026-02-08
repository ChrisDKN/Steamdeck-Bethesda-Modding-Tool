#!/usr/bin/env python3
"""
Data Folder Builder for Mod Organizer style mod lists.

Workflow:
1. Read modlist.txt from BOTTOM to TOP
2. For each enabled mod (+), scan all files and collect all folder name variants
3. For conflicting folder names (e.g., SKSE vs skse), pick the one with most uppercase letters
4. Keep FILENAMES with original case (some mods require specific casing)
5. If a file path already exists in the filemap (from a lower priority mod),
   REPLACE it with the new mod's file (higher priority wins)
6. Process the "overwrite" folder last (highest priority, always wins)
7. Once complete, hardlink all files from their source mods into the data folder
"""

import shutil

import os
import sys
import argparse
from datetime import datetime


def parse_modlist(modlist_path):
    """
    Parse modlist.txt from bottom to top.
    Returns list of enabled mod names (those starting with +).
    Order: bottom mod first, top mod last (so top mod wins on conflicts)
    """
    if not os.path.exists(modlist_path):
        print(f"Error: modlist.txt not found at: {modlist_path}")
        sys.exit(1)

    with open(modlist_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Reverse to process bottom to top
    lines = list(reversed(lines))

    enabled_mods = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith('-'):
            # Disabled mod, skip
            continue
        if line.startswith('+'):
            # Enabled mod, extract name (remove the + prefix)
            mod_name = line[1:].strip()
            enabled_mods.append(mod_name)

    return enabled_mods


def count_uppercase(s):
    """Count the number of uppercase letters in a string."""
    return sum(1 for c in s if c.isupper())


def format_size(size_bytes):
    """Format a size in bytes to a human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def get_match_key(original_path):
    """
    Get the key used for matching/deduplication.
    This is fully lowercase for case-insensitive matching.
    """
    return original_path.lower()


def scan_mod_files(mod_path):
    """
    Recursively scan a mod folder and return all files.
    Returns list of tuples: (original_relative_path, match_key)
    - original_relative_path: the path as it exists in the mod
    - match_key: fully lowercase (for deduplication matching)
    """
    files = []

    if not os.path.exists(mod_path):
        return files

    for root, dirs, filenames in os.walk(mod_path):
        rel_root = os.path.relpath(root, mod_path)
        if rel_root == '.':
            rel_root = ''

        for filename in filenames:
            if rel_root:
                original_path = os.path.join(rel_root, filename)
            else:
                original_path = filename

            # Match key: fully lowercase for deduplication
            match_key = get_match_key(original_path)

            files.append((original_path, match_key))

    return files


def scan_folder_for_variants(folder_path, folder_variants):
    """
    Scan a single folder and add its folder name variants to the dict.
    """
    if not os.path.exists(folder_path):
        return

    for root, dirs, filenames in os.walk(folder_path):
        rel_root = os.path.relpath(root, folder_path)

        # Add each directory we encounter
        for d in dirs:
            lowercase_d = d.lower()
            if lowercase_d not in folder_variants:
                folder_variants[lowercase_d] = set()
            folder_variants[lowercase_d].add(d)

        # Also track the path components from rel_root
        if rel_root != '.':
            for part in rel_root.split(os.sep):
                lowercase_part = part.lower()
                if lowercase_part not in folder_variants:
                    folder_variants[lowercase_part] = set()
                folder_variants[lowercase_part].add(part)


def collect_all_folders(modlist_path, mods_folder, overwrite_folder=None):
    """
    Scan all enabled mods and collect all folder name variants.
    Returns a dict: lowercase_folder -> set of original folder names seen
    """
    enabled_mods = parse_modlist(modlist_path)
    folder_variants = {}  # lowercase -> set of original names

    for mod_name in enabled_mods:
        mod_path = os.path.join(mods_folder, mod_name)
        scan_folder_for_variants(mod_path, folder_variants)

    # Also scan overwrite folder if provided
    if overwrite_folder and os.path.exists(overwrite_folder):
        scan_folder_for_variants(overwrite_folder, folder_variants)

    return folder_variants


def build_folder_name_map(folder_variants):
    """
    Build a mapping from lowercase folder name to the "best" variant.
    Best = the one with the most uppercase letters.
    If no conflict (only one variant), use that variant unchanged.
    """
    folder_map = {}  # lowercase -> best variant

    for lowercase_name, variants in folder_variants.items():
        if len(variants) == 1:
            # No conflict, use the original
            folder_map[lowercase_name] = next(iter(variants))
        else:
            # Conflict! Pick the one with most uppercase letters
            best = max(variants, key=lambda v: (count_uppercase(v), v))
            folder_map[lowercase_name] = best

    return folder_map


def normalize_path_with_map(original_path, folder_map):
    """
    Normalize a path using the folder name map.
    Folders are replaced with their "best" variant from folder_map.
    Filename is preserved as-is.
    """
    parts = original_path.split(os.sep)
    if len(parts) > 1:
        # Map folder parts to their best variants
        folders = []
        for p in parts[:-1]:
            lowercase_p = p.lower()
            if lowercase_p in folder_map:
                folders.append(folder_map[lowercase_p])
            else:
                folders.append(p)  # fallback to original
        filename = parts[-1]
        return os.path.join(*folders, filename)
    else:
        # No folders, just a filename - keep as-is
        return original_path


def sync_shadercache(source_data_folder, overwrite_folder):
    """
    Sync ShaderCache from the game's Data folder to the overwrite folder.
    This preserves shader cache changes made by the game between builds.

    - Only syncs if ShaderCache exists in the Data folder
    - If ShaderCache exists only in overwrite (not Data), it is preserved
    - Copies ShaderCache from source Data folder to overwrite folder

    Returns True if ShaderCache was synced, False otherwise.
    """
    if not overwrite_folder:
        return False

    source_shadercache = os.path.join(source_data_folder, "ShaderCache")
    dest_shadercache = os.path.join(overwrite_folder, "ShaderCache")

    # Check if source ShaderCache exists in Data folder
    if not os.path.exists(source_shadercache) or not os.path.isdir(source_shadercache):
        # No ShaderCache in Data folder - preserve any existing one in overwrite
        if os.path.exists(dest_shadercache):
            print(f"  No ShaderCache in Data folder, preserving existing overwrite ShaderCache")
        else:
            print(f"  No ShaderCache found in either location")
        return False

    print(f"  Source: {source_shadercache}")
    print(f"  Destination: {dest_shadercache}")

    # Delete existing ShaderCache in overwrite if it exists (will be replaced with Data's version)
    if os.path.exists(dest_shadercache):
        if os.path.islink(dest_shadercache):
            print("  Removing existing symlink in overwrite...")
            os.remove(dest_shadercache)
        else:
            print("  Removing existing ShaderCache in overwrite...")
            shutil.rmtree(dest_shadercache)

    # Copy ShaderCache from source to overwrite
    print("  Copying ShaderCache to overwrite folder...")
    shutil.copytree(source_shadercache, dest_shadercache)

    # Count files copied
    file_count = sum(len(files) for _, _, files in os.walk(dest_shadercache))
    print(f"  Copied {file_count} files")

    return True


def build_data_folder(modlist_path, mods_folder, output_dir, overwrite_folder=None, filemap_output=None):
    """
    Build the data folder with hardlinked files.
    """
    print("=" * 70)
    print("DATA FOLDER BUILDER")
    print("=" * 70)
    print(f"Modlist:     {modlist_path}")
    print(f"Mods folder: {mods_folder}")
    print(f"Overwrite:   {overwrite_folder if overwrite_folder else 'Not specified'}")
    print(f"Output:      {output_dir}")
    print("=" * 70)
    print()

    # Step 1: Parse modlist (bottom to top order)
    print("Step 1: Reading modlist.txt (bottom to top)...")
    enabled_mods = parse_modlist(modlist_path)
    print(f"  Found {len(enabled_mods)} enabled mods")
    print(f"  First mod (lowest priority): {enabled_mods[0] if enabled_mods else 'None'}")
    print(f"  Last mod (highest priority): {enabled_mods[-1] if enabled_mods else 'None'}")
    print()

    # Step 2: Collect all folder name variants and build the folder name map
    print("Step 2: Analyzing folder names across all mods...")
    folder_variants = collect_all_folders(modlist_path, mods_folder, overwrite_folder)
    folder_map = build_folder_name_map(folder_variants)

    # Count conflicts
    conflicts = [(k, v) for k, v in folder_variants.items() if len(v) > 1]
    print(f"  Total unique folders: {len(folder_map)}")
    print(f"  Folder name conflicts resolved: {len(conflicts)}")
    if conflicts:
        print("  Conflicts (showing first 10):")
        for lowercase_name, variants in conflicts[:10]:
            winner = folder_map[lowercase_name]
            print(f"    {lowercase_name}: {variants} -> '{winner}'")
        if len(conflicts) > 10:
            print(f"    ... and {len(conflicts) - 10} more")
    print()

    # Step 3: Build filemap
    # Key: match_key (fully lowercase for case-insensitive matching)
    # Value: (mod_name, original_path_in_mod, normalized_dest_path, full_source_path)
    print("Step 3: Building filemap...")
    print("  (Conflicting folders use most-uppercase variant, filenames preserve original case)")
    filemap = {}
    overrides = 0
    size_overridden = 0  # Total size of files that were overridden (not used)

    for i, mod_name in enumerate(enabled_mods):
        mod_path = os.path.join(mods_folder, mod_name)

        if not os.path.exists(mod_path):
            print(f"  WARNING: Mod folder not found: {mod_name}")
            continue

        files = scan_mod_files(mod_path)
        mod_overrides = 0

        for original_path, match_key in files:
            full_source = os.path.join(mod_path, original_path)

            # Normalize path using the folder map
            normalized_path = normalize_path_with_map(original_path, folder_map)

            # Check if this path already exists (from lower priority mod)
            if match_key in filemap:
                # The existing file in filemap is being overridden - track its size
                old_mod, old_path, old_norm, old_source = filemap[match_key]
                try:
                    old_size = os.path.getsize(old_source) if os.path.exists(old_source) else 0
                except OSError:
                    old_size = 0
                size_overridden += old_size
                mod_overrides += 1
                overrides += 1

            # Add/replace in filemap (higher priority mod always wins)
            filemap[match_key] = (mod_name, original_path, normalized_path, full_source)

        # Progress
        if (i + 1) % 50 == 0:
            print(f"  Processed {i + 1}/{len(enabled_mods)} mods...")

    print(f"  Total files in filemap: {len(filemap)}")
    print(f"  Total overrides (files replaced by higher priority): {overrides}")
    print(f"  Size of overridden files (unused): {format_size(size_overridden)}")
    print()

    # Step 4: Process overwrite folder (highest priority)
    # Note: ShaderCache files are excluded here - they will be copied separately
    overwrite_count = 0
    overwrite_overrides = 0
    shadercache_skipped = 0
    size_overridden_by_overwrite = 0  # Size of files overridden by overwrite folder
    if overwrite_folder and os.path.exists(overwrite_folder):
        print("Step 4: Processing overwrite folder (highest priority)...")
        overwrite_files = scan_mod_files(overwrite_folder)

        for original_path, match_key in overwrite_files:
            # Skip files inside ShaderCache folder - they will be copied separately
            path_parts = original_path.split(os.sep)
            if path_parts and path_parts[0].lower() == "shadercache":
                shadercache_skipped += 1
                continue

            full_source = os.path.join(overwrite_folder, original_path)
            normalized_path = normalize_path_with_map(original_path, folder_map)

            if match_key in filemap:
                # Track size of file being overridden by overwrite
                old_mod, old_path, old_norm, old_source = filemap[match_key]
                try:
                    old_size = os.path.getsize(old_source) if os.path.exists(old_source) else 0
                except OSError:
                    old_size = 0
                size_overridden_by_overwrite += old_size
                size_overridden += old_size  # Add to total overridden
                overwrite_overrides += 1

            filemap[match_key] = ("[OVERWRITE]", original_path, normalized_path, full_source)
            overwrite_count += 1

        print(f"  Files from overwrite: {overwrite_count}")
        print(f"  Files overridden by overwrite: {overwrite_overrides}")
        print(f"  Size of files overridden by overwrite: {format_size(size_overridden_by_overwrite)}")
        if shadercache_skipped > 0:
            print(f"  ShaderCache files skipped (will be copied separately): {shadercache_skipped}")
        print()
    else:
        size_overridden_by_overwrite = 0
        if overwrite_folder:
            print("Step 4: Overwrite folder not found, skipping...")
        else:
            print("Step 4: No overwrite folder specified, skipping...")
        print()

    # Step 5: Save filemap to file (optional)
    if filemap_output:
        print(f"Step 4: Saving filemap to {filemap_output}...")
        with open(filemap_output, 'w', encoding='utf-8') as f:
            f.write("=" * 100 + "\n")
            f.write("FILEMAP - Files to be hardlinked into data folder\n")
            f.write("=" * 100 + "\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Modlist: {modlist_path}\n")
            f.write(f"Mods folder: {mods_folder}\n")
            f.write(f"Total enabled mods: {len(enabled_mods)}\n")
            f.write(f"Overwrite folder: {overwrite_folder if overwrite_folder else 'Not specified'}\n")
            f.write(f"Total files: {len(filemap)}\n")
            f.write(f"Total overrides: {overrides}\n")
            f.write(f"Overwrite files: {overwrite_count}\n")
            f.write(f"Folder name conflicts: {len(conflicts)}\n")
            f.write("NOTE: Conflicting folders use most-uppercase variant, filenames preserve original case\n")
            f.write("=" * 100 + "\n\n")
            f.write("Format: [destination_path] <- [source_mod]/[original_path]\n")
            f.write("-" * 100 + "\n\n")

            for match_key in sorted(filemap.keys()):
                mod_name, original_path, normalized_path, full_source = filemap[match_key]
                f.write(f"{normalized_path} <- {mod_name}/{original_path}\n")

            f.write("\n" + "=" * 100 + "\n")
            f.write("END OF FILEMAP\n")
            f.write("=" * 100 + "\n")
        print(f"  Filemap saved.")
        print()

    # Step 6: Create output directory
    print(f"Step 6: Preparing output directory...")
    if os.path.exists(output_dir):
        print(f"  Output directory exists: {output_dir}")
        print(f"  Existing files will be overwritten if they conflict.")
    else:
        os.makedirs(output_dir)
        print(f"  Created: {output_dir}")
    print()

    # Step 7: Create hardlinks
    print("Step 7: Creating hardlinks...")
    created = 0
    failed = 0
    failed_files = []
    total = len(filemap)

    # Track file sizes
    size_linked = 0  # Total size of successfully linked files
    size_failed = 0  # Total size of failed files

    for i, (match_key, (mod_name, original_path, normalized_path, full_source)) in enumerate(filemap.items()):
        # Destination: output_dir + normalized_path (lowercase folders, original filename)
        dest_file = os.path.join(output_dir, normalized_path)

        # Create directory structure
        dest_dir = os.path.dirname(dest_file)
        if dest_dir and not os.path.exists(dest_dir):
            os.makedirs(dest_dir)

        # Get file size before attempting link
        try:
            file_size = os.path.getsize(full_source) if os.path.exists(full_source) else 0
        except OSError:
            file_size = 0

        # Create hardlink
        try:
            # Remove existing file if present
            if os.path.exists(dest_file):
                os.remove(dest_file)

            # Verify source exists
            if not os.path.exists(full_source):
                raise FileNotFoundError(f"Source file not found: {full_source}")

            os.link(full_source, dest_file)
            created += 1
            size_linked += file_size

        except Exception as e:
            failed += 1
            size_failed += file_size
            failed_files.append((full_source, dest_file, str(e), file_size))

        # Progress
        if (i + 1) % 5000 == 0 or (i + 1) == total:
            pct = (i + 1) * 100 // total
            print(f"  Progress: {i + 1}/{total} ({pct}%) - Created: {created}, Failed: {failed}")

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total files in filemap: {total}")
    print(f"Hardlinks created:      {created}")
    print(f"Failed:                 {failed}")
    print(f"Files overridden:       {overrides}")
    print(f"Data folder:            {output_dir}")
    print()
    print(f"Size of files linked to Data:     {format_size(size_linked)} ({size_linked:,} bytes)")
    print(f"Size of overridden files (unused): {format_size(size_overridden)} ({size_overridden:,} bytes)")
    if size_failed > 0:
        print(f"Size of failed files:              {format_size(size_failed)} ({size_failed:,} bytes)")

    # Handle failures
    if failed_files:
        print()
        print("FAILURES (first 10):")
        for source, dest, error, fsize in failed_files[:10]:
            print(f"  Source: {source}")
            print(f"  Dest:   {dest}")
            print(f"  Size:   {format_size(fsize)}")
            print(f"  Error:  {error}")
            print()

        if len(failed_files) > 10:
            print(f"  ... and {len(failed_files) - 10} more failures")

    # Print build log to stdout (captured by GUI)
    print()
    print("=" * 80)
    print("DATA FOLDER BUILD LOG")
    print("=" * 80)
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Modlist: {modlist_path}")
    print(f"Mods folder: {mods_folder}")
    print(f"Overwrite folder: {overwrite_folder if overwrite_folder else 'Not specified'}")
    print(f"Output folder: {output_dir}")
    print()
    print("-" * 80)
    print("FILE STATISTICS")
    print("-" * 80)
    print(f"Total enabled mods: {len(enabled_mods)}")
    print(f"Total files in filemap: {total}")
    print(f"Hardlinks created: {created}")
    print(f"Failed: {failed}")
    print(f"Files overridden (not used): {overrides}")
    print(f"Folder name conflicts resolved: {len(conflicts)}")
    print(f"Overwrite files: {overwrite_count}")
    print(f"Overwrite overrides: {overwrite_overrides}")
    print(f"ShaderCache files skipped: {shadercache_skipped}")
    print()
    print("-" * 80)
    print("SIZE STATISTICS")
    print("-" * 80)
    print(f"Total size of files linked to Data folder:  {format_size(size_linked)} ({size_linked:,} bytes)")
    print(f"Total size of overridden files (unused):    {format_size(size_overridden)} ({size_overridden:,} bytes)")
    print(f"Total size of failed files:                 {format_size(size_failed)} ({size_failed:,} bytes)")
    print()
    print("NOTE: 'Overridden files' are files in lower-priority mods that were replaced")
    print("      by higher-priority mods. These files are not used in the game and could")
    print("      potentially be deleted to save disk space.")
    print()

    if failed_files:
        print("-" * 80)
        print("FAILED FILES")
        print("-" * 80)
        for source, dest, error, fsize in failed_files:
            print(f"Source: {source}")
            print(f"Dest:   {dest}")
            print(f"Size:   {format_size(fsize)} ({fsize:,} bytes)")
            print(f"Error:  {error}")
            print("-" * 40)

    print()
    print("=" * 80)
    print("END OF LOG")
    print("=" * 80)


def copy_shadercache_to_data(overwrite_folder, output_dir):
    """
    Copy ShaderCache from overwrite folder to the new Data folder.
    This creates a separate copy so the game can modify it freely.
    """
    if not overwrite_folder:
        return False

    source_shadercache = os.path.join(overwrite_folder, "ShaderCache")
    dest_shadercache = os.path.join(output_dir, "ShaderCache")

    if not os.path.exists(source_shadercache) or not os.path.isdir(source_shadercache):
        print("  No ShaderCache found in overwrite folder")
        return False

    print(f"  Source: {source_shadercache}")
    print(f"  Destination: {dest_shadercache}")

    # Remove existing ShaderCache in Data folder if it exists
    if os.path.exists(dest_shadercache):
        if os.path.islink(dest_shadercache):
            print("  Removing existing symlink...")
            os.remove(dest_shadercache)
        else:
            print("  Removing existing ShaderCache folder...")
            shutil.rmtree(dest_shadercache)

    # Copy ShaderCache to Data folder
    print("  Copying ShaderCache to Data folder...")
    shutil.copytree(source_shadercache, dest_shadercache)

    # Count files copied
    file_count = sum(len(files) for _, _, files in os.walk(dest_shadercache))
    print(f"  Copied {file_count} files")

    return True


def check_file_source(modlist_path, mods_folder, file_to_check):
    """
    Debug function: Check which mod provides a specific file.
    Shows all mods that have this file and which one wins.
    """
    print("=" * 70)
    print("FILE SOURCE CHECK")
    print("=" * 70)
    print(f"Checking: {file_to_check}")
    print(f"Match key (lowercase): {file_to_check.lower()}")
    print()

    # Build folder map first
    print("Building folder name map...")
    folder_variants = collect_all_folders(modlist_path, mods_folder)
    folder_map = build_folder_name_map(folder_variants)
    print(f"  {len(folder_map)} folders mapped")
    print()

    enabled_mods = parse_modlist(modlist_path)
    print(f"Processing {len(enabled_mods)} mods (bottom to top)...")
    print()

    check_key = file_to_check.lower()
    found_in = []

    for i, mod_name in enumerate(enabled_mods):
        mod_path = os.path.join(mods_folder, mod_name)
        if not os.path.exists(mod_path):
            continue

        files = scan_mod_files(mod_path)
        for original_path, match_key in files:
            if match_key == check_key:
                full_path = os.path.join(mod_path, original_path)
                normalized_path = normalize_path_with_map(original_path, folder_map)
                exists = os.path.exists(full_path)
                found_in.append((i, mod_name, original_path, normalized_path, full_path, exists))

    if not found_in:
        print(f"File not found in any enabled mod!")
    else:
        print(f"File found in {len(found_in)} mods:")
        print("-" * 70)
        for idx, mod_name, orig_path, norm_path, full_path, exists in found_in:
            status = "EXISTS" if exists else "MISSING!"
            print(f"  [{idx}] {mod_name}")
            print(f"      Original path: {orig_path}")
            print(f"      Normalized:    {norm_path}")
            print(f"      Full path:     {full_path}")
            print(f"      Status:        {status}")
            print()

        winner = found_in[-1]  # Last one wins (highest in modlist)
        print("=" * 70)
        print(f"WINNER (highest priority): {winner[1]}")
        print(f"  Source:      {winner[4]}")
        print(f"  Dest path:   {winner[3]}")
        print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description='Build a data folder with hardlinked files from mods.'
    )
    parser.add_argument(
        '--modlist', '-m',
        required=True,
        help='Path to modlist.txt file'
    )
    parser.add_argument(
        '--mods', '-d',
        required=True,
        help='Path to the mods folder'
    )
    parser.add_argument(
        '--overwrite', '-w',
        default=None,
        help='Path to the overwrite folder (highest priority, processed last)'
    )
    parser.add_argument(
        '--output', '-o',
        default=None,
        help='Output directory for the Data folder (default: ./Data in script directory)'
    )
    parser.add_argument(
        '--filemap', '-f',
        default=None,
        help='Optional: Save filemap to this file'
    )
    parser.add_argument(
        '--check', '-c',
        default=None,
        help='Check which mod provides a specific file (e.g., --check "meshes/actors/character/skeleton.nif")'
    )
    parser.add_argument(
        '--yes', '-y',
        action='store_true',
        help='Automatically answer yes to prompts (e.g., deleting existing Data folder)'
    )
    parser.add_argument(
        '--plugins-dest', '-p',
        default=None,
        help='Destination folder for plugins.txt symlink (default: Skyrim SSE AppData in Wine prefix)'
    )
    parser.add_argument(
        '--no-plugins',
        action='store_true',
        help='Skip plugins.txt symlinking'
    )

    args = parser.parse_args()

    # Default output to script directory + /Data
    if args.output is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        args.output = os.path.join(script_dir, 'Data')
    else:
        # If user specified a path, ensure it ends with 'Data'
        # This prevents accidentally deleting the wrong folder
        output_basename = os.path.basename(args.output.rstrip(os.sep))
        if output_basename.lower() != 'data':
            # User specified a parent folder, append 'Data' to it
            args.output = os.path.join(args.output, 'Data')
            print(f"Note: Output path adjusted to: {args.output}")

    # Check mode - just show which mod provides a file
    if args.check:
        check_file_source(args.modlist, args.mods, args.check)
        return

    # Safety check: ensure we're only deleting a 'Data' folder
    output_basename = os.path.basename(args.output.rstrip(os.sep))
    if output_basename.lower() != 'data':
        print(f"ERROR: Output folder must be named 'Data', got: {output_basename}")
        print("This is a safety check to prevent accidentally deleting important folders.")
        sys.exit(1)

    # Step 0: Sync ShaderCache from existing Data folder to overwrite folder
    # This preserves any shader cache changes made by the game before we delete the Data folder
    if args.overwrite and os.path.exists(args.output):
        print("=" * 70)
        print("SHADERCACHE SYNC (preserving game changes)")
        print("=" * 70)
        if sync_shadercache(args.output, args.overwrite):
            print("ShaderCache synced to overwrite folder!")
        else:
            print("No ShaderCache to sync")
        print("=" * 70)
        print()

    # Check if output directory already exists
    if os.path.exists(args.output):
        print(f"Data folder already exists: {args.output}")
        if args.yes:
            print("--yes flag specified, deleting existing folder...")
            delete = True
        else:
            response = input("Delete existing folder and create new one? (y/N): ").strip().lower()
            delete = response in ('y', 'yes')

        if delete:
            print("Deleting existing Data folder...")
            shutil.rmtree(args.output)
            print("Deleted.")
        else:
            print("Aborted. Existing Data folder was not modified.")
            sys.exit(0)

        print()

    build_data_folder(args.modlist, args.mods, args.output, args.overwrite, args.filemap)

    # Handle ShaderCache folder copying (from overwrite folder to new Data folder)
    if args.overwrite:
        print()
        print("=" * 70)
        print("SHADERCACHE COPY")
        print("=" * 70)
        if copy_shadercache_to_data(args.overwrite, args.output):
            print("ShaderCache copied successfully!")
            print("(Game will create/modify shaders in the Data folder)")
        else:
            print("No ShaderCache to copy")
        print("=" * 70)

    # Handle plugins.txt symlinking
    if not args.no_plugins:
        # plugins.txt is in the same folder as modlist.txt
        modlist_dir = os.path.dirname(args.modlist)
        plugins_source = os.path.join(modlist_dir, 'plugins.txt')

        if not os.path.exists(plugins_source):
            print(f"\nWarning: plugins.txt not found at: {plugins_source}")
            print("Skipping plugins.txt symlinking.")
        else:
            # Default destination for Skyrim SSE in Wine/Proton prefix
            if args.plugins_dest:
                plugins_dest_dir = args.plugins_dest
            else:
                plugins_dest_dir = "/home/deck/.local/share/Steam/steamapps/compatdata/489830/pfx/drive_c/users/steamuser/AppData/Local/Skyrim Special Edition"

            plugins_dest = os.path.join(plugins_dest_dir, 'plugins.txt')

            print()
            print("=" * 70)
            print("PLUGINS.TXT SYMLINK")
            print("=" * 70)
            print(f"Source:      {plugins_source}")
            print(f"Destination: {plugins_dest}")

            # Create destination directory if it doesn't exist
            if not os.path.exists(plugins_dest_dir):
                print(f"Creating destination directory: {plugins_dest_dir}")
                os.makedirs(plugins_dest_dir)

            # Remove existing plugins.txt (file or symlink)
            if os.path.exists(plugins_dest) or os.path.islink(plugins_dest):
                if os.path.islink(plugins_dest):
                    print("Removing existing symlink...")
                else:
                    print("Removing existing plugins.txt...")
                os.remove(plugins_dest)

            # Create symlink
            try:
                os.symlink(plugins_source, plugins_dest)
                print("Symlink created successfully!")
            except OSError as e:
                print(f"ERROR: Failed to create symlink: {e}")

            print("=" * 70)


if __name__ == '__main__':
    main()

# Modul: game_locator.py
# Funktion: Findet die Sims-4-Installation automatisch, egal über welchen Launcher und auf welchem Laufwerk.
#
# Gesucht wird in dieser Reihenfolge:
# 1. Windows-Registry (EA App / Origin tragen den Installationsordner unter "Maxis\The Sims 4" ein,
#    dazu die Einträge unter "Programme deinstallieren")
# 2. Steam: alle Bibliotheksordner aus libraryfolders.vdf
# 3. Epic Games: Manifest-Dateien des Launchers
# 4. Übliche Ordner auf allen Laufwerken (Program Files\EA Games, Origin Games, SteamLibrary, Games, …)
# 5. Gründliche Suche (deep=True): alle Laufwerke bis 3 Ordner tief nach einem Ordner "The Sims 4"
#
# Ein Ordner zählt nur, wenn darin Data\Client liegt – der Benutzerordner unter Dokumente
# (Mods, saves, Tray) heißt genauso, ist aber nicht die Installation.

import os
import re
import glob
import json
import logging

log = logging.getLogger(__name__)

GAME_NAMES = ["The Sims 4", "Die Sims 4", "Les Sims 4", "Los Sims 4", "De Sims 4", "The Sims™ 4", "Sims 4"]
STEAM_APP_ID = "1222670"
COMMON_PARENTS = [
    r"Program Files\EA Games", r"Program Files (x86)\EA Games",
    r"Program Files (x86)\Origin Games", r"Program Files\Origin Games",
    r"Program Files (x86)\Steam\steamapps\common", r"Program Files\Steam\steamapps\common",
    r"Program Files\Epic Games", r"SteamLibrary\steamapps\common", r"Steam\steamapps\common",
    "EA Games", "Origin Games", "Epic Games", "Games", "Spiele", "",
]
SKIP_DIRS = {"windows", "$recycle.bin", "system volume information", "users", "programdata", "recovery",
             "perflogs", "msocache", "config.msi", "documents and settings"}
PACK_PATTERN = re.compile(r"^(EP|GP|SP|FP)\d+$", re.I)

_cache = {}


def is_game_folder(path):
    return bool(path) and os.path.isdir(os.path.join(path, "Data", "Client"))


def pack_count(path):
    """Anzahl installierter Erweiterungen/Packs (Ordner EP01, GP03, SP12, …)."""
    try:
        return sum(1 for name in os.listdir(path) if PACK_PATTERN.match(name))
    except OSError:
        return 0


def _registry_candidates():
    """Installationsordner aus der Registry (nur Windows)."""
    try:
        import winreg
    except ImportError:
        return []
    found = []

    def value(root, key, name, view):
        try:
            with winreg.OpenKey(root, key, 0, winreg.KEY_READ | view) as k:
                return str(winreg.QueryValueEx(k, name)[0])
        except OSError:
            return ""

    views = (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY)
    for view in views:
        path = value(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Maxis\The Sims 4", "Install Dir", view)
        if path:
            found.append((path, "EA App / Origin (Registry)"))
    uninstall = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for view in views:
            try:
                with winreg.OpenKey(root, uninstall, 0, winreg.KEY_READ | view) as parent:
                    for i in range(winreg.QueryInfoKey(parent)[0]):
                        sub = winreg.EnumKey(parent, i)
                        key = uninstall + "\\" + sub
                        name = value(root, key, "DisplayName", view).lower()
                        if sub == f"Steam App {STEAM_APP_ID}" or ("sims" in name and "4" in name):
                            path = value(root, key, "InstallLocation", view)
                            if path:
                                found.append((path, "Windows-Programmliste"))
            except OSError:
                continue
    return found


def _steam_roots():
    roots = []
    try:
        import winreg
        for root, key, name in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
                                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath")):
            try:
                with winreg.OpenKey(root, key) as k:
                    roots.append(str(winreg.QueryValueEx(k, name)[0]))
            except OSError:
                pass
    except ImportError:
        pass
    return roots


def steam_libraries(steam_root):
    """Alle Steam-Bibliotheksordner aus <Steam>/steamapps/libraryfolders.vdf."""
    libs = [steam_root]
    try:
        with open(os.path.join(steam_root, "steamapps", "libraryfolders.vdf"), encoding="utf-8",
                  errors="replace") as f:
            for match in re.finditer(r'"path"\s+"([^"]+)"', f.read()):
                libs.append(match.group(1).replace("\\\\", "\\"))
    except OSError:
        pass
    return libs


def _steam_candidates(roots=None):
    found = []
    for root in roots if roots is not None else _steam_roots():
        for lib in steam_libraries(root):
            common = os.path.join(lib, "steamapps", "common")
            for name in GAME_NAMES:
                found.append((os.path.join(common, name), "Steam"))
    return found


def _epic_candidates(manifest_dir=None):
    manifest_dir = manifest_dir or os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"),
                                                "Epic", "EpicGamesLauncher", "Data", "Manifests")
    found = []
    for path in glob.glob(os.path.join(manifest_dir, "*.item")):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        name = str(data.get("DisplayName", "")).lower()
        if "sims" in name and "4" in name and data.get("InstallLocation"):
            found.append((data["InstallLocation"], "Epic Games"))
    return found


def _drive_roots():
    if os.name != "nt":
        return []
    from cc_finder import list_drives
    return list_drives(include_system=True)


def _common_candidates(roots):
    found = []
    for root in roots:
        for parent in COMMON_PARENTS:
            for name in GAME_NAMES:
                found.append((os.path.join(root, *parent.split("\\"), name), "üblicher Installationsordner"))
    return found


def _deep_candidates(roots, max_depth=3, should_stop=None):
    """Sucht auf den Laufwerken bis max_depth Ordner tief nach einem Ordner mit einem der Spielnamen."""
    names = {n.lower() for n in GAME_NAMES}
    found = []
    for root in roots:
        level = [root]
        for _depth in range(max_depth):
            next_level = []
            for folder in level:
                if should_stop and should_stop():
                    return found
                try:
                    with os.scandir(folder) as it:
                        for entry in it:
                            try:
                                if not entry.is_dir(follow_symlinks=False):
                                    continue
                            except OSError:
                                continue
                            low = entry.name.lower()
                            if low in names:
                                found.append((entry.path, "Laufwerkssuche"))
                            elif low not in SKIP_DIRS and not low.startswith((".", "$")):
                                next_level.append(entry.path)
                except OSError:
                    continue
            level = next_level
    return found


def find_game_folders(deep=False, roots=None, should_stop=None, extra=()):
    """Alle gefundenen Sims-4-Installationen: [{"pfad", "quelle", "packs"}], beste zuerst.
    deep=True durchsucht zusätzlich alle Laufwerke (dauert ein paar Sekunden).
    roots: Laufwerke/Ordner für die Suche (Standard: alle lokalen Laufwerke)."""
    key = (deep, tuple(roots) if roots is not None else None)
    if not extra and key in _cache:
        return _cache[key]
    drive_roots = list(roots) if roots is not None else _drive_roots()
    candidates = [(p, "Einstellungen") for p in extra if p]
    if roots is None:
        candidates += _registry_candidates() + _steam_candidates() + _epic_candidates()
    candidates += _common_candidates(drive_roots)
    if deep:
        candidates += _deep_candidates(drive_roots, should_stop=should_stop)

    result, seen = [], set()
    for path, source in candidates:
        path = os.path.normpath(path)
        norm = os.path.normcase(path)
        if norm in seen or not is_game_folder(path):
            continue
        seen.add(norm)
        result.append({"pfad": path, "quelle": source, "packs": pack_count(path)})
    if not extra and not (should_stop and should_stop()):
        _cache[key] = result
    return result


def find_game_folder():
    """Schnelle Erkennung (ohne Laufwerkssuche): der beste Treffer oder ""."""
    try:
        found = find_game_folders(deep=False)
    except Exception as e:      # Erkennung darf den Programmstart nie verhindern
        log.warning("Spielordner-Erkennung fehlgeschlagen: %s", e)
        return ""
    return found[0]["pfad"] if found else ""


def describe(candidate):
    packs = f", {candidate['packs']} Packs" if candidate.get("packs") else ""
    return f"{candidate['pfad']}   ({candidate['quelle']}{packs})"

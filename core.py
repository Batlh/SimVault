# Modul: core.py
# Funktion: Gemeinsame Abläufe für Programmfenster (gui/) und Kommandozeile – ohne Ausgaben,
#           mit Fortschritts-Rückmeldung und Abbruchmöglichkeit.

import os
import sys
import glob
import json
import tempfile

import config as cfg_mod

DEFAULT_CONFIG_NAME = "config.json"


def user_data_dir():
    """Benutzerordner für Einstellungen, Berichte und Backups des Programms."""
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "SimVault")
    return os.path.join(os.path.expanduser("~"), ".config", "simvault")


def default_config_path():
    """config.json neben dem Programm (portabel), sonst im Benutzerordner."""
    if getattr(sys, "frozen", False):
        here = os.path.dirname(sys.executable)
    else:
        here = os.path.dirname(os.path.abspath(__file__))
    portable = os.path.join(here, DEFAULT_CONFIG_NAME)
    if os.path.exists(portable) or not getattr(sys, "frozen", False):
        return portable
    return os.path.join(user_data_dir(), DEFAULT_CONFIG_NAME)


def load(config_path=None):
    """Lädt die Konfiguration, ergänzt Pfade und macht relative Ordner relativ zur config.json."""
    config_path = os.path.abspath(config_path or default_config_path())
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    raw = cfg_mod.load_config(config_path)
    cfg = cfg_mod.resolve_paths(raw)
    base = os.path.dirname(config_path)
    for key in ("backup_folder", "report_folder", "temp_folder"):
        value = cfg.get(key)
        if value and not os.path.isabs(value):
            cfg[key] = os.path.normpath(os.path.join(base, value))
    sqlite = cfg.get("database", {}).get("sqlite_path")
    if sqlite and not os.path.isabs(sqlite):
        cfg["database"]["sqlite_path"] = os.path.join(base, sqlite)
    cfg["_config_path"] = config_path
    return raw, cfg


def save(raw, config_path):
    cfg_mod.save_config({k: v for k, v in raw.items() if not k.startswith("_")}, config_path)


def analyze(cfg, all_saves=True, tray=True, missing=True, progress=None):
    """Scannt Mods, gleicht mit Spielständen/Bibliothek ab und sucht fehlende CC."""
    from mod_folder_scanner import scan_mods_folder
    from savegame_analyzer import find_saves, analyze_usage
    say = progress or (lambda _m: None)
    say("Scanne Mods-Ordner …")
    mod_scan = scan_mods_folder(cfg["mods_folder"], progress=lambda i, n: say(f"Mods: {i}/{n}"))
    saves = find_saves(cfg["savegames_folder"])
    if not all_saves:
        saves = saves[:1]
    tray_folder = cfg.get("tray_folder") if tray else None
    id_usage = {}
    usage = analyze_usage(mod_scan, saves, tray_folder=tray_folder, progress=say, id_usage=id_usage)
    result = {"mod_scan": mod_scan, "usage": usage, "saves": saves, "missing": None, "missing_info": None,
              "id_usage": id_usage}
    if missing:
        result["missing"], result["missing_info"] = find_missing(cfg, mod_scan, saves, tray_folder, say)
    result["conflicts"] = check_conflicts(cfg, mod_scan, id_usage, say)
    return result


_game_ids = {}


def game_ids(cfg, progress=None):
    """IDs der Original-Inhalte des Spiels (leer, wenn kein Spielordner bekannt ist)."""
    from missing_cc import index_game_content
    game = cfg.get("game_folder")
    if not game or not os.path.isdir(game):
        return set()
    if game not in _game_ids:
        cache = os.path.join(os.path.dirname(cfg.get("_config_path") or "."), "game_ids_cache.json")
        _game_ids[game] = index_game_content(game, cache_path=cache, progress=progress)
    return _game_ids[game]


def check_conflicts(cfg, mod_scan, id_usage=None, progress=None):
    """Ordnet Überschneidungen im Mods-Ordner ein und wägt sie mit der Nutzung in den Spielständen ab."""
    import conflicts
    return conflicts.analyze_conflicts(mod_scan, id_usage, game_ids(cfg), progress)


def clean_conflicts(cfg, conflict_result):
    """Räumt auf, was sicher geht: überflüssige Dateien wandern nach <Sims-Ordner>/SimVault_aussortiert,
    veraltete Doppel werden aus Paketen entfernt (Original vorher in den Backup-Ordner).
    Gibt das Ergebnis-Dict von conflicts.resolve zurück."""
    import conflicts
    base = cfg.get("sims_folder") or os.path.dirname(os.path.normpath(cfg["mods_folder"]))
    return conflicts.resolve(cfg["mods_folder"], conflict_result, base, cfg["backup_folder"])


def check_health(cfg, deep=False, progress=None, should_stop=None):
    """Prüft alle CC-Dateien und Spielstände auf Schäden."""
    import repair
    return repair.check_all(cfg.get("mods_folder"), cfg.get("savegames_folder"), deep, progress, should_stop)


def repair_items(cfg, items, progress=None):
    """Repariert die reparierbaren Einträge aus check_health. Gibt (Backup-Ordner, Ergebnisse) zurück."""
    import repair
    import archive_tools
    return repair.repair_all(items, cfg["backup_folder"], cfg.get("mods_folder"),
                             archive_tools.tools_from_config(cfg), progress)


def find_game_folders(deep=True, should_stop=None):
    import game_locator
    return game_locator.find_game_folders(deep=deep, should_stop=should_stop)


def find_missing(cfg, mod_scan, saves, tray_folder, progress=None):
    from missing_cc import find_missing as _find
    known = set(mod_scan.id_lookup())
    game = cfg.get("game_folder")
    if game and os.path.isdir(game):
        known |= game_ids(cfg, progress)
        info = f"Abgleich mit Mods-Ordner und Spielordner ({game})"
    else:
        info = ("Abgleich mit dem Mods-Ordner; Spielordner nicht gefunden – "
                "EA-Inhalte werden an ihren kleineren IDs erkannt")
    return _find(saves, tray_folder, known, progress=progress), info


def write_report(cfg, analysis=None, mod_scan=None, found=None):
    from report_generator import generate_report
    analysis = analysis or {}
    return generate_report(mod_scan or analysis.get("mod_scan"), analysis.get("usage"), analysis.get("saves"),
                           output_dir=cfg["report_folder"], db_path=cfg["database"].get("sqlite_path"),
                           formats=cfg["report_formats"], app_name=cfg["branding"].get("app_name", "SimVault"),
                           missing=analysis.get("missing"), missing_info=analysis.get("missing_info"), found=found,
                           conflicts=analysis.get("conflicts"))


def search_locations(cfg, extra_folders=None, drives=None, whole_pc=False):
    import cc_finder
    if drives is None:
        drives = cfg.get("search_drives", True)
    return cc_finder.search_locations(cfg, extra_folders, drives=drives, whole_pc=whole_pc)


def find(cfg, missing_parts, folders, progress=None, should_stop=None, keep_hits=False, work_dir=None):
    """Sucht die fehlenden Teile in folders. Gibt das Fundstellen-Dict (wie im Bericht) zurück."""
    import cc_finder
    import archive_tools
    tools = archive_tools.tools_from_config(cfg)
    wanted = {int(p["id"], 16) for p in missing_parts}
    temp_base = cfg.get("temp_folder") or None
    if temp_base:
        os.makedirs(temp_base, exist_ok=True)
    cc_finder.cleanup_stale_temp(temp_base)
    own = work_dir is None
    work = work_dir or tempfile.mkdtemp(prefix=cc_finder.TEMP_PREFIX, dir=temp_base)
    try:
        hits, unreadable = cc_finder.search(folders, wanted, exclude=[cfg["mods_folder"]], progress=progress,
                                            work_dir=work, tools=tools, keep_hits=keep_hits,
                                            max_archive_mb=cfg.get("max_archive_mb", 4096), should_stop=should_stop)
        found, n_found = cc_finder.summarize(hits, missing_parts)
    finally:
        if own and not keep_hits:
            import shutil
            shutil.rmtree(work, ignore_errors=True)
    return {"dateien": found, "ordner": folders, "nicht_lesbar": unreadable,
            "gefunden": n_found, "gesucht": len(missing_parts)}


def restore(cfg, found_files, exclude=(), backup_first=True, progress=None, skipped=None):
    """Holt Funde zurück (vorher optional Backup). Gibt (backup_pfad, angelegt, fehlgeschlagen) zurück.
    skipped: optionale Liste – wird mit [(Datei, Grund)] der bewusst nicht kopierten Funde gefüllt."""
    import cc_finder
    import archive_tools
    backup_path = None
    if backup_first:
        if progress:
            progress("Sichere den Mods-Ordner …")
        backup_path = backup(cfg, "mods", "full")
    tools = archive_tools.tools_from_config(cfg)
    with tempfile.TemporaryDirectory(prefix=cc_finder.TEMP_PREFIX, dir=cfg.get("temp_folder") or None) as work:
        created, failed = cc_finder.restore(found_files, cfg["mods_folder"], exclude=exclude, tools=tools,
                                            work_dir=work, progress=progress, skipped=skipped)
    return backup_path, created, failed


def backup(cfg, target="mods", mode="full", file_list=None):
    from backup_manager import backup_manager
    source = cfg["mods_folder"] if target == "mods" else cfg["savegames_folder"]
    return backup_manager(mode, source, cfg["backup_folder"], file_list=file_list)


def latest_report(cfg, with_found=False):
    """Neuester Bericht (Pfad, Daten) – optional nur einer mit Fundstellen."""
    for path in sorted(glob.glob(os.path.join(cfg["report_folder"], "report_*.json")), reverse=True):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        if not with_found or (data.get("fundstellen") or {}).get("dateien"):
            return path, data
    return None, None

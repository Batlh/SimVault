# Modul: config.py
# Funktion: Laden und Speichern der zentralen Konfigurationsdatei (`config.json`)
#
# - Fehlt die Datei, wird sie mit Standardwerten angelegt.
# - Der Sims-4-Ordner wird automatisch gesucht (auch deutsche Installation "Die Sims 4"
#   und Dokumente-Ordner in OneDrive).
# - Fehlende Einträge in einer bestehenden config.json werden mit Standardwerten ergänzt.
#
# Standardwerte für:
# - Sims-, Mods-, Savegames-, Tray-, Spiel- und Backup-Pfad
# - Backup-Modus (full, delta, selective)
# - Berichtformate (HTML, CSV, JSON, MD)
# - Datenbank-Typ (sqlite, mysql)
# Optional / geplant:
# - Custom Branding (z.B. Logo, App-Name)
# - Spracheinstellungen (future i18n Support)
# - MySQL/PostgreSQL als Plugin für Fortgeschrittene

import os
import copy
import json

SIMS_FOLDER_NAMES = ["Die Sims 4", "The Sims 4", "Les Sims 4", "De Sims 4", "Los Sims 4", "I Sims 4"]

DEFAULT_CONFIG = {
    "sims_folder": "",          # leer = automatisch suchen
    "mods_folder": "",          # leer = <sims_folder>/Mods
    "savegames_folder": "",     # leer = <sims_folder>/saves
    "tray_folder": "",          # leer = <sims_folder>/Tray
    "game_folder": "",          # Spiel-Installation, leer = automatisch suchen (optional, für sichere Fehlend-Erkennung)
    "search_folders": [],       # Ordner für "find" – leer = Downloads, alte Mods-Ordner, Mod-Manager … automatisch
    "search_drives": True,      # "find" durchsucht zusätzlich alle weiteren Laufwerke (D:, E:, USB …)
    "extractor": "",            # Entpacker für RAR/7z: leer = automatisch, Pfad zu 7z.exe/UnRAR.exe/tar.exe, "none" = aus
    "max_archive_mb": 4096,     # größere Archive werden bei der Suche übersprungen
    "temp_folder": "",          # Temp-Ordner fürs kurze Entpacken (leer = System-Temp, z. B. auf D: legen)
    "backup_folder": "./backups",
    "backup_mode": "full",      # full, delta, selective
    "report_folder": "./reports",
    "report_formats": ["html", "csv", "json", "md"],
    "database": {
        "type": "sqlite",       # options: sqlite, mysql (future)
        "sqlite_path": "simvault_data.db",
        "mysql": {
            "enabled": False,
            "host": "localhost",
            "user": "root",
            "password": "",
            "database": "simvault",
        },
    },
    "branding": {
        "app_name": "SimVault",
        "logo_path": "",
    },
    "language": "en",           # future: i18n support
}


def _documents_candidates():
    home = os.path.expanduser("~")
    candidates = [os.path.join(home, "Documents"), os.path.join(home, "Dokumente")]
    for env in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        base = os.environ.get(env)
        if base:
            candidates += [os.path.join(base, "Documents"), os.path.join(base, "Dokumente")]
    return candidates


def find_sims_folder():
    """Sucht den Sims-4-Benutzerordner. Bevorzugt den Ordner, der Spielstände enthält."""
    found = []
    for docs in _documents_candidates():
        for name in SIMS_FOLDER_NAMES:
            path = os.path.join(docs, "Electronic Arts", name)
            if os.path.isdir(path):
                found.append(path)
    for path in found:
        if os.path.isdir(os.path.join(path, "saves")):
            return path
    return found[0] if found else ""


def _merge(defaults, user):
    merged = copy.deepcopy(defaults)
    for key, value in user.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def resolve_paths(config):
    """Füllt leere Pfade aus dem Sims-Ordner auf. Verändert config nicht, gibt eine Kopie zurück."""
    cfg = copy.deepcopy(config)
    sims = cfg.get("sims_folder") or find_sims_folder()
    cfg["sims_folder"] = sims
    for key, sub in (("mods_folder", "Mods"), ("savegames_folder", "saves"), ("tray_folder", "Tray")):
        if not cfg.get(key) and sims:
            cfg[key] = os.path.join(sims, sub)
    if not cfg.get("game_folder"):
        from missing_cc import find_game_folder
        cfg["game_folder"] = find_game_folder()
    return cfg


def create_default_config(config_path="config.json"):
    """Erstellt eine Standard-Konfigurationsdatei, falls keine existiert."""
    if not os.path.exists(config_path):
        save_config(DEFAULT_CONFIG, config_path)
        return True
    return False


def load_config(config_path="config.json"):
    """Lädt die Konfiguration (legt sie bei Bedarf an) und ergänzt fehlende Werte."""
    create_default_config(config_path)
    with open(config_path, "r", encoding="utf-8") as f:
        user = json.load(f)
    return _merge(DEFAULT_CONFIG, user)


def save_config(config, config_path="config.json"):
    """Speichert die Konfigurationsdatei."""
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

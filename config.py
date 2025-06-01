# Modul: config.py
# Funktion: Laden und Speichern der zentralen Konfigurationsdatei (`config.json`)

# Aufgaben:
# - Standard-Konfigurationsdatei verwalten (`config.json`)
# - Laden der Konfiguration beim Start
# - Speichern von Änderungen an der Konfiguration
# - Validierung von Konfigurationseinträgen
# - Erstellen einer Standard-Config, falls keine existiert

# Geplante Features:
# - Standardwerte für:
#   - Mods-Ordner-Pfad
#   - Savegames-Ordner-Pfad
#   - Backup-Pfad
#   - Backup-Modus (full, delta, selective)
#   - Berichtformate (HTML, CSV, JSON, MD)
#   - Datenbank-Typ (sqlite, mysql)
# - Optional:
#   - Custom Branding (z.B. Logo, App-Name)
#   - Spracheinstellungen (future i18n Support)

# Strukturvorschlag:
# - Funktion: load_config(config_path='config.json')
# - Funktion: save_config(config, config_path='config.json')
# - Funktion: create_default_config(config_path='config.json')

import os
import json

# Default configuration settings
DEFAULT_CONFIG = {
    "mods_folder": "C:/Users/YourName/Documents/Electronic Arts/The Sims 4/Mods",
    "savegames_folder": "C:/Users/YourName/Documents/Electronic Arts/The Sims 4/saves",
    "backup_folder": "./backups",
    "backup_mode": "full",  # options: full, delta, selective
    "report_formats": ["html", "csv", "json", "md"],
    "database": {
        "type": "sqlite",  # options: sqlite, mysql (future)
        "sqlite_path": "simvault_data.db",
        "mysql": {
            "enabled": False,
            "host": "localhost",
            "user": "root",
            "password": "",
            "database": "simvault"
        }
    },
    "branding": {
        "app_name": "SimVault",
        "logo_path": ""
    },
    "language": "en"  # future: i18n support
}

def create_default_config(config_path='config.json'):
    """Erstellt eine Standard-Konfigurationsdatei, falls keine existiert."""
    if not os.path.exists(config_path):
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
        print(f"Default config created at {config_path}")
    else:
        print(f"Config file already exists at {config_path}")

def load_config(config_path='config.json'):
    """Lädt die Konfigurationsdatei."""
    if not os.path.exists(config_path):
        print("No config file found. Creating default config...")
        create_default_config(config_path)
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    print(f"Config loaded from {config_path}")
    return config

def save_config(config, config_path='config.json'):
    """Speichert die Konfigurationsdatei."""
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4)
    print(f"Config saved to {config_path}")

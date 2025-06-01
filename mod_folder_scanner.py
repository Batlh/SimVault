# Modul: mod_folder_scanner.py
# Funktion: Scannt den Sims 4 Mods-Ordner und listet installierte CC- und Script-Mod-Dateien

# Aufgaben:
# - Mods-Ordner durchsuchen
# - Alle .package- und .ts4script-Dateien finden
# - Dateinamen extrahieren
# - Vergleichbare Liste erstellen

# Strukturvorschlag:
# - Funktion: scan_mods_folder(folder_path) → Gibt Liste der CC- und Script-Dateien zurück

# mod_folder_scanner.py

import os
import logging

# Logging konfigurieren
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def scan_mods_folder(folder_path):
    """
    Scannt den Mods-Ordner nach .package- und .ts4script-Dateien und erstellt eine Liste der Dateipfade.
    
    Args:
        folder_path (str): Pfad zum Sims 4 Mods-Ordner.
        
    Returns:
        list: Liste der gefundenen Mod-Dateien (voller Pfad).
    """
    cc_files = []
    try:
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                if file.lower().endswith(('.package', '.ts4script')):
                    full_path = os.path.join(root, file)
                    cc_files.append(full_path)
        logging.info(f"{len(cc_files)} Mod-Dateien (.package und .ts4script) im Mods-Ordner gefunden.")
    except Exception as e:
        logging.error(f"Fehler beim Scannen des Mods-Ordners: {e}")
    
    return cc_files

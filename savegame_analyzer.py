# Modul: savegame_analyzer.py
# Funktion: Analysiert Sims 4 Savegames, extrahiert verwendete CC-IDs

# Aufgaben:
# - Savegame-Datei laden (Binary-Parsing)
# - CC-IDs extrahieren
# - Fehlerhandling und Logging
# - Ergebnisse als Liste zurückgeben

# Strukturvorschlag:
# - Funktion: load_savegame(file_path)
# - Funktion: extract_cc_ids(savegame_binary_data)
# - Funktion: analyze_savegame(file_path) → Main Entry

# savegame_analyzer.py

import struct
import logging

# Logging konfigurieren
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def load_savegame(file_path):
    """Lädt die Savegame-Datei im Binärmodus."""
    try:
        with open(file_path, 'rb') as f:
            data = f.read()
        logging.info(f"Savegame {file_path} erfolgreich geladen.")
        return data
    except Exception as e:
        logging.error(f"Fehler beim Laden des Savegames: {e}")
        return None

def extract_cc_ids(savegame_binary_data):
    """Extrahiert CC-IDs aus dem Binärdaten des Savegames."""
    cc_ids = set()
    try:
        # Suche nach typischem CC-ID-Muster
        for i in range(0, len(savegame_binary_data) - 8, 8):
            chunk = savegame_binary_data[i:i+8]
            if len(chunk) == 8:
                try:
                    cc_id = struct.unpack('<Q', chunk)[0]
                    # Filter: Nur CC-relevante IDs
                    if cc_id > 0x8000000000000000:
                        cc_ids.add(hex(cc_id))
                except struct.error:
                    continue
        logging.info(f"{len(cc_ids)} CC-IDs extrahiert.")
    except Exception as e:
        logging.error(f"Fehler beim Extrahieren der CC-IDs: {e}")
    return list(cc_ids)

def analyze_savegame(file_path):
    """Hauptfunktion: lädt Savegame und extrahiert CC-IDs."""
    savegame_data = load_savegame(file_path)
    if savegame_data:
        cc_ids = extract_cc_ids(savegame_data)
        return cc_ids
    else:
        return []

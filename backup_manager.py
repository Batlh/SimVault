# Modul: backup_manager.py
# Funktion: Erstellt automatische Backups von Savegames und Mods-Ordnern vor Änderungen mit drei wählbaren Backup-Modi

# Aufgaben:
# - Backup des Savegame-Ordners oder Mods-Ordners erstellen
# - Unterstützte Backup-Modi:
#   - Full ZIP Backup: Gesamter Ordner wird als ZIP-Datei komprimiert (Standard)
#   - Delta Backup: Nur neue oder geänderte Dateien werden gesichert (Hash-basiert)
#   - Selective Backup: Nur vom Benutzer ausgewählte Dateien werden gesichert
# - Backups werden in ein eigenes Backup-Verzeichnis gespeichert (mit Zeitstempel)
# - Speicherung der Datei-Hashes für Delta-Backups (z.B. `previous_hashes.json`)

# Geplante Features:
# - Komprimierung der kompletten Backups als ZIP-Dateien (ZIP_DEFLATED)
# - Delta-Backup: Vergleich neuer Dateien via SHA256-Hash
# - Selective Backup: Benutzerdefinierte Dateiauswahl für gezielte Sicherungen
# - Automatische Timestamps im Backup-Ordnernamen
# - Optionales Aufräumen alter Backups (z.B. älter als 30 Tage oder mehr als 10 Backups)

# Strukturvorschlag:
# - Funktion: full_zip_backup(source_folder, backup_root)
# - Funktion: delta_backup(source_folder, backup_root, hash_file='previous_hashes.json')
# - Funktion: selective_backup(file_list, source_folder, backup_root)
# - Funktion: backup_manager(mode, source_folder, backup_root, file_list=None)

import os
import zipfile
import hashlib
import shutil
from datetime import datetime
import json

# Helper function to calculate SHA256 Hash of a file
def calculate_hash(file_path):
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

# Helper function to load or initialize previous file hashes
def load_previous_hashes(hash_file):
    if os.path.exists(hash_file):
        with open(hash_file, 'r') as f:
            return json.load(f)
    return {}

def save_current_hashes(hashes, hash_file):
    with open(hash_file, 'w') as f:
        json.dump(hashes, f, indent=4)

# 1. Full ZIP Backup
def full_zip_backup(source_folder, backup_root):
    os.makedirs(backup_root, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_name = os.path.basename(source_folder.rstrip(os.sep))
    zip_name = f"{folder_name}_backup_{timestamp}.zip"
    zip_path = os.path.join(backup_root, zip_name)

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(source_folder):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, start=source_folder)
                zipf.write(file_path, arcname)
    return zip_path

# 2. Delta Backup (Only new/changed files)
# Hinweis: Ein Delta-Backup enthält nur Änderungen seit dem letzten Lauf – zum Wiederherstellen
# braucht man das letzte Voll-Backup plus alle Deltas danach.
def delta_backup(source_folder, backup_root, hash_file=None):
    os.makedirs(backup_root, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_name = os.path.basename(source_folder.rstrip(os.sep).rstrip("/"))
    # Eigene Hash-Datei pro Quellordner, sonst vergleicht ein Mods-Backup mit den Hashes der Spielstände
    if hash_file is None:
        hash_file = os.path.join(backup_root, f"{folder_name}_hashes.json")
    delta_folder = os.path.join(backup_root, f"{folder_name}_delta_{timestamp}")
    os.makedirs(delta_folder, exist_ok=True)

    previous_hashes = load_previous_hashes(hash_file)
    current_hashes = {}

    for root, dirs, files in os.walk(source_folder):
        for file in files:
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, start=source_folder)
            file_hash = calculate_hash(file_path)
            current_hashes[rel_path] = file_hash

            if rel_path not in previous_hashes or previous_hashes[rel_path] != file_hash:
                # Neue oder geänderte Datei sichern
                dest_path = os.path.join(delta_folder, rel_path)
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                shutil.copy2(file_path, dest_path)
    
    save_current_hashes(current_hashes, hash_file)
    return delta_folder

# 3. Selective Backup (User specifies files to backup)
def selective_backup(file_list, source_folder, backup_root):
    os.makedirs(backup_root, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_name = os.path.basename(source_folder.rstrip(os.sep).rstrip("/"))
    selective_folder = os.path.join(backup_root, f"{folder_name}_selective_{timestamp}")
    os.makedirs(selective_folder, exist_ok=True)

    for file_rel_path in file_list:
        source_path = os.path.join(source_folder, file_rel_path)
        if os.path.exists(source_path):
            dest_path = os.path.join(selective_folder, file_rel_path)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            shutil.copy2(source_path, dest_path)
        else:
            print(f"Warning: {source_path} does not exist and was skipped.")
    return selective_folder

# Dispatcher
def backup_manager(mode, source_folder, backup_root, file_list=None):
    if mode == 'full':
        return full_zip_backup(source_folder, backup_root)
    elif mode == 'delta':
        return delta_backup(source_folder, backup_root)
    elif mode == 'selective' and file_list:
        return selective_backup(file_list, source_folder, backup_root)
    else:
        raise ValueError("Invalid mode or missing file list for selective backup.")

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

# Umgesetzt:
# - Komprimierung der kompletten Backups als ZIP-Dateien (ZIP_DEFLATED)
# - Delta-Backup: Vergleich neuer Dateien via SHA256-Hash
# - Selective Backup: Benutzerdefinierte Dateiauswahl für gezielte Sicherungen
# - Automatische Timestamps im Backup-Ordnernamen
# - Wiederherstellen (Recovery): Voll-Backup, Delta (letztes Voll-Backup + alle Deltas bis zum gewählten),
#   Selective sowie die Sicherungen von Reparatur und Konflikt-Aufräumen -> list_backups / restore_backup
# - Aufräumen alter Backups (z.B. älter als 30 Tage oder mehr als 10 Backups) -> plan_cleanup / cleanup_backups

# Strukturvorschlag:
# - Funktion: full_zip_backup(source_folder, backup_root)
# - Funktion: delta_backup(source_folder, backup_root, hash_file='previous_hashes.json')
# - Funktion: selective_backup(file_list, source_folder, backup_root)
# - Funktion: backup_manager(mode, source_folder, backup_root, file_list=None)

import os
import re
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


# ---------------------------------------------------------------------------
# Recovery: Backups auflisten, wiederherstellen, alte aufräumen
# ---------------------------------------------------------------------------

BACKUP_PATTERN = re.compile(r"^(?P<quelle>.+)_(?P<art>backup|delta|selective)_(?P<zeit>\d{8}_\d{6})(?P<zip>\.zip)?$")
SPECIAL_PATTERN = re.compile(r"^(?P<art>reparatur|konflikte|beiseite)_(?P<zeit>\d{8}_\d{6})$")
KIND_NAMES = {"backup": "Voll-Backup", "delta": "Delta", "selective": "Auswahl", "reparatur": "Originale (Reparatur)",
              "konflikte": "Originale (Konflikte)", "beiseite": "Beiseitegelegt (Wiederherstellung)"}


def _folder_stats(path):
    size = count = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            count += 1
            try:
                size += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return size, count


def list_backups(backup_root):
    """Alle Backups im Backup-Ordner, neueste zuerst. Jedes als Dict:
    name, pfad, art (backup/delta/selective/reparatur/konflikte/beiseite), art_name, quelle (z. B. "Mods"),
    zeit (datetime), groesse (Bytes), dateien (Anzahl; bei ZIPs erst beim Wiederherstellen bekannt = None)."""
    result = []
    if not backup_root or not os.path.isdir(backup_root):
        return result
    for name in os.listdir(backup_root):
        path = os.path.join(backup_root, name)
        match = BACKUP_PATTERN.match(name) or SPECIAL_PATTERN.match(name)
        if not match:
            continue
        info = match.groupdict()
        is_zip = bool(info.get("zip"))
        if is_zip != os.path.isfile(path):          # ZIP muss Datei sein, alles andere ein Ordner
            continue
        try:
            when = datetime.strptime(info["zeit"], "%Y%m%d_%H%M%S")
        except ValueError:
            continue
        size, count = (os.path.getsize(path), None) if is_zip else _folder_stats(path)
        result.append({"name": name, "pfad": path, "art": info["art"], "art_name": KIND_NAMES[info["art"]],
                       "quelle": info.get("quelle") or "", "zeit": when, "groesse": size, "dateien": count})
    return sorted(result, key=lambda b: (b["zeit"], b["name"]), reverse=True)


def _safe_rel(name):
    """Relativer Pfad aus einem Archiv – oder None, wenn er aus dem Zielordner herausführen würde."""
    rel = os.path.normpath(name.replace("\\", "/"))
    if os.path.isabs(rel) or rel.startswith("..") or rel in (".", ""):
        return None
    return rel


def _collect(backup, mapping, sub=None):
    """Trägt die Dateien eines Backups in mapping ein: rel_pfad -> (Backup, Eintrag). Spätere überschreiben frühere."""
    if backup["pfad"].lower().endswith(".zip") and os.path.isfile(backup["pfad"]):
        with zipfile.ZipFile(backup["pfad"]) as z:
            for info in z.infolist():
                rel = None if info.is_dir() else _safe_rel(info.filename)
                if rel:
                    mapping[rel] = (backup, info.filename)
        return
    base = os.path.join(backup["pfad"], sub) if sub else backup["pfad"]
    for root, _dirs, files in os.walk(base):
        for name in files:
            full = os.path.join(root, name)
            mapping[os.path.relpath(full, base)] = (backup, full)


def restore_chain(backups, backup):
    """Welche Backups nacheinander eingespielt werden: beim Delta das letzte Voll-Backup davor und alle
    Deltas bis einschließlich des gewählten, sonst nur das Backup selbst."""
    if backup["art"] != "delta":
        return [backup]
    same = [b for b in backups if b["quelle"].lower() == backup["quelle"].lower()]
    fulls = [b for b in same if b["art"] == "backup" and b["zeit"] <= backup["zeit"]]
    base = max(fulls, key=lambda b: b["zeit"]) if fulls else None
    start = base["zeit"] if base else datetime.min
    deltas = sorted((b for b in same if b["art"] == "delta" and start <= b["zeit"] <= backup["zeit"]),
                    key=lambda b: b["zeit"])
    return ([base] if base else []) + deltas


def restore_backup(backup_root, name, targets, overwrite=True, exact=False, progress=None):
    """Spielt ein Backup zurück.

    targets:   {Ordnername in Kleinbuchstaben: Zielordner}, z. B. {"mods": ".../Mods", "saves": ".../saves"}
    overwrite: vorhandene Dateien ersetzen (False = nur Fehlendes ergänzen)
    exact:     Zielordner genau auf den Stand des Backups bringen – Dateien, die das Backup nicht kennt,
               werden nach <Backup-Ordner>/beiseite_<Zeit>/ verschoben (nicht gelöscht). Nur bei Voll/Delta.
    Gibt ein Dict zurück: ziele, kette, wiederhergestellt, uebersprungen, beiseite (Ordner oder None), verschoben."""
    backups = list_backups(backup_root)
    backup = next((b for b in backups if b["name"] == name), None)
    if backup is None:
        raise ValueError(f"Backup nicht gefunden: {name}")
    if backup["art"] == "beiseite":
        raise ValueError("Beiseitegelegte Dateien bitte von Hand zurückschieben.")
    plans = []                       # [(Zielordner, mapping)]
    if backup["art"] in ("reparatur", "konflikte"):
        # Originale: reparatur_<Zeit>/Mods/… und /saves/…, konflikte_<Zeit>/… (relativ zum Mods-Ordner)
        subs = [("mods", "Mods"), ("saves", "saves")] if backup["art"] == "reparatur" else [("mods", None)]
        for key, sub in subs:
            if sub and not os.path.isdir(os.path.join(backup["pfad"], sub)):
                continue
            if key not in targets:
                raise ValueError(f"Zielordner für {key} ist nicht bekannt.")
            mapping = {}
            _collect(backup, mapping, sub)
            plans.append((targets[key], mapping))
        chain, exact = [backup], False
    else:
        target = targets.get(backup["quelle"].lower())
        if not target:
            raise ValueError(f"Kein Zielordner für „{backup['quelle']}“ bekannt – das Backup stammt aus einem "
                             "anderen Ordner als den eingestellten.")
        chain = restore_chain(backups, backup)
        mapping = {}
        for part in chain:
            _collect(part, mapping)
        plans.append((target, mapping))
        if backup["art"] == "selective":
            exact = False

    out = {"ziele": [t for t, _m in plans], "kette": [b["name"] for b in chain], "wiederhergestellt": 0,
           "uebersprungen": 0, "beiseite": None, "verschoben": 0}
    open_zips = {}
    try:
        for target, mapping in plans:
            os.makedirs(target, exist_ok=True)
            if exact:
                keep = {os.path.normcase(rel) for rel in mapping}
                aside = os.path.join(backup_root, "beiseite_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
                for root, _dirs, files in os.walk(target):
                    for fname in files:
                        full = os.path.join(root, fname)
                        rel = os.path.relpath(full, target)
                        if os.path.normcase(rel) not in keep:
                            dest = os.path.join(aside, rel)
                            os.makedirs(os.path.dirname(dest), exist_ok=True)
                            shutil.move(full, dest)
                            out["verschoben"] += 1
                            out["beiseite"] = aside
            total = len(mapping)
            for i, (rel, (part, member)) in enumerate(sorted(mapping.items()), 1):
                if progress and i % 50 == 0:
                    progress(f"Wiederherstellen: {i}/{total}")
                dest = os.path.join(target, rel)
                if os.path.exists(dest) and not overwrite:
                    out["uebersprungen"] += 1
                    continue
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                if part["pfad"].lower().endswith(".zip") and os.path.isfile(part["pfad"]):
                    z = open_zips.get(part["pfad"]) or open_zips.setdefault(part["pfad"], zipfile.ZipFile(part["pfad"]))
                    info = z.getinfo(member)
                    with z.open(info) as src, open(dest, "wb") as dst:
                        shutil.copyfileobj(src, dst, 1 << 20)
                    try:                                    # Änderungsdatum aus dem Backup übernehmen
                        stamp = datetime(*info.date_time).timestamp()
                        os.utime(dest, (stamp, stamp))
                    except (ValueError, OSError):
                        pass
                else:
                    shutil.copy2(member, dest)
                out["wiederhergestellt"] += 1
    finally:
        for z in open_zips.values():
            z.close()
    return out


def plan_cleanup(backup_root, keep_last=10, max_age_days=30, now=None):
    """Welche Backups beim Aufräumen wegfallen würden (Liste wie list_backups).
    Regeln je Quellordner: höchstens keep_last Voll-Backups und keine älter als max_age_days (0 = Regel aus);
    das neueste Voll-Backup bleibt immer. Deltas fallen weg, wenn ihr Voll-Backup wegfällt oder sie zu alt sind."""
    now = now or datetime.now()
    backups = list_backups(backup_root)

    def too_old(b):
        return max_age_days > 0 and (now - b["zeit"]).days > max_age_days

    doomed = []
    sources = {b["quelle"].lower() for b in backups if b["art"] in ("backup", "delta", "selective")}
    for source in sources:
        same = [b for b in backups if b["quelle"].lower() == source]
        fulls = [b for b in same if b["art"] == "backup"]                 # neueste zuerst
        kept = [b for i, b in enumerate(fulls) if i == 0 or not (too_old(b) or (keep_last > 0 and i >= keep_last))]
        doomed += [b for b in fulls if b not in kept]
        oldest_kept = min((b["zeit"] for b in kept), default=None)
        for b in same:
            if b["art"] == "delta" and (too_old(b) or (fulls and oldest_kept and b["zeit"] < oldest_kept)):
                doomed.append(b)
        selective = [b for b in same if b["art"] == "selective"]
        doomed += [b for i, b in enumerate(selective) if too_old(b) or (keep_last > 0 and i >= keep_last)]
    doomed += [b for b in backups if b["art"] in ("reparatur", "konflikte", "beiseite") and too_old(b)]
    return sorted(doomed, key=lambda b: b["zeit"], reverse=True)


def cleanup_backups(backup_root, keep_last=10, max_age_days=30):
    """Löscht alte Backups nach den Regeln von plan_cleanup. Gibt (gelöscht, freigegebene Bytes) zurück."""
    removed, freed = [], 0
    for b in plan_cleanup(backup_root, keep_last, max_age_days):
        try:
            if os.path.isfile(b["pfad"]):
                os.remove(b["pfad"])
            else:
                shutil.rmtree(b["pfad"])
        except OSError:
            continue
        removed.append(b["name"])
        freed += b["groesse"]
    return removed, freed

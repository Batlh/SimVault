# Modul: savegame_analyzer.py
# Funktion: Liest Sims-4-Spielstände (.save) und Tray-Dateien (Bibliothek) und stellt fest,
#           welche installierte CC darin tatsächlich verwendet wird.
#
# Vorgehen:
# - Eine .save-Datei ist ein DBPF-Paket. Ihre Ressourcen (v. a. die Spielstand-Daten) werden
#   entpackt und als Protobuf durchlaufen – ohne Schema: Es werden alle 64-Bit-Zahlen eingesammelt,
#   auch aus verschachtelten Nachrichten und gepackten Listen.
# - Zusätzlich werden die Rohdaten nach 8-Byte-Werten (Little Endian) durchsucht.
# - Diese Zahlen werden mit den Ressourcen-IDs aller installierten Mods abgeglichen.
#   Bei 64-Bit-IDs ist ein zufälliger Treffer praktisch ausgeschlossen, das Ergebnis ist also verlässlich.
#
# Grenzen:
# - "Fehlende" CC (im Spielstand verwendet, aber nicht installiert) lässt sich so noch nicht
#   sicher erkennen, weil dafür bekannt sein muss, welche Zahlen CAS-Teile/Objekte sind und
#   welche IDs zum Spiel selbst gehören. Das ist der nächste Ausbauschritt.

import os
import re
import sys
import glob
import logging
from array import array

import dbpf

log = logging.getLogger(__name__)

SAVE_PATTERN = re.compile(r"^Slot_[0-9A-Fa-f]+\.save$")
# Nur Dateien mit Daten; .sgi/.hhi/.bpi/.rmi sind Vorschaubilder
TRAY_EXTENSIONS = (".trayitem", ".householdbinary", ".blueprint", ".room")
MAX_DEPTH = 40


# ---------------------------------------------------------------------------
# Spielstände finden
# ---------------------------------------------------------------------------

def find_saves(saves_folder):
    """Gibt alle aktuellen Spielstände (ohne .verX-Sicherungen) zurück, neuester zuerst."""
    if not os.path.isdir(saves_folder):
        return []
    saves = [os.path.join(saves_folder, n) for n in os.listdir(saves_folder) if SAVE_PATTERN.match(n)]
    return sorted(saves, key=os.path.getmtime, reverse=True)


# ---------------------------------------------------------------------------
# Zahlen aus Binärdaten einsammeln
# ---------------------------------------------------------------------------

def _read_varint(buf, pos, end):
    result = 0
    shift = 0
    while True:
        if pos >= end or shift > 63:
            raise ValueError
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if b < 0x80:
            return result, pos
        shift += 7


def _walk_protobuf(buf, start, end, known, found, depth):
    """Durchläuft buf[start:end] als Protobuf-Nachricht. Gibt True zurück, wenn der Bereich
    vollständig und gültig war. Treffer (Werte, die in known liegen) landen in found."""
    pos = start
    rv = _read_varint
    while pos < end:
        try:
            key, pos = rv(buf, pos, end)
        except ValueError:
            return False
        field_no = key >> 3
        wire = key & 7
        if field_no == 0:
            return False
        if wire == 0:
            try:
                value, pos = rv(buf, pos, end)
            except ValueError:
                return False
            if value in known:
                found.add(value)
        elif wire == 1:
            if pos + 8 > end:
                return False
            value = int.from_bytes(buf[pos:pos + 8], "little")
            pos += 8
            if value in known:
                found.add(value)
        elif wire == 2:
            try:
                length, pos = rv(buf, pos, end)
            except ValueError:
                return False
            sub_end = pos + length
            if sub_end > end:
                return False
            if length and depth < MAX_DEPTH:
                if not _walk_protobuf(buf, pos, sub_end, known, found, depth + 1):
                    if not _walk_packed_varints(buf, pos, sub_end, known, found) and length % 8 == 0:
                        # gepackte 64-Bit-Liste (so stehen z. B. die Outfit-Teile der Sims)
                        for i in range(pos, sub_end, 8):
                            value = int.from_bytes(buf[i:i + 8], "little")
                            if value in known:
                                found.add(value)
            pos = sub_end
        elif wire == 5:
            if pos + 4 > end:
                return False
            pos += 4
        else:
            return False
    return pos == end


def _walk_packed_varints(buf, pos, end, known, found):
    """Versucht einen Bereich als gepackte Liste von Varints zu lesen (z. B. Listen von CAS-Teil-IDs)."""
    values = []
    try:
        while pos < end:
            value, pos = _read_varint(buf, pos, end)
            values.append(value)
    except ValueError:
        return False
    for value in values:
        if value in known:
            found.add(value)
    return True


def _scan_raw_uint64(data, known, found):
    """Sucht alle 8-Byte-Fenster (Little Endian) in data, die einer bekannten ID entsprechen."""
    n = len(data)
    for align in range(8):
        usable = (n - align) // 8 * 8
        if usable <= 0:
            continue
        arr = array("Q")
        arr.frombytes(data[align:align + usable])
        if sys.byteorder != "little":
            arr.byteswap()
        found.update(known.intersection(arr))


def collect_known_ids(data, known, try_offsets=(0,)):
    """Sammelt alle IDs aus known, die in den Binärdaten vorkommen."""
    found = set()
    if not data or not known:
        return found
    view = memoryview(data)
    for off in try_offsets:
        if off < len(data) and _walk_protobuf(view, off, len(data), known, found, 0):
            break
    _scan_raw_uint64(data, known, found)
    return found


# ---------------------------------------------------------------------------
# Spielstände und Tray auswerten
# ---------------------------------------------------------------------------

def ids_in_save(save_path, known):
    """Liest einen Spielstand und gibt die darin verwendeten IDs aus known zurück."""
    found = set()
    entries = dbpf.read_index(save_path)
    for entry in entries:
        if entry.compression == dbpf.COMPRESSION_DELETED:
            continue
        try:
            data = dbpf.read_resource(save_path, entry)
        except Exception as e:  # einzelne defekte Ressource soll nicht alles abbrechen
            log.warning("Ressource %s in %s nicht lesbar: %s", entry.tgi_str(), save_path, e)
            continue
        found |= collect_known_ids(data, known)
    return found


def _tray_item_id(filename):
    # Tray-Dateien heißen z. B. "0x00000002!0x0a1b2c3d4e5f6789.householdbinary"
    stem = os.path.splitext(filename)[0]
    return stem.split("!")[-1].lower()


def ids_in_tray(tray_folder, known):
    """Gibt {ID: Anzahl Tray-Einträge (Haushalte/Grundstücke/Räume), die sie verwenden} zurück."""
    usage = {}
    if not os.path.isdir(tray_folder):
        return usage
    per_item = {}
    for path in glob.glob(os.path.join(tray_folder, "*")):
        if not path.lower().endswith(TRAY_EXTENSIONS):
            continue
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            continue
        if data[:4] == dbpf.DBPF_MAGIC:
            try:
                ids = ids_in_save(path, known)
            except dbpf.DBPFError:
                ids = collect_known_ids(data, known)
        else:
            # Manche Tray-Dateien haben einen kurzen Kopf vor den Protobuf-Daten
            ids = collect_known_ids(data, known, try_offsets=(0, 4, 8, 12, 16))
        if ids:
            per_item.setdefault(_tray_item_id(os.path.basename(path)), set()).update(ids)
    for ids in per_item.values():
        for rid in ids:
            usage[rid] = usage.get(rid, 0) + 1
    return usage


def analyze_usage(mod_scan, save_paths, tray_folder=None, progress=None):
    """Gleicht installierte Mods mit Spielständen (und optional dem Tray) ab.

    Gibt eine Liste von Dicts zurück, je Mod-Datei:
      {"mod": ModFile, "status": ..., "saves": [Spielstand-Namen], "tray": Anzahl}
    """
    lookup = mod_scan.id_lookup()
    known = set(lookup)

    used_in_save = {}   # ID -> Liste der Spielstand-Dateinamen
    for i, save in enumerate(save_paths, 1):
        if progress:
            progress(f"Spielstand {i}/{len(save_paths)}: {os.path.basename(save)}")
        try:
            ids = ids_in_save(save, known)
        except (dbpf.DBPFError, OSError) as e:
            log.error("Spielstand %s nicht lesbar: %s", save, e)
            continue
        for rid in ids:
            used_in_save.setdefault(rid, []).append(os.path.basename(save))

    tray_usage = {}
    if tray_folder:
        if progress:
            progress("Bibliothek (Tray)")
        tray_usage = ids_in_tray(tray_folder, known)

    rows = []
    for mod in mod_scan.mods:
        saves = sorted({s for rid in mod.match_ids for s in used_in_save.get(rid, [])})
        tray = max((tray_usage.get(rid, 0) for rid in mod.match_ids), default=0)
        used = bool(saves or tray)
        if mod.category == "Defekt":
            status = "defekt"
        elif mod.kind == "script":
            status = "nicht prüfbar"
        elif used:
            status = "genutzt"
        elif mod.is_content:
            status = "ungenutzt"
        else:
            status = "nicht nachweisbar"
        rows.append({"mod": mod, "status": status, "saves": saves, "tray": tray})
    return rows

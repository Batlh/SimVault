# Modul: missing_cc.py
# Funktion: Findet fehlende CC – CAS-Teile und Objekte, die in Spielständen oder in der
#           Bibliothek verwendet werden, aber nicht (mehr) installiert sind.
#
# Vorgehen (an echten Spielständen ermittelt):
# - Spielstand-Daten (Ressource 0x0000000D) sind Protobuf. Darin:
#     Feld 6  = Sims:      5 Vorname, 6 Nachname
#                          21 → 1 → 5 → 1   Outfit-Teile (gepackte 64-Bit-Liste) = CAS-Teile
#                          28 → 5/6 → 1 → 1 weitere CAS-Teile (z. B. Make-up/Tattoos)
#                          20 → 1 → 30      Inventar-Objekte (Objektdefinition)
#     Feld 5  = Haushalte: 3 Name, 6 → 1 → 30 Haushaltsinventar
#     Feld 7  = Zonen:     1 Zonen-ID, 2 Grundstücksname
#     Feld 8  = 4 → 1 → 30 weitere Objekte
# - Zonen (Ressource 0x00000006, Instanz = Zonen-ID): 3 → 1 → 30 platzierte Objekte
# - Bibliothek: .householdbinary (8 Byte Kopf) → 1 → 6 = Sims wie oben,
#               Name des Eintrags in der .trayitem-Datei (Feld 4)
#
# Woran wird fehlende CC erkannt?
# - EA-Inhalte haben IDs unter 2^32, Creator-CC nutzt 64-Bit-Hashes (≥ 2^32).
#   Eine ID ≥ 2^32 an einer CAS-/Objekt-Stelle, die in keinem installierten Paket steckt,
#   ist fehlende CC.
# - Ist der Spielordner bekannt, werden zusätzlich alle Spiel-IDs ausgeschlossen (ganz sicher).
#
# Noch nicht abgedeckt: Grundstücke/Räume in der Bibliothek (.blueprint/.room sind anders verpackt).

import os
import json
import glob
import logging
from collections import Counter

import dbpf
from savegame_analyzer import _read_varint, _tray_item_id

log = logging.getLogger(__name__)

MIN_CC_ID = 1 << 32

# Pfade innerhalb eines Sims: (Pfad, Modus)
SIM_CAS_PATHS = [((21, 1, 5, 1), "fixed64_list"),
                 ((28, 5, 1, 1), "scalar"),
                 ((28, 6, 1, 1), "scalar")]
SIM_INVENTORY_PATH = (20, 1, 30)

GAME_FOLDER_NAMES = ["The Sims 4", "Die Sims 4"]
GAME_FOLDER_PARENTS = [
    r"C:\Program Files\EA Games",
    r"C:\Program Files (x86)\EA Games",
    r"C:\Program Files (x86)\Origin Games",
    r"C:\Program Files\Origin Games",
    r"C:\Program Files (x86)\Steam\steamapps\common",
    r"C:\Program Files\Steam\steamapps\common",
]


# ---------------------------------------------------------------------------
# Kleiner Protobuf-Leser
# ---------------------------------------------------------------------------

def iter_fields(buf, start, end):
    """Liefert (Feldnummer, Wire-Typ, Wert) – bei Wire-Typ 2 ist der Wert (start, end).
    Wirft ValueError bei ungültigen Daten."""
    pos = start
    while pos < end:
        key, pos = _read_varint(buf, pos, end)
        field_no, wire = key >> 3, key & 7
        if wire == 0:
            value, pos = _read_varint(buf, pos, end)
            yield field_no, 0, value
        elif wire == 1:
            if pos + 8 > end:
                raise ValueError
            yield field_no, 1, int.from_bytes(buf[pos:pos + 8], "little")
            pos += 8
        elif wire == 2:
            length, pos = _read_varint(buf, pos, end)
            if pos + length > end:
                raise ValueError
            yield field_no, 2, (pos, pos + length)
            pos += length
        elif wire == 5:
            if pos + 4 > end:
                raise ValueError
            yield field_no, 5, None
            pos += 4
        else:
            raise ValueError


def values_at(buf, rng, path, mode="scalar"):
    """Alle Werte am Feldpfad innerhalb von buf[rng]. Wiederholte Felder werden alle durchlaufen."""
    head, rest = path[0], path[1:]
    for field_no, wire, value in iter_fields(buf, *rng):
        if field_no != head:
            continue
        if rest:
            if wire == 2:
                yield from values_at(buf, value, rest, mode)
        elif mode == "scalar" and wire in (0, 1):
            yield value
        elif mode == "fixed64_list" and wire == 2:
            start, end = value
            if (end - start) % 8 == 0:
                for i in range(start, end, 8):
                    yield int.from_bytes(buf[i:i + 8], "little")


def _string(buf, rng):
    return bytes(buf[rng[0]:rng[1]]).decode("utf-8", "replace")


# ---------------------------------------------------------------------------
# Sammeln
# ---------------------------------------------------------------------------

class MissingCollector:
    """Sammelt IDs ≥ 2^32, die nicht in known stehen, mit Fundorten."""

    def __init__(self, known):
        self.known = known
        self.items = {}

    def add(self, value, kind, where, source):
        if value < MIN_CC_ID or value in self.known:
            return
        item = self.items.setdefault(value, {"id": value, "kind": kind, "where": Counter(), "sources": set()})
        item["where"][where] += 1
        item["sources"].add(source)

    def result(self):
        rows = []
        for item in self.items.values():
            rows.append({
                "id": f"0x{item['id']:016X}",
                "art": item["kind"],
                "verwendet_von": [f"{w} ({n}×)" if n > 1 else w for w, n in item["where"].most_common()],
                "anzahl": sum(item["where"].values()),
                "quellen": sorted(item["sources"]),
            })
        return sorted(rows, key=lambda r: (-r["anzahl"], r["id"]))


def _scan_sim(buf, rng, collector, source, prefix=""):
    first = last = ""
    for field_no, wire, value in iter_fields(buf, *rng):
        if wire == 2 and field_no == 5:
            first = _string(buf, value)
        elif wire == 2 and field_no == 6:
            last = _string(buf, value)
    name = f"{prefix}{(first + ' ' + last).strip() or 'Sim ohne Namen'}"
    for path, mode in SIM_CAS_PATHS:
        for value in values_at(buf, rng, path, mode):
            collector.add(value, "CAS-Teil", name, source)
    for value in values_at(buf, rng, SIM_INVENTORY_PATH):
        collector.add(value, "Objekt", f"Inventar von {name}", source)


def scan_save(path, collector):
    """Durchsucht einen Spielstand nach fehlender CC."""
    source = os.path.basename(path)
    entries = dbpf.read_index(path)
    zone_names = {}

    for entry in entries:
        if entry.type != dbpf.TYPE_SAVEGAME_DATA:
            continue
        data = dbpf.read_resource(path, entry)
        buf = memoryview(data)
        try:
            top = list(iter_fields(buf, 0, len(data)))
        except ValueError:
            log.warning("Spielstand-Daten in %s nicht lesbar", source)
            continue
        for field_no, wire, value in top:
            if wire != 2:
                continue
            try:
                if field_no == 6:
                    _scan_sim(buf, value, collector, source)
                elif field_no == 5:
                    hh_name = next((_string(buf, v) for f, w, v in iter_fields(buf, *value) if f == 3 and w == 2), "")
                    for obj in values_at(buf, value, (6, 1, 30)):
                        collector.add(obj, "Objekt", f"Haushaltsinventar {hh_name}".strip(), source)
                elif field_no == 7:
                    zid = name = None
                    for f, w, v in iter_fields(buf, *value):
                        if f == 1 and w in (0, 1):
                            zid = v
                        elif f == 2 and w == 2:
                            name = _string(buf, v)
                    if zid is not None and name:
                        zone_names[zid] = name
                elif field_no == 8:
                    for obj in values_at(buf, value, (4, 1, 30)):
                        collector.add(obj, "Objekt", "Weitere Objekte im Spielstand", source)
            except ValueError:
                continue  # einzelner defekter Eintrag

    for entry in entries:
        if entry.type != 0x00000006:
            continue
        try:
            data = dbpf.read_resource(path, entry)
            lot = zone_names.get(entry.instance, f"Zone {entry.instance:X}")
            for obj in values_at(memoryview(data), (0, len(data)), (3, 1, 30)):
                collector.add(obj, "Objekt", f"Grundstück {lot}", source)
        except (ValueError, dbpf.DBPFError, Exception) as e:  # noqa: B014 – eine Zone darf nicht alles abbrechen
            log.debug("Zone %X in %s übersprungen: %s", entry.instance, source, e)


def _tray_names(tray_folder):
    names = {}
    for path in glob.glob(os.path.join(tray_folder, "*.trayitem")):
        try:
            with open(path, "rb") as f:
                data = f.read()
            buf = memoryview(data)
            for field_no, wire, value in iter_fields(buf, 8, len(data)):
                if field_no == 4 and wire == 2:
                    names[_tray_item_id(os.path.basename(path))] = _string(buf, value)
                    break
        except (OSError, ValueError):
            continue
    return names


def scan_tray(tray_folder, collector):
    """Durchsucht gespeicherte Haushalte der Bibliothek nach fehlender CC."""
    if not tray_folder or not os.path.isdir(tray_folder):
        return
    names = _tray_names(tray_folder)
    for path in glob.glob(os.path.join(tray_folder, "*.householdbinary")):
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            continue
        if len(data) <= 8:
            continue
        buf = memoryview(data)
        item_id = _tray_item_id(os.path.basename(path))
        label = f"Bibliothek „{names.get(item_id, item_id)}“: "
        try:
            for field_no, wire, value in iter_fields(buf, 8, len(data)):
                if field_no == 1 and wire == 2:
                    for f, w, sim in iter_fields(buf, *value):
                        if f == 6 and w == 2:
                            _scan_sim(buf, sim, collector, "Bibliothek", prefix=label)
        except ValueError:
            log.debug("Tray-Datei %s nicht lesbar", path)


def find_missing(save_paths, tray_folder, known, progress=None):
    """Gibt eine Liste fehlender CC zurück (siehe MissingCollector.result)."""
    collector = MissingCollector(known)
    for save in save_paths:
        if progress:
            progress(f"Fehlende CC: {os.path.basename(save)}")
        try:
            scan_save(save, collector)
        except (dbpf.DBPFError, OSError) as e:
            log.error("Spielstand %s nicht lesbar: %s", save, e)
    if tray_folder:
        if progress:
            progress("Fehlende CC: Bibliothek")
        scan_tray(tray_folder, collector)
    return collector.result()


# ---------------------------------------------------------------------------
# Spielordner (EA-Inhalte) – optional, macht die Erkennung absolut sicher
# ---------------------------------------------------------------------------

def find_game_folder():
    for parent in GAME_FOLDER_PARENTS:
        for name in GAME_FOLDER_NAMES:
            path = os.path.join(parent, name)
            if os.path.isdir(os.path.join(path, "Data", "Client")):
                return path
    return ""


def index_game_content(game_folder, cache_path=None, progress=None):
    """Liest die IDs aller CAS-Teile und Objekte des Spiels (≥ 2^32) aus dem Spielordner.
    Das Ergebnis wird zwischengespeichert, solange sich der Spielordner nicht ändert."""
    packages = glob.glob(os.path.join(game_folder, "**", "*.package"), recursive=True)
    stats = [os.stat(p) for p in packages]
    signature = [len(packages), sum(s.st_size for s in stats), max((int(s.st_mtime) for s in stats), default=0)]

    if cache_path and os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache = json.load(f)
            if cache.get("folder") == game_folder and cache.get("signature") == signature:
                return set(cache["ids"])
        except (OSError, ValueError, KeyError):
            pass

    ids = set()
    for i, path in enumerate(packages, 1):
        if progress and i % 200 == 0:
            progress(f"Spielordner: {i}/{len(packages)} Pakete")
        try:
            for entry in dbpf.read_index(path):
                if entry.type in dbpf.CONTENT_TYPES and entry.instance >= MIN_CC_ID:
                    ids.add(entry.instance)
        except (dbpf.DBPFError, OSError):
            continue

    if cache_path:
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump({"folder": game_folder, "signature": signature, "ids": sorted(ids)}, f)
        except OSError:
            pass
    return ids

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
# Die Vorschaubilder der Einträge (.hhi/.bpi/.rmi/.sgi) werden über thumbnails.py gelesen.

import os
import re
import json
import glob
import logging
from collections import Counter
from datetime import datetime, timedelta
from urllib.parse import quote_plus

import dbpf
from savegame_analyzer import _read_varint, _tray_item_id

log = logging.getLogger(__name__)

MIN_CC_ID = 1 << 32

SIM_INVENTORY_PATH = (20, 1, 30)

# Steckplätze (BodyType) der CAS-Teile. Abgeglichen an installierter CC in echten Spielständen
# (2 Haare, 5 Ganzkörper, 6 Oberteil, 7 Unterteil, 8 Schuhe, 10 Ohrringe, 29–33 Make-up …).
# Creator nutzen freie Steckplätze oft für anderes (z. B. Flügel auf einem Ring-Steckplatz).
BODY_TYPES = {
    1: "Hut/Kopfschmuck", 2: "Haare", 3: "Kopf", 4: "Zähne", 5: "Ganzkörper-Outfit", 6: "Oberteil",
    7: "Unterteil", 8: "Schuhe", 9: "Accessoire", 10: "Ohrringe", 11: "Brille", 12: "Halskette",
    13: "Handschuhe", 14: "Armband links", 15: "Armband rechts", 16: "Lippenpiercing links",
    17: "Lippenpiercing rechts", 18: "Nasenpiercing links", 19: "Nasenpiercing rechts",
    20: "Augenbrauenpiercing links", 21: "Augenbrauenpiercing rechts", 22: "Ring Zeigefinger links",
    23: "Ring Zeigefinger rechts", 24: "Ring Ringfinger links", 25: "Ring Ringfinger rechts",
    26: "Ring Mittelfinger links", 27: "Ring Mittelfinger rechts", 28: "Bart", 29: "Lippenstift",
    30: "Lidschatten", 31: "Eyeliner/Wimpern", 32: "Rouge", 33: "Gesichtsbemalung", 34: "Augenbrauen",
    35: "Augenfarbe", 36: "Socken", 37: "Mascara", 42: "Strumpfhose", 58: "Hautüberlagerung",
}
for _bt in list(range(38, 42)) + [43, 44, 55, 56, 57]:
    BODY_TYPES[_bt] = "Hautdetail"
for _bt in range(45, 55):
    BODY_TYPES[_bt] = "Tattoo"


def body_type_name(bt):
    if bt is None:
        return "CAS-Teil"
    return f"{BODY_TYPES.get(bt, 'CAS-Teil')} (Steckplatz {bt})"


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

    def add(self, value, kind, where, source, slot=None, group=None):
        """group: Gruppierung für die Übersicht (z. B. Bibliotheks-Haushalt oder Spielstand)."""
        if value < MIN_CC_ID or value in self.known:
            return
        item = self.items.setdefault(value, {"id": value, "kind": kind, "where": Counter(), "sources": set(),
                                             "slots": Counter(), "groups": set()})
        item["where"][where] += 1
        item["sources"].add(source)
        if slot is not None:
            item["slots"][slot] += 1
        if group:
            item["groups"].add(group)

    def result(self):
        rows = []
        for item in self.items.values():
            slot = item["slots"].most_common(1)[0][0] if item["slots"] else None
            rows.append({
                "id": f"0x{item['id']:016X}",
                "art": body_type_name(slot) if item["kind"] == "CAS-Teil" else item["kind"],
                "steckplatz": slot,
                "gruppen": sorted(item["groups"]),
                "verwendet_von": [f"{w} ({n}×)" if n > 1 else w for w, n in item["where"].most_common()],
                "anzahl": sum(item["where"].values()),
                "quellen": sorted(item["sources"]),
            })
        return sorted(rows, key=lambda r: (-r["anzahl"], r["id"]))


def _packed_varints(buf, rng):
    values, pos = [], rng[0]
    while pos < rng[1]:
        value, pos = _read_varint(buf, pos, rng[1])
        values.append(value)
    return values


def sim_cas_parts(buf, rng):
    """Alle CAS-Teile eines Sims als (ID, Steckplatz) – aus den Outfits (Feld 21) und der
    Grundausstattung (Feld 28: Frisur, Augenbrauen, Augenfarbe, Hautdetails …)."""
    for field_no, wire, value in iter_fields(buf, *rng):
        if wire != 2:
            continue
        if field_no == 21:
            for f, w, outfit in iter_fields(buf, *value):
                if f != 1 or w != 2:
                    continue
                parts, types = [], []
                for pf, pw, pv in iter_fields(buf, *outfit):
                    if pw != 2:
                        continue
                    for lf, lw, lv in iter_fields(buf, *pv):
                        if lf == 1 and lw == 2:
                            if pf == 5 and (lv[1] - lv[0]) % 8 == 0:
                                parts = [int.from_bytes(buf[i:i + 8], "little") for i in range(lv[0], lv[1], 8)]
                            elif pf == 7:
                                types = _packed_varints(buf, lv)
                if len(types) != len(parts):
                    types = [None] * len(parts)
                yield from zip(parts, types)
        elif field_no == 28:
            for f, w, lst in iter_fields(buf, *value):
                if f not in (5, 6) or w != 2:
                    continue
                for ef, ew, entry in iter_fields(buf, *lst):
                    if ef != 1 or ew != 2:
                        continue
                    vals = {a: x for a, c, x in iter_fields(buf, *entry) if c in (0, 1)}
                    if 1 in vals:
                        yield vals[1], vals.get(2)


def _scan_sim(buf, rng, collector, source, prefix="", group=None):
    first = last = ""
    for field_no, wire, value in iter_fields(buf, *rng):
        if wire == 2 and field_no == 5:
            first = _string(buf, value)
        elif wire == 2 and field_no == 6:
            last = _string(buf, value)
    name = f"{prefix}{(first + ' ' + last).strip() or 'Sim ohne Namen'}"
    for value, slot in sim_cas_parts(buf, rng):
        collector.add(value, "CAS-Teil", name, source, slot=slot, group=group or source)
    for value in values_at(buf, rng, SIM_INVENTORY_PATH):
        collector.add(value, "Objekt", f"Inventar von {name}", source, group=group or source)


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


URL_PATTERN = re.compile(r"https?://[^\s<>\"']+")
TRAY_TYPES = {1: "Haushalt", 2: "Grundstück", 3: "Raum"}


def read_tray_items(tray_folder):
    """Liest Name, Ersteller, Beschreibung usw. aller Bibliothekseinträge (.trayitem).
    Aufbau: 8 Byte Kopf, dann Protobuf – 2 Typ, 4 Name, 5 Beschreibung, 7 Ersteller (Galerie-ID),
    11 Zeitpunkt (Sekunden seit Jahr 1), 15 ursprünglicher Ersteller bei Remixen."""
    items = {}
    if not tray_folder or not os.path.isdir(tray_folder):
        return items
    import thumbnails
    images = thumbnails.index_tray_images(tray_folder)
    for path in glob.glob(os.path.join(tray_folder, "*.trayitem")):
        try:
            with open(path, "rb") as f:
                data = f.read()
            if len(data) <= 8:
                continue
            buf = memoryview(data)
            info = {"id": _tray_item_id(os.path.basename(path)), "typ": "", "name": "", "beschreibung": "",
                    "ersteller": "", "original_ersteller": "", "datum": ""}
            for field_no, wire, value in iter_fields(buf, 8, len(data)):
                if wire == 2 and field_no in (4, 5, 7, 15):
                    key = {4: "name", 5: "beschreibung", 7: "ersteller", 15: "original_ersteller"}[field_no]
                    info[key] = _string(buf, value).strip()
                elif wire == 0 and field_no == 2:
                    info["typ"] = TRAY_TYPES.get(value, str(value))
                elif wire == 0 and field_no == 11 and value:
                    try:
                        # Sekunden ab 1.1.0001, um einen Tag versetzt (an echten Dateizeiten geprüft)
                        info["datum"] = (datetime(1, 1, 1) + timedelta(seconds=value, days=-1)).strftime("%Y-%m-%d")
                    except OverflowError:
                        pass
            info["links"] = URL_PATTERN.findall(info["beschreibung"])
            info["bild"] = images.get(info["id"].lower(), "")      # Vorschaubild (.hhi/.bpi/.rmi/.sgi)
            items[info["id"]] = info
        except (OSError, ValueError):
            continue
    return items


def _search_link(info):
    terms = " ".join(t for t in (info.get("ersteller"), info.get("name"), "sims 4 cc") if t)
    return "https://www.google.com/search?q=" + quote_plus(terms)


def scan_tray(tray_folder, collector, tray_items=None):
    """Durchsucht gespeicherte Haushalte der Bibliothek nach fehlender CC."""
    if not tray_folder or not os.path.isdir(tray_folder):
        return
    if tray_items is None:
        tray_items = read_tray_items(tray_folder)
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
        label = f"Bibliothek „{tray_items.get(item_id, {}).get('name') or item_id}“: "
        try:
            for field_no, wire, value in iter_fields(buf, 8, len(data)):
                if field_no == 1 and wire == 2:
                    for f, w, sim in iter_fields(buf, *value):
                        if f == 6 and w == 2:
                            _scan_sim(buf, sim, collector, "Bibliothek", prefix=label, group="tray:" + item_id)
        except ValueError:
            log.debug("Tray-Datei %s nicht lesbar", path)


def find_missing(save_paths, tray_folder, known, progress=None):
    """Sucht fehlende CC. Gibt {"teile": [...], "bibliothek": [...]} zurück:
    teile      – je fehlendem Teil: ID, Art/Steckplatz, wer es nutzt, Quellen
    bibliothek – je Bibliotheks-Haushalt mit fehlender CC: Name, Ersteller, Beschreibung,
                 Links aus der Beschreibung, Suchlink und die fehlenden Teile"""
    collector = MissingCollector(known)
    tray_items = read_tray_items(tray_folder) if tray_folder else {}
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
        scan_tray(tray_folder, collector, tray_items)
    parts = collector.result()

    households = {}
    for part in parts:
        for group in part["gruppen"]:
            if not group.startswith("tray:"):
                continue
            item_id = group[5:]
            info = tray_items.get(item_id, {"id": item_id, "name": item_id, "typ": "Haushalt", "beschreibung": "",
                                            "ersteller": "", "original_ersteller": "", "datum": "", "links": []})
            entry = households.setdefault(item_id, dict(info, fehlend=[], suche=_search_link(info)))
            entry["fehlend"].append({"id": part["id"], "art": part["art"]})
    overview = sorted(households.values(), key=lambda h: (-len(h["fehlend"]), h["name"].lower()))
    return {"teile": parts, "bibliothek": overview}


# ---------------------------------------------------------------------------
# Spielordner (EA-Inhalte) – optional, macht die Erkennung absolut sicher
# ---------------------------------------------------------------------------

def find_game_folder():
    """Sims-4-Installation automatisch finden (Registry, Steam, Epic, übliche Ordner) – siehe game_locator."""
    import game_locator
    return game_locator.find_game_folder()


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

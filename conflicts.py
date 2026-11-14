# Modul: conflicts.py
# Funktion: Prüft Konflikte im Mods-Ordner genau, statt sie nur zu melden.
#
# Ein "Konflikt" ist zunächst nur: dieselbe Ressource (Typ/Gruppe/Instanz) steckt in mehreren Paketen.
# Ob das schlimm ist, hängt davon ab, WIE sie sich überschneiden:
#
# - Doppelt:        der Inhalt ist Byte für Byte gleich und eine Datei steckt komplett in den anderen
#                   -> diese Datei ist überflüssig und kann weg
# - Überschneidung: der gemeinsame Inhalt ist gleich, aber jede Datei bringt noch eigene Teile mit
#                   -> harmlos, alles behalten
# - Konflikt:       gleiche Ressource, unterschiedlicher Inhalt (zwei Fassungen/Varianten)
#                   -> das Spiel nutzt nur eine davon; hier muss man sich entscheiden
# - Überschreibung: mehrere Mods ersetzen dasselbe Original-Teil des Spiels (Default-Replacement)
#
# Abgewogen wird mit den Spielständen: Werden die betroffenen Teile überhaupt benutzt, und wo?
#
# Bei einem echten Konflikt schaut SimVault in die CAS-Teile selbst:
# - gleicher Name, aber eine Datei hat das neuere CAS-Format -> das ist die aktualisierte Fassung, sie bleibt.
#   Die veralteten Doppel werden aus der anderen Datei entfernt (deren übriger Inhalt bleibt erhalten).
# - unterschiedliche Namen unter derselben ID -> zwei verschiedene CC, die sich gegenseitig verdecken
# - gleicher Name, gleiches Format -> dieselbe CC, nur anders gespeichert oder eine Variante (größer/kleiner …)

import os
import struct
import hashlib
import logging
from collections import defaultdict
from datetime import datetime

import dbpf

log = logging.getLogger(__name__)

RESTORE_SUBFOLDER = "SimVault_wiederhergestellt"
QUARANTINE_FOLDER = "SimVault_aussortiert"
EA_ID_LIMIT = 1 << 32


def _fingerprints(path, wanted=None):
    """{TGI: Fingerabdruck} für die Ressourcen eines Pakets (wanted = nur diese TGIs).
    Der schnelle Fingerabdruck ist der Hash der gespeicherten Bytes; _same() entpackt bei Bedarf."""
    result = {}
    entries = dbpf.read_index(path)
    with open(path, "rb") as f:
        for e in entries:
            if e.compression == dbpf.COMPRESSION_DELETED or (wanted is not None and e.tgi not in wanted):
                continue
            f.seek(e.offset)
            raw = f.read(e.file_size)
            result[e.tgi] = (e.mem_size, e.compression, hashlib.sha1(raw).digest(), e)
    return result


def _same(path_a, fp_a, path_b, fp_b):
    """True, wenn zwei Ressourcen denselben Inhalt haben (auch bei unterschiedlicher Kompression)."""
    if fp_a[:3] == fp_b[:3]:
        return True
    if fp_a[0] != fp_b[0]:          # unterschiedliche entpackte Größe
        return False
    try:
        return dbpf.read_resource(path_a, fp_a[3]) == dbpf.read_resource(path_b, fp_b[3])
    except Exception:               # nicht entpackbar -> lieber als unterschiedlich werten
        return False


def casp_info(data):
    """(Format-Version, interner Name) eines CAS-Teils – oder None, wenn die Daten nicht passen."""
    try:
        version = struct.unpack_from("<I", data, 0)[0]
        pos = 12                               # Version, Offset der Verweise, Anzahl Presets
        length = data[pos]
        pos += 1
        if length & 0x80:
            length = (length & 0x7F) | (data[pos] << 7)
            pos += 1
        name = data[pos:pos + length].decode("utf-16-be")
        if version > 0x200 or not name.isprintable():
            return None
        return version, name
    except (struct.error, IndexError, UnicodeDecodeError):
        return None


def _compare_parts(path_a, prints_a, path_b, prints_b, tgis):
    """Vergleicht die unterschiedlichen CAS-Teile zweier Dateien: welche hat das neuere Format,
    und sind es überhaupt dieselben Teile? Gibt ein Dict mit Zählern und den Versionen zurück."""
    out = {"neuer_a": 0, "neuer_b": 0, "gleich": 0, "andere_cc": 0, "version_a": 0, "version_b": 0}
    for tgi in tgis[:400]:
        if tgi[0] != dbpf.TYPE_CASP:
            continue
        try:
            a = casp_info(dbpf.read_resource(path_a, prints_a[tgi][3]))
            b = casp_info(dbpf.read_resource(path_b, prints_b[tgi][3]))
        except Exception:
            continue
        if not a or not b:
            continue
        if a[1] != b[1]:
            out["andere_cc"] += 1
            continue
        out["version_a"], out["version_b"] = max(out["version_a"], a[0]), max(out["version_b"], b[0])
        out["neuer_a" if a[0] > b[0] else "neuer_b" if b[0] > a[0] else "gleich"] += 1
    return out


def _looks_like_variants(a, b):
    """Zwei Dateinamen, die sich nur am Ende unterscheiden (z. B. "… bigger" / "… smaller")."""
    a, b = (os.path.splitext(os.path.basename(x))[0].lower() for x in (a, b))
    common = len(os.path.commonprefix([a, b]))
    return common >= 8 and common >= 0.6 * min(len(a), len(b))


def analyze_conflicts(mod_scan, id_usage=None, game_ids=None, progress=None):
    """Prüft alle Überschneidungen im Mods-Ordner.

    id_usage: {"saves": {ID: [Spielstände]}, "tray": {ID: Anzahl}} aus analyze_usage (optional)
    game_ids: IDs der Original-Inhalte des Spiels (optional, erkennt Überschreibungen sicherer)

    Gibt {"konflikte": [...], "entfernbar": [...], "geprueft": bool} zurück. Jeder Konflikt:
      art, dateien, teile, identisch, unterschiedlich, genutzt, spielstaende, bibliothek, empfehlung, entfernbar
    """
    id_usage = id_usage or {}
    used_saves = id_usage.get("saves") or {}
    used_tray = id_usage.get("tray") or {}
    game_ids = game_ids or set()
    mods = {m.rel_path: m for m in mod_scan.mods if m.kind == "package" and m.category != "Defekt"}

    # 1. Welche Dateien teilen sich CAS-/Objekt-Ressourcen?
    owners = defaultdict(set)
    for mod in mods.values():
        for tgi in mod.content_tgis:
            owners[tgi].add(mod.rel_path)
    groups = defaultdict(list)             # (Datei, Datei, ...) -> gemeinsame CAS-/Objekt-TGIs
    for tgi, files in owners.items():
        if len(files) > 1:
            groups[tuple(sorted(files))].append(tgi)
    involved = sorted({f for files in groups for f in files})
    if not involved:
        return {"konflikte": [], "entfernbar": [], "geprueft": True}

    # 2. Inhalt aller Ressourcen der beteiligten Dateien einlesen (alle Typen, nicht nur CAS/Objekt –
    #    nur so lässt sich sagen, ob eine Datei wirklich komplett in einer anderen steckt)
    prints = {}
    for i, rel in enumerate(involved, 1):
        if progress:
            progress(f"Konflikte prüfen: {i}/{len(involved)} {os.path.basename(rel)}")
        try:
            prints[rel] = _fingerprints(mods[rel].path)
        except (dbpf.DBPFError, OSError) as e:
            log.warning("%s nicht lesbar: %s", rel, e)
            prints[rel] = {}
    where = defaultdict(list)              # TGI -> Dateien, die sie enthalten
    for rel, fp in prints.items():
        for tgi in fp:
            where[tgi].append(rel)

    def same(tgi, a, b):
        return _same(mods[a].path, prints[a][tgi], mods[b].path, prints[b][tgi])

    # 3. Überflüssige Dateien: jede Ressource steckt mit gleichem Inhalt in einer anderen, verbleibenden Datei.
    #    Kleine Dateien zuerst (Einzelpaket steckt im Set), bei Gleichstand zuerst die von SimVault zurückgeholte.
    removable = {}
    order = sorted(involved, key=lambda r: (len(prints[r]), RESTORE_SUBFOLDER.lower() not in r.lower(), r.lower()))
    for rel in order:
        if not prints[rel]:
            continue
        covered_by = set()
        for tgi in prints[rel]:
            other = next((o for o in where[tgi] if o != rel and o not in removable and same(tgi, rel, o)), None)
            if other is None:
                covered_by = None
                break
            covered_by.add(other)
        if covered_by:
            removable[rel] = sorted(covered_by)
    # "steckt in" nur mit Dateien angeben, die am Ende wirklich bleiben (A steckt in B, B in C -> beide stecken in C)
    for rel in removable:
        keepers = set()
        for tgi in prints[rel]:
            keepers.add(next(o for o in where[tgi] if o not in removable and same(tgi, rel, o)))
        removable[rel] = sorted(keepers)

    # 4. Jede Überschneidung einordnen und mit den Spielständen abwägen
    conflicts = []
    solvable = []
    for files, tgis in groups.items():
        first = files[0]
        differing = [t for t in tgis if not all(t in prints[f] and same(t, first, f) for f in files[1:])]
        different = len(differing)
        identical = len(tgis) - different
        instances = {t[2] for t in tgis}
        saves = sorted({s for i in instances for s in used_saves.get(i, [])})
        in_tray = any(used_tray.get(i) for i in instances)
        used = sum(1 for i in instances if used_saves.get(i) or used_tray.get(i))
        overrides = sum(1 for i in instances if i < EA_ID_LIMIT or i in game_ids)
        gone = [f for f in files if f in removable]
        name = os.path.basename
        solution = None

        if different == 0 and gone:
            art = "Doppelt"
            parts = [f"{name(f)} steckt komplett in {', '.join(name(o) for o in removable[f])}" for f in gone]
            advice = "; ".join(parts) + (" – kann weg" if len(gone) == 1 else " – können weg") \
                + ", es geht nichts verloren."
        elif different == 0:
            art = "Überschneidung"
            advice = ("Der gemeinsame Inhalt ist identisch – harmlos. Jede Datei bringt daneben eigene Teile mit, "
                      "also alle behalten.")
        else:
            art = "Überschreibung" if overrides else "Konflikt"
            # Welche Datei steckt (dem Inhaltsverzeichnis nach) komplett in den anderen der Gruppe?
            inside = [f for f in files if prints[f] and
                      all(any(o != f and t in prints[o] for o in files) for t in prints[f])]
            cmp = None
            if len(files) == 2 and not overrides:
                cmp = _compare_parts(mods[files[0]].path, prints[files[0]], mods[files[1]].path, prints[files[1]],
                                     differing)
            keeper = loser = None
            if cmp and not cmp["andere_cc"]:
                if cmp["neuer_a"] and not cmp["neuer_b"]:
                    keeper, loser, v_new, v_old = files[0], files[1], cmp["version_a"], cmp["version_b"]
                elif cmp["neuer_b"] and not cmp["neuer_a"]:
                    keeper, loser, v_new, v_old = files[1], files[0], cmp["version_b"], cmp["version_a"]
            if overrides:
                advice = (f"{len(files)} Mods ersetzen dasselbe Original-Teil des Spiels – nur eine Fassung "
                          "kann gelten. Die behalten, deren Aussehen du willst.")
            elif keeper:
                shared = [t for t in prints[loser] if t in prints[keeper]]
                advice = (f"Dieselbe CC in zwei Fassungen: {name(keeper)} ist die aktuellere "
                          f"(CAS-Format {v_new} statt {v_old}). ")
                if loser in inside:
                    advice += f"{name(loser)} steckt komplett darin und kann weg."
                    solution = {"aktion": "aussortieren", "verlierer": loser, "behalten": keeper,
                                "ressourcen": len(shared)}
                else:
                    advice += (f"Die {len(shared)} veralteten Doppel können aus {name(loser)} entfernt werden – "
                               f"alles andere in {name(loser)} bleibt.")
                    solution = {"aktion": "bereinigen", "verlierer": loser, "behalten": keeper,
                                "ressourcen": len(shared)}
            elif cmp and cmp["andere_cc"]:
                advice = (f"{cmp['andere_cc']} Teil(e) sind verschiedene CC mit derselben ID – eine verdeckt die "
                          "andere. Lösen lässt sich das nur, indem eine der beiden Dateien entfernt wird.")
            elif len(files) == 2 and _looks_like_variants(*files):
                advice = ("Zwei Varianten derselben CC (gleiche Teile, anderer Inhalt) – nur eine behalten, "
                          "sonst entscheidet die Ladereihenfolge.")
            else:
                advice = (f"Dieselbe CC, aber {different} Teil(e) sind unterschiedlich gespeichert "
                          "(z. B. nachträglich bearbeitet) – das Spiel nutzt nur eine Fassung. ")
                if inside:
                    advice += (f"{name(inside[0])} steckt komplett in "
                               f"{', '.join(name(f) for f in files if f != inside[0])} – am einfachsten "
                               f"{name(inside[0])} entfernen.")
                else:
                    advice += "Eine der Dateien entfernen; welche sonst gilt, hängt von der Ladereihenfolge ab."
            for f in gone:
                if not solution or f != solution["verlierer"]:
                    advice += (f" {name(f)} ist ohnehin überflüssig (steckt identisch in "
                               f"{', '.join(name(o) for o in removable[f])}).")
            if used:
                advice += (" Wichtig: Das Teil ist in Benutzung." if len(tgis) == 1 else
                           f" Wichtig: {used} dieser Teile {'ist' if used == 1 else 'sind'} in Benutzung.")
            elif id_usage:
                advice += " Aktuell wird davon nichts benutzt – eilt also nicht."
            if solution and solution["verlierer"] not in removable:
                solvable.append(solution)

        conflicts.append({
            "art": art, "dateien": list(files), "namen": [name(f) for f in files], "teile": len(tgis),
            "identisch": identical, "unterschiedlich": different,
            "genutzt": used, "spielstaende": saves, "bibliothek": in_tray,
            "empfehlung": advice, "entfernbar": gone, "loesung": solution,
        })

    rank = {"Konflikt": 0, "Überschreibung": 1, "Doppelt": 2, "Überschneidung": 3}
    conflicts.sort(key=lambda c: (rank[c["art"]], -c["genutzt"], -c["teile"]))
    return {"konflikte": conflicts, "geprueft": True, "aufloesbar": solvable,
            "entfernbar": [{"datei": f, "steckt_in": o, "groesse": mods[f].size} for f, o in removable.items()]}


def quarantine(mods_folder, rel_paths, target_base):
    """Verschiebt Dateien aus dem Mods-Ordner nach <target_base>/SimVault_aussortiert/<Zeit>/ (Unterordner bleiben
    erhalten). Es wird nichts gelöscht – zum Rückgängigmachen einfach zurückschieben.
    Gibt (Zielordner, verschoben, [(Datei, Grund)]) zurück."""
    import shutil
    target = os.path.join(target_base, QUARANTINE_FOLDER, datetime.now().strftime("%Y%m%d_%H%M%S"))
    moved, failed = [], []
    for rel in rel_paths:
        source = os.path.join(mods_folder, rel)
        dest = os.path.join(target, rel)
        try:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.move(source, dest)
            moved.append(rel)
        except OSError as e:
            failed.append((rel, str(e)))
    return target, moved, failed


def strip_shared(mods_folder, loser, keeper, backup_dir):
    """Entfernt aus dem Paket loser alle Ressourcen, die auch in keeper stecken (dort gilt die aktuellere Fassung).
    Das Original von loser wird vorher nach backup_dir kopiert. Gibt die Anzahl entfernter Ressourcen zurück."""
    import shutil
    loser_path, keeper_path = os.path.join(mods_folder, loser), os.path.join(mods_folder, keeper)
    keep_tgis = {e.tgi for e in dbpf.read_index(keeper_path) if e.compression != dbpf.COMPRESSION_DELETED}
    entries = [e for e in dbpf.read_index(loser_path) if e.compression != dbpf.COMPRESSION_DELETED]
    remaining = [e for e in entries if e.tgi not in keep_tgis]
    removed = len(entries) - len(remaining)
    if not removed:
        return 0
    backup = os.path.join(backup_dir, loser)
    if not os.path.exists(backup):          # bei mehreren Durchgängen das echte Original behalten
        os.makedirs(os.path.dirname(backup), exist_ok=True)
        shutil.copy2(loser_path, backup)
    if not remaining:                       # nichts Eigenes übrig: die Datei ist damit ganz überflüssig
        os.remove(loser_path)               # (das Original liegt im Backup)
        return removed
    tmp = loser_path + ".simvault_tmp"
    try:
        dbpf.rebuild_package(loser_path, tmp, remaining)
        if len(dbpf.read_index(tmp)) != len(remaining):
            raise dbpf.DBPFError("Gegenprobe fehlgeschlagen")
        os.replace(tmp, loser_path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return removed


def resolve(mods_folder, result, quarantine_base, backup_folder):
    """Räumt auf, was sich sicher auflösen lässt:
    1. überflüssige Dateien (stecken identisch in anderen) -> aussortieren
    2. veraltete Fassungen: Datei aussortieren, wenn sie komplett in der aktuelleren steckt,
       sonst nur die veralteten Doppel aus dem Paket entfernen (Original ins Backup)
    Gibt ein Dict zurück: ordner, verschoben, bereinigt [(Datei, Anzahl)], backup, fehler [(Datei, Grund)]."""
    out = {"ordner": None, "verschoben": [], "bereinigt": [], "backup": None, "fehler": []}
    to_move = [e["datei"] for e in result.get("entfernbar", [])]
    strips = []
    for sol in result.get("aufloesbar", []):
        if sol["verlierer"] in to_move or sol["behalten"] in to_move:
            continue
        if sol["aktion"] == "aussortieren":
            to_move.append(sol["verlierer"])
        else:
            strips.append(sol)
    if to_move:
        out["ordner"], out["verschoben"], out["fehler"] = quarantine(mods_folder, to_move, quarantine_base)
    if strips:
        out["backup"] = os.path.join(backup_folder, "konflikte_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
        for sol in strips:
            if sol["behalten"] in out["verschoben"]:
                continue
            try:
                out["bereinigt"].append((sol["verlierer"],
                                         strip_shared(mods_folder, sol["verlierer"], sol["behalten"], out["backup"])))
            except (dbpf.DBPFError, OSError) as e:
                out["fehler"].append((sol["verlierer"], str(e)))
    return out

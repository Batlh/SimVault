# Modul: repair.py
# Funktion: Prüft CC-Dateien und Spielstände auf Schäden und repariert, was sich sicher reparieren lässt.
#
# Was geht – und was ehrlich nicht:
#
# CC (.package)
# - falsch benanntes Archiv (ZIP/RAR/7z mit Endung .package): wird entpackt, die echten Pakete kommen daneben
# - einzelne kaputte Ressourcen in einem sonst lesbaren Paket: das Paket wird ohne sie neu geschrieben
#   (rettet z. B. den Rest eines Merges; dem betroffenen Teil kann danach Textur oder Form fehlen)
# - leere Datei, abgeschnittener Download, gespeicherte Webseite statt Datei: NICHT reparierbar –
#   die Daten sind schlicht nicht da. Hier hilft nur neu herunterladen (SimVault zeigt Suchlinks).
#
# Spielstände (.save)
# - Das Spiel legt von jedem Spielstand bis zu 5 ältere Fassungen an (.save.ver0 … .ver4).
#   Ist ein Spielstand kaputt, wird die neueste intakte Fassung zurückgeholt.
# - Einen kaputten Spielstand "von innen" flicken geht nicht zuverlässig – das wird nicht versucht.
#
# Vor jeder Reparatur wandert das Original in den Backup-Ordner (reparatur_<Zeit>). Es wird nie etwas gelöscht.

import os
import re
import shutil
import struct
import logging
import zipfile
import tempfile
from datetime import datetime

import dbpf
import archive_tools

log = logging.getLogger(__name__)

OK, BROKEN = "in Ordnung", "defekt"
REDOWNLOAD = "Nicht reparierbar – neu herunterladen."
VERSION_PATTERN = re.compile(r"\.save\.ver(\d+)$", re.I)


def _item(path, kind, base=None):
    return {"pfad": path, "datei": os.path.relpath(path, base) if base else os.path.basename(path), "typ": kind,
            "zustand": OK, "code": "", "problem": "", "loesung": "", "reparierbar": False}


def _bad(item, code, problem, solution, repairable=False):
    item.update(zustand=BROKEN, code=code, problem=problem, loesung=solution, reparierbar=repairable)
    return item


def _broken_resources(path, entries, should_stop=None):
    """Einträge, die sich nicht lesen/entpacken lassen."""
    size = os.path.getsize(path)
    bad = []
    with open(path, "rb") as f:
        for e in entries:
            if should_stop and should_stop():
                break
            if e.compression == dbpf.COMPRESSION_DELETED:
                continue
            if e.offset + e.file_size > size:
                bad.append(e)
                continue
            if e.compression == dbpf.COMPRESSION_NONE:
                continue
            f.seek(e.offset)
            try:
                dbpf.decompress(f.read(e.file_size), e.compression)
            except Exception:
                bad.append(e)
    return bad


# ---------------------------------------------------------------------------
# CC-Dateien
# ---------------------------------------------------------------------------

def check_package(path, deep=False, base=None, should_stop=None):
    """Prüft ein Paket. deep=True entpackt zusätzlich jede Ressource (findet Schäden mitten in der Datei)."""
    item = _item(path, "CC", base)
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            head = f.read(96)
    except OSError as e:
        return _bad(item, "lesefehler", f"Datei nicht lesbar: {e}", "Zugriffsrechte oder Datenträger prüfen.")
    if size == 0:
        return _bad(item, "leer", "Datei ist 0 Byte groß.", REDOWNLOAD)
    fmt = archive_tools.sniff(path)
    if fmt:
        return _bad(item, "archiv", f"Ist in Wahrheit ein {fmt[1:].upper()}-Archiv mit der Endung .package.",
                    "Reparatur entpackt das Archiv und legt die echten Pakete daneben.", True)
    if head.lstrip()[:1] == b"<":
        return _bad(item, "webseite", "Ist eine Webseite statt der Datei (Download fehlgeschlagen oder "
                                      "Anmeldung nötig).", REDOWNLOAD)
    if head[:4] != dbpf.DBPF_MAGIC:
        return _bad(item, "kein_paket", "Kein Sims-Paket (falscher Dateianfang).", REDOWNLOAD)
    major = struct.unpack_from("<I", head, 4)[0] if len(head) >= 8 else 0
    if major == 1:
        return _bad(item, "sims2", "Paket für Die Sims 2 – funktioniert nicht in Die Sims 4.",
                    "Aus dem Mods-Ordner entfernen.")
    try:
        entries = dbpf.read_index(path, strict=False)
    except dbpf.DBPFError as e:
        return _bad(item, "abgeschnitten", f"Inhaltsverzeichnis fehlt oder ist kaputt ({e}) – "
                                           "meist ein abgebrochener Download.", REDOWNLOAD)
    live = [e for e in entries if e.compression != dbpf.COMPRESSION_DELETED]
    if not live:
        return _bad(item, "ohne_inhalt", "Paket enthält keine Ressourcen.", "Aus dem Mods-Ordner entfernen.")
    beyond = [e for e in live if e.offset + e.file_size > size]
    bad = _broken_resources(path, live, should_stop) if deep else beyond
    if bad:
        return _damaged(item, live, bad)
    return item


def _damaged(item, live, bad):
    if len(bad) == len(live):
        return _bad(item, "alles_kaputt", "Keine einzige Ressource ist lesbar.", REDOWNLOAD)
    core = sum(1 for e in bad if e.type in dbpf.CONTENT_TYPES)
    note = (f" Darunter {core} CC-Eintrag/Einträge selbst – diese Teile verschwinden aus dem Spiel."
            if core else " Betroffene Teile können danach ohne Textur oder Form erscheinen.")
    return _bad(item, "ressourcen", f"{len(bad)} von {len(live)} Ressourcen sind beschädigt.",
                "Reparatur schreibt das Paket ohne die kaputten Ressourcen neu." + note, True)


def check_script(path, base=None):
    item = _item(path, "Script", base)
    try:
        if os.path.getsize(path) == 0:
            return _bad(item, "leer", "Datei ist 0 Byte groß.", REDOWNLOAD)
        with zipfile.ZipFile(path) as z:
            broken = z.testzip()
    except (zipfile.BadZipFile, OSError) as e:
        return _bad(item, "kein_script", f"Kein gültiges Script-Archiv ({e}).", REDOWNLOAD)
    if broken:
        return _bad(item, "script_kaputt", f"Datei im Script-Archiv beschädigt: {broken}", REDOWNLOAD)
    return item


def _backup(path, backup_dir, base=None):
    """Kopiert das Original in den Backup-Ordner und gibt den Zielpfad zurück."""
    rel = os.path.relpath(path, base) if base else os.path.basename(path)
    target = os.path.join(backup_dir, rel)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.copy2(path, target)
    return target


def repair_package(item, backup_dir, tools=(), base=None):
    """Repariert ein von check_package als reparierbar gemeldetes Paket. Gibt (ok, Meldung) zurück."""
    path = item["pfad"]
    if item["code"] == "archiv":
        return _unpack_misnamed(path, backup_dir, tools, base)
    if item["code"] != "ressourcen":
        return False, "nicht reparierbar"
    entries = [e for e in dbpf.read_index(path, strict=False) if e.compression != dbpf.COMPRESSION_DELETED]
    bad = {id(e) for e in _broken_resources(path, entries)}
    good = [e for e in entries if id(e) not in bad]
    if not good:
        return False, "keine lesbare Ressource übrig"
    _backup(path, backup_dir, base)
    tmp = path + ".simvault_tmp"
    try:
        dbpf.rebuild_package(path, tmp, good)
        if len(dbpf.read_index(tmp)) != len(good):       # Gegenprobe: neues Paket muss sauber lesbar sein
            raise dbpf.DBPFError("Gegenprobe fehlgeschlagen")
        os.replace(tmp, path)
    except (dbpf.DBPFError, OSError) as e:
        if os.path.exists(tmp):
            os.remove(tmp)
        return False, f"Neuschreiben fehlgeschlagen: {e}"
    return True, f"{len(good)} Ressourcen gerettet, {len(bad)} kaputte entfernt"


def _unpack_misnamed(path, backup_dir, tools, base):
    folder = os.path.dirname(path)
    fmt = archive_tools.sniff(path)
    with tempfile.TemporaryDirectory(prefix="simvault_rep_") as work:
        try:
            if fmt == ".zip":
                with zipfile.ZipFile(path) as z:
                    for name in z.namelist():
                        if name.lower().endswith(".package"):
                            z.extract(name, work)
            else:
                archive_tools.extract_relevant(path, work, list(tools), fmt)
        except (RuntimeError, zipfile.BadZipFile, OSError) as e:
            return False, f"Archiv lässt sich nicht entpacken: {e}"
        packages = [os.path.join(root, n) for root, _d, names in os.walk(work)
                    for n in names if n.lower().endswith(".package")]
        if not packages:
            return False, "im Archiv steckt kein Paket"
        # Original in den Backup-Ordner verschieben – sonst bliebe das falsche "Paket" im Mods-Ordner
        rel = os.path.relpath(path, base) if base else os.path.basename(path)
        moved_to = os.path.join(backup_dir, rel)
        os.makedirs(os.path.dirname(moved_to), exist_ok=True)
        shutil.move(path, moved_to)
        placed = 0
        for src in packages:
            target = os.path.join(folder, os.path.basename(src))
            if not os.path.exists(target):
                shutil.move(src, target)
                placed += 1
    return True, f"{placed} Paket(e) aus dem Archiv entpackt"


# ---------------------------------------------------------------------------
# Spielstände
# ---------------------------------------------------------------------------

def _save_error(path, deep=True, should_stop=None):
    """Leerer Text = Spielstand ist lesbar, sonst die Fehlerbeschreibung."""
    try:
        if os.path.getsize(path) == 0:
            return "Datei ist 0 Byte groß"
        entries = dbpf.read_index(path)
    except dbpf.DBPFError:
        return "Datei ist abgeschnitten oder kein Spielstand"
    except OSError as e:
        return f"nicht lesbar ({e})"
    data = [e for e in entries if e.type == dbpf.TYPE_SAVEGAME_DATA]
    if not data:
        return "enthält keine Spielstand-Daten"
    if not deep:
        return ""
    bad = _broken_resources(path, entries, should_stop)
    if bad:
        return f"{len(bad)} von {len(entries)} Datenblöcken lassen sich nicht entpacken"
    from missing_cc import iter_fields
    for e in data:              # Grundstruktur der eigentlichen Spielstand-Daten prüfen
        try:
            buf = dbpf.read_resource(path, e)
            for _field in iter_fields(buf, 0, len(buf)):
                pass
        except Exception:
            return "Spielstand-Daten sind in sich beschädigt"
    return ""


def save_versions(path):
    """Ältere Fassungen eines Spielstands (.ver0 = jüngste), als [(Pfad, Zeitpunkt)] – neueste zuerst."""
    folder, name = os.path.split(path)
    versions = []
    try:
        for other in os.listdir(folder):
            if other.lower().startswith(name.lower() + ".ver") and VERSION_PATTERN.search(other):
                full = os.path.join(folder, other)
                versions.append((full, os.path.getmtime(full)))
    except OSError:
        pass
    return sorted(versions, key=lambda v: v[1], reverse=True)


def check_save(path, deep=True, should_stop=None):
    item = _item(path, "Spielstand")
    error = _save_error(path, deep, should_stop)
    versions = save_versions(path)
    item["fassungen"] = len(versions)
    if not error:
        return item
    for version, mtime in versions:
        if not _save_error(version, deep, should_stop):
            when = datetime.fromtimestamp(mtime).strftime("%d.%m.%Y %H:%M")
            item["ersatz"] = version
            return _bad(item, "spielstand", f"Spielstand beschädigt: {error}.",
                        f"Reparatur holt die letzte intakte Fassung zurück ({os.path.basename(version)} "
                        f"vom {when}). Der Fortschritt danach geht verloren.", True)
    return _bad(item, "spielstand", f"Spielstand beschädigt: {error}.",
                "Keine intakte ältere Fassung vorhanden – nicht reparierbar. "
                "Falls du ein Backup der Spielstände hast, von dort zurückholen.")


def repair_save(item, backup_dir):
    """Ersetzt einen kaputten Spielstand durch seine letzte intakte Fassung. Gibt (ok, Meldung) zurück."""
    path, replacement = item["pfad"], item.get("ersatz")
    if not replacement or not os.path.isfile(replacement):
        return False, "keine intakte Fassung vorhanden"
    try:
        _backup(path, backup_dir)
        shutil.copy2(replacement, path)
    except OSError as e:
        return False, f"Zurückholen fehlgeschlagen: {e}"
    return True, f"ersetzt durch {os.path.basename(replacement)}"


# ---------------------------------------------------------------------------
# Alles prüfen / alles reparieren
# ---------------------------------------------------------------------------

def check_all(mods_folder, saves_folder, deep=False, progress=None, should_stop=None):
    """Prüft alle CC-Dateien und Spielstände. Gibt die Liste aller Einträge zurück (auch die intakten)."""
    from savegame_analyzer import find_saves
    files = []
    if mods_folder and os.path.isdir(mods_folder):
        for root, _dirs, names in os.walk(mods_folder):
            for name in names:
                if name.lower().endswith((".package", ".ts4script")):
                    files.append(os.path.join(root, name))
    items = []
    for i, path in enumerate(files, 1):
        if should_stop and should_stop():
            return items
        if progress and (i % 25 == 0 or deep):
            progress(f"Prüfe CC: {i}/{len(files)} {os.path.basename(path)}")
        if path.lower().endswith(".ts4script"):
            items.append(check_script(path, mods_folder))
        else:
            items.append(check_package(path, deep, mods_folder, should_stop))
    saves = find_saves(saves_folder) if saves_folder else []
    for i, path in enumerate(saves, 1):
        if should_stop and should_stop():
            return items
        if progress:
            progress(f"Prüfe Spielstand {i}/{len(saves)}: {os.path.basename(path)}")
        items.append(check_save(path, deep=True, should_stop=should_stop))
    return items


def repair_all(items, backup_folder, mods_folder=None, tools=(), progress=None):
    """Repariert alle reparierbaren Einträge. Gibt (Backup-Ordner, [(Datei, ok, Meldung)]) zurück."""
    todo = [it for it in items if it["zustand"] == BROKEN and it["reparierbar"]]
    if not todo:
        return None, []
    backup_dir = os.path.join(backup_folder, "reparatur_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    results = []
    for it in todo:
        if progress:
            progress(f"Repariere {it['datei']}")
        try:
            if it["typ"] == "Spielstand":
                ok, message = repair_save(it, os.path.join(backup_dir, "saves"))
            else:
                ok, message = repair_package(it, os.path.join(backup_dir, "Mods"), tools, mods_folder)
        except Exception as e:          # eine Datei darf die restlichen Reparaturen nicht verhindern
            log.exception("Reparatur von %s fehlgeschlagen", it["pfad"])
            ok, message = False, str(e)
        results.append((it["datei"], ok, message))
    return backup_dir, results

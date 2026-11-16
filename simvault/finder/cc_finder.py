# Modul: simvault/finder/cc_finder.py
# Funktion: "Fundgrube" – sucht fehlende CC auf dem eigenen PC.
#
# Durchsucht beliebige Ordner (alte Mods-Ordner, Downloads, Mod-Manager- und CurseForge-Ordner,
# Backups …) samt ZIP-Archiven nach .package-Dateien, die die gesuchten IDs enthalten.
# Gefundene Pakete können optional in den Mods-Ordner zurückgeholt werden
# (Unterordner "SimVault_wiederhergestellt", es wird nichts überschrieben).
#
# Laufwerke: Standardmäßig werden zusätzlich alle weiteren Laufwerke (D:, E:, USB-Sticks …)
# komplett durchsucht, Systemordner ausgenommen. Mit "ganzer PC" auch das Systemlaufwerk C:.
#
# Archive: ZIP wird direkt gelesen. RAR und 7z werden mit 7-Zip, WinRAR oder dem tar von
# Windows 10/11 kurz in einen Temp-Ordner entpackt (nur Pakete und verschachtelte Archive),
# durchsucht und danach wieder gelöscht. Archive in Archiven werden bis zu 3 Ebenen tief durchsucht.
# Was nicht geht (kein Entpacker, Passwort, zu groß, defekt), wird mit Grund gemeldet.

import os
import shutil
import logging
import tempfile
import zipfile

from simvault.analysis import dbpf
from simvault.finder import archive_tools

log = logging.getLogger(__name__)

RESTORE_SUBFOLDER = "SimVault_wiederhergestellt"
MAX_NESTING = 3
SKIP_DIRS = {"$recycle.bin", "system volume information", "node_modules", ".git", "__pycache__",
             # Systemordner beim Durchsuchen ganzer Laufwerke
             "windows", "program files", "program files (x86)", "programdata", "$windows.~bt", "$windows.~ws",
             "$winreagent", "recovery", "perflogs", "windowsapps", "msocache", "appdata"}

DRIVE_REMOVABLE = 2
DRIVE_FIXED = 3


def list_drives(include_system=False):
    """Alle lokalen Festplatten und USB-Laufwerke (nur Windows), z. B. ["D:\\", "E:\\"].
    Das Systemlaufwerk (meist C:) nur mit include_system=True."""
    if os.name != "nt":
        return []
    import ctypes
    import string
    kernel32 = ctypes.windll.kernel32
    system = os.environ.get("SystemDrive", "C:").upper().rstrip("\\") + "\\"
    mask = kernel32.GetLogicalDrives()
    drives = []
    for i, letter in enumerate(string.ascii_uppercase):
        if not mask & (1 << i):
            continue
        root = f"{letter}:\\"
        if kernel32.GetDriveTypeW(root) not in (DRIVE_FIXED, DRIVE_REMOVABLE):
            continue  # Netzlaufwerke, CD/DVD usw. auslassen
        if root.upper() == system and not include_system:
            continue
        drives.append(root)
    return drives


def default_search_folders(cfg):
    """Typische Orte, an denen alte oder heruntergeladene CC liegt. Gibt nur vorhandene Ordner zurück."""
    home = os.path.expanduser("~")
    docs_candidates = [os.path.join(home, "Documents"), os.path.join(home, "Dokumente")]
    active_mods = os.path.normcase(os.path.abspath(cfg.get("mods_folder") or ""))
    candidates = []
    for docs in docs_candidates:
        ea = os.path.join(docs, "Electronic Arts")
        if os.path.isdir(ea):
            for name in os.listdir(ea):  # andere Sims-4-Ordner (z. B. alter englischer Ordner)
                mods = os.path.join(ea, name, "Mods")
                if "4" in name and os.path.isdir(mods) and os.path.normcase(os.path.abspath(mods)) != active_mods:
                    candidates.append(mods)
        candidates += [os.path.join(docs, n) for n in
                       ("Sims 4 Mod Manager Data", "MEGAsync Downloads", "Curse", "My Curse")]
    candidates += [os.path.join(home, n) for n in ("Downloads", "Desktop", "curseforge")]
    seen, result = set(), []
    for path in candidates:
        key = os.path.normcase(os.path.abspath(path))
        if os.path.isdir(path) and key not in seen:
            seen.add(key)
            result.append(path)
    return result


def search_locations(cfg, folders=None, drives=True, whole_pc=False):
    """Ordner für die Suche: angegebene Ordner oder die Standard-Orte, plus Laufwerke."""
    locations = list(folders or cfg.get("search_folders") or default_search_folders(cfg))
    if drives or whole_pc:
        locations += list_drives(include_system=whole_pc)
    seen, result = set(), []
    for path in locations:
        key = os.path.normcase(os.path.abspath(path))
        if os.path.isdir(path) and key not in seen:
            seen.add(key)
            result.append(path)
    # Ordner weglassen, die schon in einem durchsuchten Laufwerk/Ordner stecken
    keys = [os.path.normcase(os.path.abspath(p)) for p in result]
    return [p for p, k in zip(result, keys)
            if not any(k != o and k.startswith(o.rstrip("\\/") + os.sep) for o in keys)]


def _ids_in_entries(entries, wanted):
    return {e.instance for e in entries if e.instance in wanted}


# Ganze Wörter, die klar auf Sims hindeuten. Allgemeine Wörter wie "mod" oder "patreon"
# gehören nicht dazu – sonst landen z. B. Mass-Effect-Mods in der Sims-Liste.
SIMS_WORDS = {"sims", "sims4", "ts4", "s4", "cc", "package", "tray", "wickedwhims", "wicked", "mccc",
              "tsr", "cas", "mcas", "simfileshare", "mts", "modthesims", "nraas", "lumpinou", "basemental"}
SIMS_PREFIXES = ("sims4", "thesims", "ts4", "s4cc", "s4_", "wickedwhims")


def looks_like_sims(path):
    """Grobe Einschätzung, ob ein (nicht lesbares) Archiv Sims-Inhalte enthalten könnte."""
    import re
    low = path.lower()
    words = [w for w in re.split(r"[^a-z0-9]+", low) if w]
    return any(w in SIMS_WORDS for w in words) or any(p in low for p in SIMS_PREFIXES)


TEMP_PREFIX = "simvault_fund_"
FREE_SPACE_RESERVE = 1024 ** 3   # mindestens 1 GB frei lassen
STALE_TEMP_SECONDS = 30 * 60


def cleanup_stale_temp(base=None):
    """Löscht Temp-Ordner früherer, abgebrochener Suchläufe (älter als 30 Minuten)."""
    import time
    base = base or tempfile.gettempdir()
    removed = 0
    try:
        names = os.listdir(base)
    except OSError:
        return 0
    for name in names:
        path = os.path.join(base, name)
        if name.startswith(TEMP_PREFIX) and os.path.isdir(path):
            try:
                if time.time() - os.path.getmtime(path) > STALE_TEMP_SECONDS:
                    shutil.rmtree(path, ignore_errors=True)
                    removed += 1
            except OSError:
                pass
    return removed


class Cancelled(Exception):
    """Die Suche wurde vom Nutzer abgebrochen."""


def search(folders, wanted, exclude=(), progress=None, work_dir=None, tools=None, max_archive_mb=4096,
           keep_hits=False, should_stop=None):
    """Durchsucht folders nach Paketen mit IDs aus wanted.

    Speicherplatz: Jedes RAR/7z wird nur kurz entpackt und direkt danach wieder gelöscht –
    auch wenn etwas gefunden wurde. Nur mit keep_hits=True (für --restore) bleiben die
    gefundenen Pakete selbst im work_dir liegen, bis der Aufrufer es löscht.
    Vor jedem Entpacken wird geprüft, ob genug Platz frei ist.

    should_stop: Funktion ohne Argumente; liefert sie True, bricht die Suche mit Cancelled ab.

    Gibt (treffer, nicht_lesbar) zurück:
      treffer:      [{"pfad", "archiv_eintrag" (oder None), "ids": set, "groesse", "temp_datei"?}]
      nicht_lesbar: [{"pfad", "grund"}] – Archive, die nicht durchsucht werden konnten
    """
    if not wanted:
        return [], []
    own_work = work_dir is None
    if own_work:
        work_dir = tempfile.mkdtemp(prefix=TEMP_PREFIX)
    run = _Search(wanted, archive_tools.find_tools() if tools is None else tools, work_dir,
                  keep_hits, max_archive_mb, progress)
    excluded = {os.path.normcase(os.path.abspath(x)) for x in exclude if x}
    try:
        for folder in folders:
            if progress:
                progress(f"durchsuche {folder}")
            for root, dirs, files in os.walk(folder):
                dirs[:] = [d for d in dirs if d.lower() not in SKIP_DIRS
                           and os.path.normcase(os.path.abspath(os.path.join(root, d))) not in excluded]
                if should_stop and should_stop():
                    raise Cancelled()
                for name in files:
                    run.file(os.path.join(root, name))
    finally:
        if own_work and not keep_hits:
            shutil.rmtree(work_dir, ignore_errors=True)
    return run.hits, run.unreadable


def _chain(prefix, name):
    return f"{prefix} → {name}" if prefix else name


class _Search:
    def __init__(self, wanted, tools, work_dir, keep_hits, max_archive_mb, progress):
        self.wanted = wanted
        self.tools = tools
        self.work_dir = work_dir
        self.keep_hits = keep_hits
        self.max_bytes = max_archive_mb * 1024 * 1024
        self.progress = progress
        self.hits = []
        self.unreadable = []
        self.checked = 0

    def _fail(self, where, reason):
        self.unreadable.append({"pfad": where, "grund": reason, "sims": looks_like_sims(where)})

    def _space_ok(self, needed):
        try:
            return shutil.disk_usage(self.work_dir).free > needed + FREE_SPACE_RESERVE
        except OSError:
            return True

    def _kept_path(self, name):
        return os.path.join(tempfile.mkdtemp(dir=self.work_dir, prefix="f_"), os.path.basename(name))

    def _count(self):
        self.checked += 1
        if self.progress and self.checked % 500 == 0:
            self.progress(f"{self.checked} Pakete durchsucht")

    # -- Dateien auf der Platte -------------------------------------------------
    def file(self, path):
        low = path.lower()
        try:
            if low.endswith(".package"):
                self._count()
                ids = _ids_in_entries(dbpf.read_index(path), self.wanted)
                if ids:
                    self.hits.append({"pfad": path, "archiv_eintrag": None, "ids": ids,
                                      "groesse": os.path.getsize(path)})
            elif low.endswith(".zip"):
                try:
                    self.zip(path, path, "", 0)
                except zipfile.BadZipFile:
                    real = archive_tools.sniff(path)   # z. B. ein RAR mit der Endung .zip
                    if real in archive_tools.EXTERNAL_ARCHIVES:
                        self.external(path, path, "", 0, fmt=real)
                    else:
                        self._fail(path, "kein gültiges ZIP (beschädigt oder anderes Format)")
            elif low.endswith(archive_tools.EXTERNAL_ARCHIVES):
                self.external(path, path, "", 0)
        except (dbpf.DBPFError, OSError, zipfile.BadZipFile, RuntimeError, EOFError) as e:
            log.debug("%s übersprungen: %s", path, e)
            if low.endswith(".zip"):
                self._fail(path, f"ZIP nicht lesbar ({e})")

    # -- ZIP: direkt lesen, ohne zu entpacken -----------------------------------
    def zip(self, zip_path, outer, prefix, depth):
        with zipfile.ZipFile(zip_path) as z:
            for info in z.infolist():
                name, low = info.filename, info.filename.lower()
                if info.file_size == 0 or info.is_dir():
                    continue
                if low.endswith(".package"):
                    self._count()
                    try:
                        with z.open(info) as member:   # gestreamt – das Paket landet nicht im Arbeitsspeicher
                            ids = _ids_in_entries(dbpf.read_index_fileobj(member), self.wanted)
                    except (dbpf.DBPFError, RuntimeError, OSError, EOFError, zipfile.BadZipFile):
                        continue
                    if ids:
                        hit = {"pfad": outer, "archiv_eintrag": _chain(prefix, name), "ids": ids,
                               "groesse": info.file_size}
                        if prefix and self.keep_hits:  # verschachtelt: für --restore aufheben
                            target = self._kept_path(name)
                            with z.open(info) as src, open(target, "wb") as dst:
                                shutil.copyfileobj(src, dst)
                            hit["temp_datei"] = target
                        self.hits.append(hit)
                elif low.endswith((".zip",) + archive_tools.EXTERNAL_ARCHIVES) and depth < MAX_NESTING:
                    where = _chain(outer, _chain(prefix, name))
                    if not self._space_ok(info.file_size):
                        self._fail(where, "zu wenig freier Speicherplatz zum Prüfen")
                        continue
                    scratch = tempfile.mkdtemp(dir=self.work_dir, prefix="z_")
                    try:
                        inner = os.path.join(scratch, os.path.basename(name))
                        with z.open(info) as src, open(inner, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        self.nested(inner, outer, _chain(prefix, name), depth + 1)
                    finally:
                        shutil.rmtree(scratch, ignore_errors=True)   # Kopie sofort wieder weg

    def nested(self, path, outer, prefix, depth):
        try:
            real = archive_tools.sniff(path) or os.path.splitext(path)[1].lower()
            if real == ".zip":
                self.zip(path, outer, prefix, depth)
            else:
                self.external(path, outer, prefix, depth, fmt=real)
        except (zipfile.BadZipFile, OSError, RuntimeError, EOFError) as e:
            self._fail(_chain(outer, prefix), str(e))

    # -- RAR/7z: kurz entpacken, prüfen, sofort löschen -------------------------
    def external(self, archive, outer, prefix, depth, fmt=None):
        where = _chain(outer, prefix) if prefix else outer
        if not self.tools:
            self._fail(where, "kein Entpacker gefunden – 7-Zip installieren")
            return
        size = os.path.getsize(archive)
        if size > self.max_bytes:
            self._fail(where, f"größer als {self.max_bytes // (1024 * 1024)} MB – übersprungen")
            return
        if not self._space_ok(2 * size):
            self._fail(where, "zu wenig freier Speicherplatz zum Entpacken")
            return
        if self.progress:
            self.progress(f"entpacke {os.path.basename(archive)}")
        dest = tempfile.mkdtemp(dir=self.work_dir, prefix="x_")
        try:
            try:
                archive_tools.extract_relevant(archive, dest, self.tools, fmt=fmt or archive_tools.sniff(archive))
            except RuntimeError as e:
                self._fail(where, str(e))
                return
            for root, _dirs, files in os.walk(dest):
                for name in files:
                    path = os.path.join(root, name)
                    rel = os.path.relpath(path, dest)
                    low = name.lower()
                    try:
                        if low.endswith(".package"):
                            self._count()
                            ids = _ids_in_entries(dbpf.read_index(path), self.wanted)
                            if ids:
                                hit = {"pfad": outer, "archiv_eintrag": _chain(prefix, rel), "ids": ids,
                                       "groesse": os.path.getsize(path)}
                                if self.keep_hits:   # nur das gefundene Paket aufheben, nicht das ganze Archiv
                                    target = self._kept_path(name)
                                    shutil.move(path, target)
                                    hit["temp_datei"] = target
                                self.hits.append(hit)
                            else:
                                os.remove(path)      # geprüft, nichts drin: Platz sofort freigeben
                        elif low.endswith((".zip",) + archive_tools.EXTERNAL_ARCHIVES) and depth < MAX_NESTING:
                            self.nested(path, outer, _chain(prefix, rel), depth + 1)
                            os.remove(path)
                    except (dbpf.DBPFError, OSError):
                        continue
        finally:
            shutil.rmtree(dest, ignore_errors=True)   # entpackter Inhalt immer sofort weg


def summarize(hits, parts):
    """Ordnet die Treffer den fehlenden Teilen zu.
    parts: Liste aus find_missing()["teile"]. Gibt Treffer (sortiert, IDs als Hex) und die Anzahl
    der Teile zurück, die gefunden wurden."""
    by_id = {int(p["id"], 16): p for p in parts}
    grouped = {}  # gleiche Datei (Name + gefundene IDs) an mehreren Orten nur einmal aufführen
    found = set()
    for hit in hits:
        found |= hit["ids"]
        inner = (hit["archiv_eintrag"] or hit["pfad"]).split(" → ")[-1]   # letzte Stufe bei Verschachtelung
        name = os.path.basename(inner.replace("\\", "/"))
        key = (name.lower(), frozenset(hit["ids"]))
        where = f"{hit['pfad']} → {hit['archiv_eintrag']}" if hit["archiv_eintrag"] else hit["pfad"]
        if key in grouped:
            grouped[key]["weitere_fundorte"].append(where)
            continue
        users = sorted({u for i in hit["ids"] if i in by_id for u in by_id[i]["verwendet_von"]})
        grouped[key] = {
            "datei": name,
            "pfad": hit["pfad"],
            "archiv_eintrag": hit["archiv_eintrag"],
            "anzahl_ids": len(hit["ids"]),
            "ids": sorted(f"0x{i:016X}" for i in hit["ids"]),
            "arten": sorted({by_id[i]["art"].split(" (")[0] for i in hit["ids"] if i in by_id}),
            "verwendet_von": users,
            "groesse": hit["groesse"],
            "weitere_fundorte": [],
            "temp_datei": hit.get("temp_datei"),
        }
    result = sorted(grouped.values(), key=lambda r: (-r["anzahl_ids"], r["datei"].lower()))
    return result, len(found)


def fetch(outer, entry, target, tools=None, work_dir=None):
    """Holt eine gefundene Datei an ihren Zielort.
    outer: Datei auf der Platte; entry: Weg ins Archiv ("a.zip → b.rar → x.package") oder None."""
    if not entry:
        shutil.copy2(outer, target)
        return
    segments = entry.split(" → ")
    scratch = tempfile.mkdtemp(prefix=TEMP_PREFIX, dir=work_dir)
    try:
        current = outer
        for i, segment in enumerate(segments):
            last = i == len(segments) - 1
            dest = target if last else os.path.join(tempfile.mkdtemp(dir=scratch), os.path.basename(segment))
            if (archive_tools.sniff(current) or os.path.splitext(current)[1].lower()) == ".zip":
                with zipfile.ZipFile(current) as z, z.open(segment) as src, open(dest, "wb") as dst:
                    shutil.copyfileobj(src, dst)
            else:
                if tools is None:
                    tools = archive_tools.find_tools()
                archive_tools.extract_member(current, segment, dest, tools, work_dir=scratch)
            current = dest
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def plan_restore(found, installed_ids=(), exclude=()):
    """Wählt aus den Funden möglichst wenige Dateien, die alle noch fehlenden Teile abdecken.
    Teile, die schon im Mods-Ordner stecken, zählen nicht. Bei Gleichstand gewinnt die kleinere Datei
    (einzelnes Paket statt großem Set). Gibt (auswahl, [(Datei, Grund)] übersprungen) zurück."""
    patterns = [x.lower() for x in exclude if x]
    installed = set(installed_ids)
    candidates, skipped = [], []
    for item in found:
        haystack = f"{item['pfad']} {item.get('archiv_eintrag') or ''} {item['datei']}".lower()
        if any(p in haystack for p in patterns):
            skipped.append((item["datei"], "ausgelassen (--ohne)"))
            continue
        ids = {int(x, 16) if isinstance(x, str) else x for x in item.get("ids") or []}
        if not ids:                        # alter Bericht ohne ID-Liste: nicht aussortieren
            candidates.append((item, None))
            continue
        need = ids - installed
        if not need:
            skipped.append((item["datei"], "alle Teile sind schon im Mods-Ordner"))
            continue
        candidates.append((item, need))
    chosen = [item for item, need in candidates if need is None]
    rest = [(item, need) for item, need in candidates if need is not None]
    covered = set()
    while rest:
        rest.sort(key=lambda c: (-len(c[1] - covered), c[0].get("groesse") or 0))
        item, need = rest.pop(0)
        if not need - covered:
            skipped.append((item["datei"], "Teile kommen schon aus einer anderen Fund-Datei"))
            for other, _n in rest:
                skipped.append((other["datei"], "Teile kommen schon aus einer anderen Fund-Datei"))
            break
        chosen.append(item)
        covered |= need
    return chosen, skipped


def installed_ids(mods_folder):
    """Alle CC-IDs, die im Mods-Ordner schon vorhanden sind."""
    from simvault.analysis.mod_folder_scanner import scan_mods_folder
    ids = set()
    for mod in scan_mods_folder(mods_folder).mods:
        ids |= mod.match_ids
    return ids


def restore(found, mods_folder, exclude=(), tools=None, work_dir=None, progress=None, skipped=None):
    """Kopiert gefundene Pakete nach <Mods>/SimVault_wiederhergestellt. Überschreibt nichts.
    exclude: Textstücke – Funde, deren Datei oder Fundort eines davon enthält, werden übersprungen.
    Funde, deren Teile schon installiert sind oder von einer anderen Fund-Datei mitgebracht werden,
    werden nicht kopiert (landen in der Liste skipped, falls übergeben).
    Gibt (angelegt, fehlgeschlagen) zurück: Liste der neuen Dateien und [(Datei, Grund)]."""
    target_dir = os.path.join(mods_folder, RESTORE_SUBFOLDER)
    os.makedirs(target_dir, exist_ok=True)
    created, failed = [], []
    if progress:
        progress("prüfe, was schon im Mods-Ordner ist")
    chosen, left_out = plan_restore(found, installed_ids(mods_folder), exclude)
    if skipped is not None:
        skipped.extend(left_out)
    for item in chosen:
        target = os.path.join(target_dir, item["datei"])
        if os.path.exists(target):
            continue
        if progress:
            progress(f"hole {item['datei']}")
        if item.get("temp_datei") and os.path.isfile(item["temp_datei"]):
            shutil.copy2(item["temp_datei"], target)     # schon bei der Suche zwischengespeichert
            created.append(target)
            continue
        # erster Fundort, bei Problemen die weiteren Fundorte derselben Datei
        locations = [(item["pfad"], item.get("archiv_eintrag"))]
        for where in item.get("weitere_fundorte") or []:
            outer, _sep, entry = where.partition(" → ")
            locations.append((outer, entry or None))
        error = None
        for outer, entry in locations:
            try:
                fetch(outer, entry, target, tools, work_dir)
                error = None
                break
            except (OSError, RuntimeError, KeyError, zipfile.BadZipFile) as e:
                error = e
                if os.path.exists(target):
                    os.remove(target)
        if error is not None:
            failed.append((item["datei"], str(error)))
            log.error("%s konnte nicht zurückgeholt werden: %s", item["datei"], error)
            continue
        created.append(target)
    return created, failed

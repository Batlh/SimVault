# Modul: cc_finder.py
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

import dbpf
import archive_tools

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


def search(folders, wanted, exclude=(), progress=None, work_dir=None, tools=None, max_archive_mb=4096):
    """Durchsucht folders nach Paketen mit IDs aus wanted.

    work_dir: Temp-Ordner für entpackte RAR/7z-Inhalte. Treffer daraus bleiben dort liegen
              (für --restore), bis der Aufrufer den Ordner löscht.
    tools:    Entpacker aus archive_tools.find_tools() (None = automatisch suchen)

    Gibt (treffer, nicht_lesbar) zurück:
      treffer:      [{"pfad", "archiv_eintrag" (oder None), "ids": set, "groesse", "temp_datei"?}]
      nicht_lesbar: [{"pfad", "grund"}] – Archive, die nicht durchsucht werden konnten
    """
    hits, unreadable = [], []
    if not wanted:
        return hits, unreadable
    if tools is None:
        tools = archive_tools.find_tools()
    own_work = work_dir is None
    if own_work:
        work_dir = tempfile.mkdtemp(prefix="simvault_fund_")
    excluded = {os.path.normcase(os.path.abspath(x)) for x in exclude if x}
    checked = 0
    for folder in folders:
        if progress:
            progress(f"durchsuche {folder}")
        for root, dirs, files in os.walk(folder):
            dirs[:] = [d for d in dirs if d.lower() not in SKIP_DIRS
                       and os.path.normcase(os.path.abspath(os.path.join(root, d))) not in excluded]
            for name in files:
                path = os.path.join(root, name)
                low = name.lower()
                try:
                    if low.endswith(".package"):
                        checked += 1
                        ids = _ids_in_entries(dbpf.read_index(path), wanted)
                        if ids:
                            hits.append({"pfad": path, "archiv_eintrag": None, "ids": ids,
                                         "groesse": os.path.getsize(path)})
                    elif low.endswith(".zip"):
                        hits.extend(_search_zip(path, path, "", wanted, tools, work_dir, unreadable, 0, progress))
                    elif low.endswith(archive_tools.EXTERNAL_ARCHIVES):
                        if not tools:
                            unreadable.append({"pfad": path, "grund": "kein Entpacker gefunden – 7-Zip installieren"})
                        elif os.path.getsize(path) > max_archive_mb * 1024 * 1024:
                            unreadable.append({"pfad": path, "grund": f"größer als {max_archive_mb} MB – übersprungen"})
                        else:
                            hits.extend(_search_external(path, path, "", wanted, tools, work_dir, unreadable, 0,
                                                         progress))
                except (dbpf.DBPFError, OSError, zipfile.BadZipFile, RuntimeError) as e:
                    log.debug("%s übersprungen: %s", path, e)
                    if low.endswith(".zip"):
                        unreadable.append({"pfad": path, "grund": f"ZIP defekt oder geschützt ({e})"})
                if progress and checked and checked % 500 == 0:
                    progress(f"{checked} Pakete durchsucht")
    if own_work and not hits:
        shutil.rmtree(work_dir, ignore_errors=True)
    return hits, unreadable


def _chain(prefix, name):
    return f"{prefix} → {name}" if prefix else name


def _search_zip(zip_path, outer, prefix, wanted, tools, work_dir, unreadable, depth, progress=None):
    """Durchsucht ein ZIP. outer/prefix: Fundort für die Anzeige (äußeres Archiv und Weg hinein)."""
    hits = []
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            name = info.filename
            low = name.lower()
            if info.file_size == 0 or info.is_dir():
                continue
            if low.endswith(".package"):
                data = z.read(info)
                try:
                    ids = _ids_in_entries(dbpf.read_index_bytes(data), wanted)
                except dbpf.DBPFError:
                    continue
                if ids:
                    hit = {"pfad": outer, "archiv_eintrag": _chain(prefix, name), "ids": ids,
                           "groesse": info.file_size}
                    if prefix:  # liegt in einem verschachtelten Archiv: für --restore zwischenspeichern
                        hit["temp_datei"] = _keep(data, name, work_dir)
                    hits.append(hit)
            elif low.endswith((".zip",) + archive_tools.EXTERNAL_ARCHIVES) and depth < MAX_NESTING:
                inner = os.path.join(tempfile.mkdtemp(dir=work_dir, prefix="z_"), os.path.basename(name))
                with z.open(info) as src, open(inner, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                hits.extend(_search_nested(inner, outer, _chain(prefix, name), wanted, tools, work_dir,
                                           unreadable, depth + 1, progress))
    return hits


def _keep(data, name, work_dir):
    path = os.path.join(tempfile.mkdtemp(dir=work_dir, prefix="f_"), os.path.basename(name))
    with open(path, "wb") as f:
        f.write(data)
    return path


def _search_nested(path, outer, prefix, wanted, tools, work_dir, unreadable, depth, progress):
    try:
        if path.lower().endswith(".zip"):
            return _search_zip(path, outer, prefix, wanted, tools, work_dir, unreadable, depth, progress)
        if not tools:
            unreadable.append({"pfad": f"{outer} → {prefix}", "grund": "kein Entpacker gefunden – 7-Zip installieren"})
            return []
        return _search_external(path, outer, prefix, wanted, tools, work_dir, unreadable, depth, progress)
    except (zipfile.BadZipFile, OSError, RuntimeError) as e:
        unreadable.append({"pfad": f"{outer} → {prefix}", "grund": str(e)})
        return []


def _search_external(archive, outer, prefix, wanted, tools, work_dir, unreadable, depth, progress=None):
    """Entpackt ein RAR/7z kurz in den Temp-Ordner und durchsucht den Inhalt."""
    if progress:
        progress(f"entpacke {os.path.basename(archive)}")
    dest = tempfile.mkdtemp(dir=work_dir, prefix="x_")
    try:
        archive_tools.extract_relevant(archive, dest, tools)
    except RuntimeError as e:
        unreadable.append({"pfad": _chain(outer, prefix) if prefix else outer, "grund": str(e)})
        shutil.rmtree(dest, ignore_errors=True)
        return []
    hits, keep = [], False
    for root, _dirs, files in os.walk(dest):
        for name in files:
            path = os.path.join(root, name)
            rel = os.path.relpath(path, dest)
            low = name.lower()
            try:
                if low.endswith(".package"):
                    ids = _ids_in_entries(dbpf.read_index(path), wanted)
                    if ids:
                        hits.append({"pfad": outer, "archiv_eintrag": _chain(prefix, rel), "ids": ids,
                                     "groesse": os.path.getsize(path), "temp_datei": path})
                        keep = True
                elif low.endswith((".zip",) + archive_tools.EXTERNAL_ARCHIVES) and depth < MAX_NESTING:
                    hits.extend(_search_nested(path, outer, _chain(prefix, rel), wanted, tools, work_dir,
                                               unreadable, depth + 1, progress))
            except (dbpf.DBPFError, OSError):
                continue
    if not keep:
        shutil.rmtree(dest, ignore_errors=True)  # nichts gefunden: sofort aufräumen
    return hits


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


def restore(found, mods_folder, exclude=()):
    """Kopiert gefundene Pakete nach <Mods>/SimVault_wiederhergestellt. Überschreibt nichts.
    exclude: Textstücke – Funde, deren Datei oder Fundort eines davon enthält, werden übersprungen.
    Gibt die Liste der neu angelegten Dateien zurück."""
    target_dir = os.path.join(mods_folder, RESTORE_SUBFOLDER)
    os.makedirs(target_dir, exist_ok=True)
    created = []
    patterns = [x.lower() for x in exclude if x]
    for item in found:
        haystack = f"{item['pfad']} {item.get('archiv_eintrag') or ''}".lower()
        if any(p in haystack for p in patterns):
            continue
        target = os.path.join(target_dir, item["datei"])
        if os.path.exists(target):
            continue
        try:
            if item.get("temp_datei") and os.path.isfile(item["temp_datei"]):
                shutil.copy2(item["temp_datei"], target)          # aus RAR/7z oder verschachteltem Archiv
            elif item["archiv_eintrag"] and item["pfad"].lower().endswith(".zip"):
                with zipfile.ZipFile(item["pfad"]) as z, z.open(item["archiv_eintrag"]) as src, \
                        open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
            elif item["archiv_eintrag"]:
                archive_tools.extract_member(item["pfad"], item["archiv_eintrag"], target,
                                             archive_tools.find_tools())
            else:
                shutil.copy2(item["pfad"], target)
        except (OSError, RuntimeError, KeyError, zipfile.BadZipFile) as e:
            log.error("%s konnte nicht zurückgeholt werden: %s", item["datei"], e)
            continue
        created.append(target)
    return created

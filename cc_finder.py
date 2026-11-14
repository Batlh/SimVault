# Modul: cc_finder.py
# Funktion: "Fundgrube" – sucht fehlende CC auf dem eigenen PC.
#
# Durchsucht beliebige Ordner (alte Mods-Ordner, Downloads, Mod-Manager- und CurseForge-Ordner,
# Backups …) samt ZIP-Archiven nach .package-Dateien, die die gesuchten IDs enthalten.
# Gefundene Pakete können optional in den Mods-Ordner zurückgeholt werden
# (Unterordner "SimVault_wiederhergestellt", es wird nichts überschrieben).
#
# Grenzen: .rar- und .7z-Archive kann Python ohne Zusatzprogramme nicht öffnen – sie werden
# aufgelistet, damit man sie selbst entpacken kann.

import os
import shutil
import logging
import zipfile

import dbpf

log = logging.getLogger(__name__)

RESTORE_SUBFOLDER = "SimVault_wiederhergestellt"
UNREADABLE_ARCHIVES = (".rar", ".7z")
SKIP_DIRS = {"$recycle.bin", "system volume information", "node_modules", ".git", "__pycache__"}


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


def _ids_in_entries(entries, wanted):
    return {e.instance for e in entries if e.instance in wanted}


def search(folders, wanted, exclude=(), progress=None):
    """Durchsucht folders nach Paketen mit IDs aus wanted.

    Gibt (treffer, nicht_lesbar) zurück:
      treffer:     [{"pfad", "archiv_eintrag" (oder None), "ids": set, "groesse"}]
      nicht_lesbar: Archive, die nicht geöffnet werden konnten (.rar/.7z/defekt)
    """
    hits, unreadable = [], []
    if not wanted:
        return hits, unreadable
    excluded = {os.path.normcase(os.path.abspath(x)) for x in exclude if x}
    checked = 0
    for folder in folders:
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
                        hits.extend(_search_zip(path, wanted))
                    elif low.endswith(UNREADABLE_ARCHIVES):
                        unreadable.append(path)
                except (dbpf.DBPFError, OSError, zipfile.BadZipFile, RuntimeError) as e:
                    log.debug("%s übersprungen: %s", path, e)
                    if low.endswith(".zip"):
                        unreadable.append(path)
                if progress and checked and checked % 500 == 0:
                    progress(f"{checked} Pakete durchsucht")
    return hits, unreadable


def _search_zip(path, wanted):
    hits = []
    with zipfile.ZipFile(path) as z:
        for info in z.infolist():
            if not info.filename.lower().endswith(".package") or info.file_size == 0:
                continue
            data = z.read(info)
            try:
                ids = _ids_in_entries(dbpf.read_index_bytes(data), wanted)
            except dbpf.DBPFError:
                continue
            if ids:
                hits.append({"pfad": path, "archiv_eintrag": info.filename, "ids": ids, "groesse": info.file_size})
    return hits


def summarize(hits, parts):
    """Ordnet die Treffer den fehlenden Teilen zu.
    parts: Liste aus find_missing()["teile"]. Gibt Treffer (sortiert, IDs als Hex) und die Anzahl
    der Teile zurück, die gefunden wurden."""
    by_id = {int(p["id"], 16): p for p in parts}
    result = []
    found = set()
    for hit in hits:
        found |= hit["ids"]
        arts = sorted({by_id[i]["art"].split(" (")[0] for i in hit["ids"] if i in by_id})
        result.append({
            "datei": os.path.basename(hit["archiv_eintrag"] or hit["pfad"]),
            "pfad": hit["pfad"],
            "archiv_eintrag": hit["archiv_eintrag"],
            "anzahl_ids": len(hit["ids"]),
            "ids": sorted(f"0x{i:016X}" for i in hit["ids"]),
            "arten": arts,
            "groesse": hit["groesse"],
        })
    result.sort(key=lambda r: (-r["anzahl_ids"], r["datei"].lower()))
    return result, len(found)


def restore(found, mods_folder):
    """Kopiert gefundene Pakete nach <Mods>/SimVault_wiederhergestellt. Überschreibt nichts.
    Gibt die Liste der neu angelegten Dateien zurück."""
    target_dir = os.path.join(mods_folder, RESTORE_SUBFOLDER)
    os.makedirs(target_dir, exist_ok=True)
    created = []
    for item in found:
        target = os.path.join(target_dir, item["datei"])
        if os.path.exists(target):
            continue
        if item["archiv_eintrag"]:
            with zipfile.ZipFile(item["pfad"]) as z, z.open(item["archiv_eintrag"]) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
        else:
            shutil.copy2(item["pfad"], target)
        created.append(target)
    return created

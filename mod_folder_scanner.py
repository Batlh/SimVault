# Modul: mod_folder_scanner.py
# Funktion: Scannt den Sims-4-Mods-Ordner, liest jedes .package über seinen DBPF-Index aus
#           und findet typische Probleme.
#
# Ergebnis (ModScanResult):
# - mods: alle .package- und .ts4script-Dateien mit Kategorie und den enthaltenen Ressourcen-IDs
# - issues: Probleme, die dazu führen, dass Mods nicht laden oder sich stören:
#   - .ts4script tiefer als 1 Unterordner (lädt nicht)
#   - .package tiefer als 5 Unterordner (lädt nicht)
#   - beschädigte/leere Pakete, kaputte Script-Archive
#   - nicht entpackte Archive (.zip/.rar/.7z) im Mods-Ordner
#   - doppelte Dateien (gleicher Inhalt)
#   - Konflikte: gleiche CAS-/Objekt-Ressource in mehreren Paketen

import os
import hashlib
import logging
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field

import dbpf

log = logging.getLogger(__name__)

MAX_PACKAGE_DEPTH = 5
MAX_SCRIPT_DEPTH = 1
ARCHIVE_EXTENSIONS = (".zip", ".rar", ".7z")

# IDs unterhalb dieser Grenze werden nicht für den Abgleich genutzt: Creator-IDs sind
# 64-Bit-Hashes, kleine Zahlen würden zufällig mit Zählern im Spielstand übereinstimmen.
MIN_MATCH_ID = 1 << 32


@dataclass
class ModFile:
    path: str
    rel_path: str
    kind: str                 # "package" oder "script"
    size: int
    category: str = ""        # "CAS", "Objekt", "CAS + Objekt", "Tuning/Sonstiges", "Script", "Defekt"
    resource_count: int = 0
    match_ids: set = field(default_factory=set)    # alle Instanz-IDs für den Abgleich mit Spielständen
    content_tgis: list = field(default_factory=list)  # CAS-/Objekt-Ressourcen für die Konfliktsuche

    @property
    def is_content(self):
        """CAS- oder Objekt-CC: Nutzung lässt sich sicher im Spielstand nachweisen."""
        return self.category in ("CAS", "Objekt", "CAS + Objekt")


@dataclass
class Issue:
    severity: str   # "Fehler" oder "Hinweis"
    kind: str
    message: str
    files: list = field(default_factory=list)


@dataclass
class ModScanResult:
    folder: str
    mods: list = field(default_factory=list)
    issues: list = field(default_factory=list)

    def id_lookup(self):
        """Abbildung Instanz-ID -> Liste der Mod-Dateien, die sie enthalten."""
        lookup = defaultdict(list)
        for mod in self.mods:
            for rid in mod.match_ids:
                lookup[rid].append(mod)
        return lookup


def _depth(rel_path):
    return len(rel_path.replace("\\", "/").split("/")) - 1


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _categorize(entries):
    kinds = {dbpf.CONTENT_TYPES[e.type] for e in entries if e.type in dbpf.CONTENT_TYPES}
    if kinds == {"CAS"}:
        return "CAS"
    if kinds == {"Objekt"}:
        return "Objekt"
    if kinds:
        return "CAS + Objekt"
    return "Tuning/Sonstiges"


def scan_mods_folder(folder_path, progress=None):
    """Scannt den Mods-Ordner rekursiv und gibt ein ModScanResult zurück."""
    result = ModScanResult(folder=folder_path)
    if not os.path.isdir(folder_path):
        result.issues.append(Issue("Fehler", "Ordner fehlt", f"Mods-Ordner nicht gefunden: {folder_path}"))
        return result

    archives = []
    for root, _dirs, files in os.walk(folder_path):
        for name in files:
            full = os.path.join(root, name)
            rel = os.path.relpath(full, folder_path)
            low = name.lower()
            if low.endswith(".package"):
                result.mods.append(ModFile(full, rel, "package", os.path.getsize(full)))
            elif low.endswith(".ts4script"):
                result.mods.append(ModFile(full, rel, "script", os.path.getsize(full), category="Script"))
            elif low.endswith(ARCHIVE_EXTENSIONS):
                archives.append(rel)

    total = len(result.mods)
    too_deep_pkg, too_deep_script, broken, empty = [], [], [], []
    for i, mod in enumerate(result.mods, 1):
        if progress and i % 200 == 0:
            progress(i, total)
        if mod.size == 0:
            mod.category = "Defekt"
            empty.append(mod.rel_path)
            continue
        if mod.kind == "script":
            if _depth(mod.rel_path) > MAX_SCRIPT_DEPTH:
                too_deep_script.append(mod.rel_path)
            if not zipfile.is_zipfile(mod.path):
                mod.category = "Defekt"
                broken.append(f"{mod.rel_path} (kein gültiges Script-Archiv)")
            continue

        if _depth(mod.rel_path) > MAX_PACKAGE_DEPTH:
            too_deep_pkg.append(mod.rel_path)
        try:
            entries = dbpf.read_index(mod.path)
        except (dbpf.DBPFError, OSError) as e:
            mod.category = "Defekt"
            broken.append(f"{mod.rel_path} ({e})")
            continue
        mod.resource_count = len(entries)
        mod.category = _categorize(entries)
        mod.match_ids = {e.instance for e in entries if e.instance >= MIN_MATCH_ID}
        mod.content_tgis = [e.tgi for e in entries if e.type in dbpf.CONTENT_TYPES]

    if too_deep_script:
        result.issues.append(Issue("Fehler", "Script zu tief",
                                   "Script-Mods (.ts4script) laden nur direkt im Mods-Ordner "
                                   "oder maximal 1 Unterordner tief.", too_deep_script))
    if too_deep_pkg:
        result.issues.append(Issue("Fehler", "Paket zu tief",
                                   "Pakete laden nur bis maximal 5 Unterordner tief.", too_deep_pkg))
    if broken:
        result.issues.append(Issue("Fehler", "Beschädigt", "Diese Dateien sind beschädigt oder unvollständig.", broken))
    if empty:
        result.issues.append(Issue("Fehler", "Leer", "Diese Dateien sind 0 Byte groß.", empty))
    if archives:
        result.issues.append(Issue("Hinweis", "Archiv", "Archive im Mods-Ordner werden vom Spiel nicht gelesen – "
                                   "entpacken und das Archiv löschen.", archives))

    duplicates = _find_duplicates(result.mods)
    result.issues.extend(duplicates)
    result.issues.extend(_find_conflicts(result.mods, {tuple(d.files) for d in duplicates}))
    log.info("%d Mod-Dateien gescannt, %d Probleme gefunden.", total, len(result.issues))
    return result


def _find_duplicates(mods):
    by_size = defaultdict(list)
    for mod in mods:
        if mod.size > 0:
            by_size[mod.size].append(mod)
    by_hash = defaultdict(list)
    for same_size in by_size.values():
        if len(same_size) > 1:
            for mod in same_size:
                try:
                    by_hash[_sha256(mod.path)].append(mod.rel_path)
                except OSError:
                    pass
    issues = []
    for paths in by_hash.values():
        if len(paths) > 1:
            issues.append(Issue("Hinweis", "Duplikat", "Identische Dateien – eine davon reicht.", sorted(paths)))
    return issues


def _find_conflicts(mods, duplicate_groups=()):
    owners = defaultdict(set)
    for mod in mods:
        for tgi in mod.content_tgis:
            owners[tgi].add(mod.rel_path)
    # Gleiche Paket-Kombination nur einmal melden
    grouped = defaultdict(int)
    for files in owners.values():
        if len(files) > 1:
            grouped[tuple(sorted(files))] += 1
    issues = []
    for files, count in grouped.items():
        if files in duplicate_groups:
            continue  # schon als Duplikat gemeldet
        issues.append(Issue("Hinweis", "Konflikt",
                            f"{count} CAS-/Objekt-Ressource(n) stecken in mehreren Paketen – "
                            "meist doppelt installierte CC (z. B. einzeln und zusätzlich in einem Merge).",
                            list(files)))
    return issues

# Modul: downloads.py
# Funktion: Download-Verwaltung – heruntergeladene CC prüfen, entpacken und an die richtige Stelle legen.
#
# Ein Download kann sein: ein .package, ein Script-Mod (.ts4script), Bibliotheks-Dateien (Sims, Häuser,
# Räume) oder ein Archiv (ZIP, RAR, 7z – auch verschachtelt) mit beliebig vielem davon.
#
# Installieren heißt:
# - Pakete       -> Mods\SimVault_heruntergeladen\<Name des Downloads>\   (2 Ebenen tief, lädt sicher)
# - Script-Mods  -> Mods\SimVault_heruntergeladen\                        (Scripts laden nur 1 Ebene tief)
# - Bibliothek   -> Tray\                                                 (das Spiel liest dort nur flach)
# Übersprungen wird, was schon installiert ist (alle CC-Teile des Pakets sind schon im Mods-Ordner, oder
# dieselbe Datei liegt schon da) und was kaputt ist. Es wird nie etwas überschrieben.
#
# Die Liste der Downloads (downloads.json im Download-Ordner) merkt sich, was installiert wurde.

import os
import re
import json
import shutil
import hashlib
import logging
import zipfile
import tempfile
import threading
import time
from datetime import datetime
from urllib.parse import urlsplit

import dbpf
import archive_tools

log = logging.getLogger(__name__)

INSTALL_SUBFOLDER = "SimVault_heruntergeladen"
TRAY_EXTENSIONS = (".trayitem", ".householdbinary", ".blueprint", ".room", ".bpi", ".hhi", ".sgi", ".rmi")
SCRIPT_EXTENSIONS = (".ts4script",)
PACKAGE_EXTENSIONS = (".package",)
ARCHIVE_EXTENSIONS = (".zip", ".rar", ".7z")
WANTED = PACKAGE_EXTENSIONS + SCRIPT_EXTENSIONS + TRAY_EXTENSIONS + ARCHIVE_EXTENSIONS
MAX_DEPTH = 3
MIN_CC_ID = 1 << 32


# Seiten, die zu häufiges Laden derselben Datei bestrafen: (Muster der Datei-URL, erlaubte Anzahl, Zeitraum in
# Sekunden, Hinweis). NewSea sperrt das Konto für eine Stunde, wenn dieselbe Datei öfter als zweimal in fünf
# Minuten geladen wird.
DOWNLOAD_LIMITS = [
    (re.compile(r"^https?://(www\.)?newseasims\.com/downfile\.php", re.I), 2, 300,
     "NewSea sperrt dein Konto für 1 Stunde, wenn dieselbe Datei öfter als zweimal in 5 Minuten geladen wird"),
]


class DownloadGuard:
    """Zählt Downloads derselben Datei und sagt, wann ein weiterer gegen die Regeln der Seite verstoßen würde.
    Thread-sicher (der eingebaute Browser fragt aus seinem Netzwerk-Thread)."""

    def __init__(self, limits=None, clock=time.monotonic):
        self.limits = DOWNLOAD_LIMITS if limits is None else limits
        self.clock = clock
        self._seen = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(url):
        parts = urlsplit(url.strip())
        host = (parts.hostname or "").lower()
        if host.startswith("www."):
            host = host[4:]
        return f"{host}{parts.path}?{parts.query}"

    def _rule(self, url):
        for pattern, count, seconds, hint in self.limits:
            if pattern.search(url):
                return count, seconds, hint
        return None

    def check(self, url):
        """Gibt (Wartezeit in Sekunden, Hinweis) zurück; Wartezeit 0 = darf geladen werden (und wird gezählt)."""
        rule = self._rule(url)
        if not rule:
            return 0, ""
        count, seconds, hint = rule
        key, now = self._key(url), self.clock()
        with self._lock:
            times = [t for t in self._seen.get(key, []) if now - t < seconds]
            if len(times) >= count:
                self._seen[key] = times
                oldest = times[0] if times else now
                return max(1, int(seconds - (now - oldest)) + 1), hint
            times.append(now)
            self._seen[key] = times
        return 0, hint


download_guard = DownloadGuard()


def blocked_message(wait, hint):
    minutes = (wait + 59) // 60
    return f"Nicht geladen: {hint}. Bitte noch etwa {minutes} Min. warten."


def _sha1(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _kind(name):
    low = name.lower()
    if low.endswith(PACKAGE_EXTENSIONS):
        return "paket"
    if low.endswith(SCRIPT_EXTENSIONS):
        return "script"
    if low.endswith(TRAY_EXTENSIONS):
        return "bibliothek"
    if low.endswith(ARCHIVE_EXTENSIONS):
        return "archiv"
    return None


def _unpack(archive, dest, tools, depth=0):
    """Entpackt alle relevanten Dateien (auch aus verschachtelten Archiven) nach dest.
    Gibt [(Pfad, Herkunft)] zurück; Herkunft ist der Pfad im Archiv (mit „ → “ bei Verschachtelung)."""
    found = []
    fmt = archive_tools.sniff(archive)
    if fmt is None:
        raise RuntimeError("kein lesbares Archiv")
    os.makedirs(dest, exist_ok=True)
    if fmt == ".zip":
        with zipfile.ZipFile(archive) as z:
            for info in z.infolist():
                if info.is_dir() or not info.filename.lower().endswith(WANTED):
                    continue
                if info.flag_bits & 0x1:
                    raise RuntimeError("mit Passwort geschützt")
                rel = os.path.normpath(info.filename.replace("\\", "/"))
                if rel.startswith("..") or os.path.isabs(rel):
                    continue
                target = os.path.join(dest, rel)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with z.open(info) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst, 1 << 20)
    else:
        archive_tools.extract_relevant(archive, dest, tools, fmt, extensions=WANTED)
    for root, _dirs, names in os.walk(dest):
        for name in names:
            path = os.path.join(root, name)
            rel = os.path.relpath(path, dest)
            kind = _kind(name)
            if kind == "archiv" or (kind == "paket" and archive_tools.sniff(path)):   # auch falsch benannte
                if depth >= MAX_DEPTH:
                    continue
                inner = path + "_entpackt"
                try:
                    found += [(p, f"{rel} → {origin}") for p, origin in _unpack(path, inner, tools, depth + 1)]
                except RuntimeError as e:
                    log.warning("verschachteltes Archiv %s nicht lesbar: %s", rel, e)
            elif kind:
                found.append((path, rel))
    return found


def _package_ids(path):
    """(CC-IDs, Fehler) eines Pakets."""
    try:
        entries = dbpf.read_index(path)
    except (dbpf.DBPFError, OSError) as e:
        return None, str(e)
    if not entries:
        return None, "Paket ist leer"
    return {e.instance for e in entries if e.type in dbpf.CONTENT_TYPES and e.instance >= MIN_CC_ID}, None


def _existing_files(folder):
    """{(Dateiname klein, Größe): [Pfade]} – zum schnellen Erkennen gleicher Dateien."""
    index = {}
    if folder and os.path.isdir(folder):
        for root, _dirs, names in os.walk(folder):
            for name in names:
                path = os.path.join(root, name)
                try:
                    index.setdefault((name.lower(), os.path.getsize(path)), []).append(path)
                except OSError:
                    pass
    return index


def _same_file_exists(path, index):
    key = (os.path.basename(path).lower(), os.path.getsize(path))
    if key not in index:
        return False
    digest = _sha1(path)
    return any(_sha1(other) == digest for other in index[key])


def _place(source, folder):
    """Kopiert source nach folder – nie überschreiben, bei Namensgleichheit mit Zusatz (2)."""
    from web_session import unique_path
    os.makedirs(folder, exist_ok=True)
    target = unique_path(folder, os.path.basename(source))
    shutil.copy2(source, target)
    return target


def install(path, mods_folder, tray_folder, tools=(), installed_ids=None, work_dir=None, name=None):
    """Installiert einen Download. Gibt ein Dict zurück:
    installiert [(Art, Ziel)], uebersprungen [(Datei, Grund)], fehler [(Datei, Grund)]."""
    out = {"installiert": [], "uebersprungen": [], "fehler": []}
    if installed_ids is None:
        import cc_finder
        installed_ids = cc_finder.installed_ids(mods_folder) if os.path.isdir(mods_folder) else set()
    installed_ids = set(installed_ids)
    label = name or os.path.splitext(os.path.basename(path))[0]
    from web_session import safe_filename
    package_dir = os.path.join(mods_folder, INSTALL_SUBFOLDER, safe_filename(label, "Download"))
    script_dir = os.path.join(mods_folder, INSTALL_SUBFOLDER)
    mods_index = _existing_files(mods_folder)
    tray_index = _existing_files(tray_folder)

    with tempfile.TemporaryDirectory(prefix="simvault_dl_", dir=work_dir) as tmp:
        kind = _kind(path)
        if kind != "script" and archive_tools.sniff(path):      # Scripts sind selbst ZIPs
            kind = "archiv"
        if kind == "archiv":
            try:
                files = _unpack(path, os.path.join(tmp, "x"), list(tools))
            except (RuntimeError, zipfile.BadZipFile, OSError) as e:
                out["fehler"].append((os.path.basename(path), f"Archiv nicht lesbar: {e}"))
                return out
            if not files:
                out["fehler"].append((os.path.basename(path), "im Archiv steckt keine Sims-4-Datei"))
        elif kind:
            files = [(path, os.path.basename(path))]
        else:
            with open(path, "rb") as f:
                head = f.read(64).lstrip()
            reason = ("ist eine Webseite statt der Datei – im eingebauten Browser herunterladen"
                      if head[:1] == b"<" else "keine Sims-4-Datei")
            out["fehler"].append((os.path.basename(path), reason))
            return out

        for file, origin in files:
            k = _kind(file)
            if k == "paket":
                ids, error = _package_ids(file)
                if error:
                    out["fehler"].append((origin, f"beschädigt ({error})"))
                    continue
                if ids and ids <= installed_ids:
                    out["uebersprungen"].append((origin, "schon installiert (alle Teile sind im Mods-Ordner)"))
                    continue
                if _same_file_exists(file, mods_index):
                    out["uebersprungen"].append((origin, "dieselbe Datei liegt schon im Mods-Ordner"))
                    continue
                out["installiert"].append(("Paket", _place(file, package_dir)))
                installed_ids |= ids or set()
            elif k == "script":
                if not zipfile.is_zipfile(file):
                    out["fehler"].append((origin, "kein gültiges Script-Archiv"))
                    continue
                if _same_file_exists(file, mods_index):
                    out["uebersprungen"].append((origin, "dieselbe Datei liegt schon im Mods-Ordner"))
                    continue
                out["installiert"].append(("Script", _place(file, script_dir)))
            elif k == "bibliothek":
                if not tray_folder:
                    out["fehler"].append((origin, "Bibliotheks-Ordner (Tray) unbekannt"))
                    continue
                if _same_file_exists(file, tray_index):
                    out["uebersprungen"].append((origin, "liegt schon in der Bibliothek"))
                    continue
                if os.path.exists(os.path.join(tray_folder, os.path.basename(file))):
                    out["uebersprungen"].append((origin, "eine andere Datei mit diesem Namen ist schon in der "
                                                         "Bibliothek – nicht überschrieben"))
                    continue
                out["installiert"].append(("Bibliothek", _place(file, tray_folder)))
    return out


# ---------------------------------------------------------------------------
# Liste der Downloads
# ---------------------------------------------------------------------------

class DownloadList:
    """Merkt sich Downloads in <Ordner>/downloads.json: datei, url, quelle, zeit, status, ergebnis."""

    def __init__(self, folder):
        self.folder = folder
        self.path = os.path.join(folder, "downloads.json")
        self.items = []
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as f:
                    self.items = json.load(f)
            except (OSError, ValueError):
                self.items = []

    def _save(self):
        os.makedirs(self.folder, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.items, f, indent=1, ensure_ascii=False)

    def add(self, file, url="", source=""):
        item = {"datei": file, "url": url, "quelle": source,
                "zeit": datetime.now().isoformat(timespec="seconds"), "status": "heruntergeladen", "ergebnis": ""}
        self.items.insert(0, item)
        self._save()
        return item

    def update(self, item, status, result=""):
        item["status"], item["ergebnis"] = status, result
        self._save()

    def remove(self, item, delete_file=False):
        if item in self.items:
            self.items.remove(item)
        if delete_file and os.path.isfile(item["datei"]):
            os.remove(item["datei"])
        self._save()


def summary(result):
    """Kurzer Text zu einem install()-Ergebnis."""
    parts = []
    from collections import Counter
    kinds = Counter(k for k, _p in result["installiert"])
    if kinds:
        parts.append("installiert: " + ", ".join(f"{n}× {k}" for k, n in kinds.items()))
    if result["uebersprungen"]:
        parts.append(f"{len(result['uebersprungen'])} übersprungen")
    if result["fehler"]:
        parts.append(f"{len(result['fehler'])} Fehler")
    return "; ".join(parts) or "nichts zu installieren"

# Modul: archive_tools.py
# Funktion: Entpackt .rar- und .7z-Archive für die Fundgrube-Suche in einen Temp-Ordner.
#
# Python kann RAR und 7z nicht selbst öffnen. Genutzt wird der erste vorhandene Entpacker:
#   1. 7-Zip (7z.exe)            – RAR und 7z
#   2. WinRAR (UnRAR.exe)        – nur RAR
#   3. tar von Windows 10/11     – (bsdtar/libarchive) RAR und 7z, je nach Windows-Version
# Entpackt werden nur .package-Dateien und verschachtelte Archive – keine ganzen Spiele-Archive.
# Archive mit Passwort führen nie zu einer Abfrage: sie werden als „nicht lesbar“ gemeldet.

import os
import shutil
import logging
import subprocess

log = logging.getLogger(__name__)

EXTERNAL_ARCHIVES = (".rar", ".7z")
RELEVANT = (".package", ".zip", ".rar", ".7z")
TIMEOUT = 900  # Sekunden pro Archiv
DUMMY_PASSWORD = "SimVault-kein-Passwort"  # verhindert Passwortabfragen


def _windows_paths(*parts):
    paths = []
    for env in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
        base = os.environ.get(env)
        if base:
            paths.append(os.path.join(base, *parts))
    return paths


def _first_existing(names, extra_paths=()):
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    for path in extra_paths:
        if os.path.isfile(path):
            return path
    return None


def _is_bsdtar(path):
    try:
        out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=20,
                             stdin=subprocess.DEVNULL)
        return "bsdtar" in (out.stdout + out.stderr).lower()
    except (OSError, subprocess.SubprocessError):
        return False


def tool_kind(path):
    """Art eines Entpackers anhand des Dateinamens: "7z", "unrar" oder "bsdtar" (None = unbekannt)."""
    name = os.path.basename(path).lower()
    if name.startswith("7z"):
        return "7z"
    if "rar" in name:
        return "unrar"
    if "tar" in name and _is_bsdtar(path):
        return "bsdtar"
    return None


def tools_from_config(cfg):
    """Entpacker gemäß config.json:
    "extractor": ""      -> automatisch suchen
                 "none"  -> keinen benutzen (RAR/7z werden übersprungen)
                 Pfad    -> diesen zuerst benutzen, die übrigen gefundenen als Ersatz"""
    choice = (cfg.get("extractor") or "").strip()
    if choice.lower() in ("none", "keiner", "aus"):
        return []
    found = find_tools()
    if choice:
        kind = tool_kind(choice) if os.path.isfile(choice) else None
        if kind:
            return [(kind, choice)] + [t for t in found if os.path.normcase(t[1]) != os.path.normcase(choice)]
        log.warning("Entpacker aus config.json nicht nutzbar: %s – suche automatisch", choice)
    return found


TOOL_NAMES = {"7z": "7-Zip", "unrar": "WinRAR (UnRAR)", "bsdtar": "tar (Windows/libarchive)"}


def find_tools():
    """Gefundene Entpacker als Liste von (art, pfad), in Reihenfolge der Bevorzugung."""
    tools = []
    seven = _first_existing(["7z", "7za", "7zz"], _windows_paths("7-Zip", "7z.exe"))
    if seven:
        tools.append(("7z", seven))
    unrar = _first_existing(["unrar", "UnRAR"], _windows_paths("WinRAR", "UnRAR.exe"))
    if unrar:
        tools.append(("unrar", unrar))
    for name in ("bsdtar", "tar"):
        tar = shutil.which(name)
        if tar and _is_bsdtar(tar):
            tools.append(("bsdtar", tar))
            break
    return tools


def _run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT,
                          stdin=subprocess.DEVNULL, errors="replace")


def _bsdtar_members(tar, archive, extensions=RELEVANT):
    out = _run([tar, "-tf", archive])
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip()[:200] or "Liste nicht lesbar")
    return [m for m in out.stdout.splitlines() if m.lower().endswith(tuple(extensions))]


SIGNATURES = [(b"Rar!\x1a\x07", ".rar"), (b"7z\xbc\xaf\x27\x1c", ".7z"), (b"PK\x03\x04", ".zip")]


def sniff(path):
    """Echtes Archivformat anhand der ersten Bytes (".rar", ".7z", ".zip" oder None) –
    für Archive mit falscher Endung, z. B. ein RAR namens .zip."""
    try:
        with open(path, "rb") as f:
            head = f.read(8)
    except OSError:
        return None
    for magic, ext in SIGNATURES:
        if head.startswith(magic):
            return ext
    return None


NEEDS_7ZIP = "dieses 7z kann nur 7-Zip öffnen – 7-Zip installieren (winget install 7zip.7zip)"


def _reason(kind, text, returncode=None):
    """Kurze, verständliche Begründung aus der Ausgabe eines Entpackers."""
    t = (text or "").lower()
    if kind == "unrar" and returncode in (3, 11) or any(
            w in t for w in ("password", "passwort", "encrypt", "verschlüssel")):
        return "mit Passwort geschützt"
    if kind == "bsdtar" and ("lzma" in t or "ppmd" in t or "bcj" in t or "unsupported" in t
                             or "not supported" in t):
        return NEEDS_7ZIP
    if any(w in t for w in ("damaged", "corrupt", "crc", "unexpected end", "truncated", "beschädigt")):
        return "Archiv beschädigt oder unvollständig"
    if "can not open" in t or "cannot open" in t or "not an archive" in t or "unrecognized archive" in t:
        return "kein gültiges Archiv"
    first = next((line.strip() for line in (text or "").splitlines()
                  if line.strip() and "error exit delayed" not in line.lower()), "")
    return first[:120] or "Fehler beim Entpacken"


def extract_relevant(archive, dest, tools, fmt=None, extensions=RELEVANT):
    """Entpackt die relevanten Dateien (Pakete, verschachtelte Archive) nach dest.
    fmt: tatsächliches Format (".rar"/".7z"), falls die Dateiendung nicht stimmt.
    extensions: welche Dateien (Standard: Pakete und Archive; Downloads brauchen auch Scripts und Tray-Dateien).
    Wirft RuntimeError mit einer verständlichen Begründung, wenn es mit keinem Entpacker geht."""
    fmt = fmt or os.path.splitext(archive)[1].lower()
    reasons = []
    for kind, path in tools:
        if kind == "unrar" and fmt != ".rar":
            continue
        try:
            if kind == "7z":
                cmd = [path, "x", "-y", "-bd", f"-p{DUMMY_PASSWORD}", f"-o{dest}", archive]
                out = _run(cmd + [f"*{ext}" for ext in extensions] + ["-r"])
                ok, code = out.returncode in (0, 1), out.returncode   # 1 = Warnung
            elif kind == "unrar":
                cmd = [path, "x", "-y", "-r", "-p-", "-idq", archive] + [f"*{ext}" for ext in extensions]
                out = _run(cmd + [dest + os.sep])
                ok, code = out.returncode in (0, 1, 10), out.returncode   # 10 = nichts Passendes drin
            else:  # bsdtar
                code = None
                try:
                    members = _bsdtar_members(path, archive, extensions)
                except RuntimeError as e:
                    reasons.append(_reason(kind, str(e)))
                    continue
                ok, out = True, None
                for i in range(0, len(members), 100):  # Befehlszeile nicht zu lang werden lassen
                    out = _run([path, "-xf", archive, "-C", dest] + members[i:i + 100])
                    ok = ok and out.returncode == 0
            if ok:
                return
            reasons.append(_reason(kind, (out.stderr or "") + "\n" + (out.stdout or "") if out else "", code))
        except subprocess.TimeoutExpired:
            reasons.append("Zeitüberschreitung beim Entpacken")
        except OSError as e:
            reasons.append(f"Entpacker nicht startbar ({e})")
    if not reasons:
        raise RuntimeError(NEEDS_7ZIP if fmt == ".7z" else "kein passender Entpacker – 7-Zip installieren")
    # die aussagekräftigste Begründung nach vorn
    for preferred in ("mit Passwort geschützt", NEEDS_7ZIP, "Archiv beschädigt oder unvollständig"):
        if preferred in reasons:
            raise RuntimeError(preferred)
    raise RuntimeError("; ".join(dict.fromkeys(reasons)))


def extract_member(archive, member, target, tools, work_dir=None):
    """Holt eine einzelne Datei aus einem RAR/7z-Archiv und speichert sie als target."""
    import tempfile
    with tempfile.TemporaryDirectory(prefix="simvault_", dir=work_dir) as tmp:
        extract_relevant(archive, tmp, tools, fmt=sniff(archive))
        source = os.path.join(tmp, member)
        if not os.path.isfile(source):
            raise RuntimeError(f"{member} nicht im Archiv gefunden")
        shutil.copy2(source, target)

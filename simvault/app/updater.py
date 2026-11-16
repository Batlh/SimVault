# Modul: simvault/app/updater.py
# Funktion: Auto-Updater – prüft auf GitHub, ob es ein neueres Release gibt, zeigt den Changelog,
#           lädt die neue Version herunter und tauscht das Programm nach dem Beenden aus.
#
# Ablauf:
# 1. check()    fragt https://api.github.com/repos/<Repo>/releases/latest ab und vergleicht die Version
# 2. download() lädt SimVault-Windows.zip in den Benutzerordner (updates/)
# 3. install()  entpackt daneben und startet ein kleines Skript, das wartet, bis SimVault beendet ist,
#               die neuen Dateien über die alten kopiert und SimVault neu startet.
#               Einstellungen, Berichte, Backups und eigene Erweiterungen bleiben erhalten –
#               es wird nur überschrieben, nichts gelöscht.
#
# Wer SimVault aus dem Quellcode startet, bekommt nur den Hinweis (dort aktualisiert man mit "git pull").
# Es werden keine Daten gesendet – nur die öffentliche Release-Seite wird gelesen.

import os
import re
import sys
import json
import shutil
import zipfile
import logging
import subprocess
import urllib.request

from simvault.app.version import __version__, REPOSITORY

log = logging.getLogger(__name__)

ASSET_NAME = "SimVault-Windows.zip"
API_URL = "https://api.github.com/repos/{repo}/releases/latest"
USER_AGENT = f"SimVault/{__version__}"


def parse_version(text):
    """"v0.6.1" -> (0, 6, 1). Unlesbares ergibt (0,)."""
    numbers = re.findall(r"\d+", str(text).split("-")[0])
    return tuple(int(n) for n in numbers[:4]) or (0,)


def is_newer(candidate, current=__version__):
    a, b = parse_version(candidate), parse_version(current)
    length = max(len(a), len(b))
    return a + (0,) * (length - len(a)) > b + (0,) * (length - len(b))


def _get(url, timeout):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    return urllib.request.urlopen(request, timeout=timeout)


def check(repo=REPOSITORY, timeout=8, fetch=None):
    """Fragt das neueste Release ab. Gibt ein Dict zurück:
    aktuell, neueste, neuer (bool), notizen (Changelog), url (Release-Seite), download (ZIP-Adresse), groesse.
    Wirft OSError, wenn GitHub nicht erreichbar ist. fetch: Ersatz-Abruf für Tests (liefert das Release-Dict)."""
    if fetch:
        data = fetch()
    else:
        with _get(API_URL.format(repo=repo), timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    tag = data.get("tag_name") or ""
    asset = next((a for a in data.get("assets", []) if a.get("name") == ASSET_NAME), None)
    return {
        "aktuell": __version__,
        "neueste": tag.lstrip("v"),
        "neuer": bool(tag) and is_newer(tag),
        "notizen": data.get("body") or "",
        "url": data.get("html_url") or f"https://github.com/{repo}/releases",
        "download": asset["browser_download_url"] if asset else "",
        "groesse": asset.get("size", 0) if asset else 0,
    }


def download(info, target_dir, progress=None, should_stop=None, timeout=30):
    """Lädt das ZIP des Releases nach target_dir. Gibt den Pfad zurück (None bei Abbruch)."""
    if not info.get("download"):
        raise OSError("Dieses Release enthält kein SimVault-Windows.zip.")
    os.makedirs(target_dir, exist_ok=True)
    target = os.path.join(target_dir, f"SimVault-{info['neueste']}.zip")
    tmp = target + ".teil"
    done = 0
    with _get(info["download"], timeout) as response, open(tmp, "wb") as f:
        total = int(response.headers.get("Content-Length") or info.get("groesse") or 0)
        while True:
            if should_stop and should_stop():
                f.close()
                os.remove(tmp)
                return None
            block = response.read(1 << 18)
            if not block:
                break
            f.write(block)
            done += len(block)
            if progress and total:
                progress(f"Lade Update: {done * 100 // total} % von {total / 1048576:.0f} MB")
    if info.get("groesse") and done != info["groesse"]:
        os.remove(tmp)
        raise OSError("Download unvollständig – bitte noch einmal versuchen.")
    if not zipfile.is_zipfile(tmp):
        os.remove(tmp)
        raise OSError("Die heruntergeladene Datei ist kein gültiges ZIP.")
    os.replace(tmp, target)
    return target


def app_dir():
    """Ordner des gebauten Programms (None, wenn SimVault aus dem Quellcode läuft)."""
    return os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else None


def can_self_update():
    folder = app_dir()
    return bool(folder) and os.name == "nt" and os.access(folder, os.W_OK)


def extract(zip_path, work_dir):
    """Entpackt das Update und gibt den Ordner zurück, der SimVault.exe enthält."""
    if os.path.isdir(work_dir):
        shutil.rmtree(work_dir)
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():                       # nichts außerhalb des Arbeitsordners entpacken
            rel = os.path.normpath(name)
            if os.path.isabs(rel) or rel.startswith(".."):
                raise OSError(f"Unerwarteter Pfad im Update: {name}")
        z.extractall(work_dir)
    for root, _dirs, files in os.walk(work_dir):
        if "SimVault.exe" in files:
            return root
    raise OSError("Im Update steckt keine SimVault.exe.")


def write_swap_script(new_dir, target_dir, pid, script_path, cleanup_dir=None):
    """Schreibt das Skript, das nach dem Beenden von SimVault die Dateien austauscht und neu startet.
    cleanup_dir: Ordner mit den entpackten Dateien, der danach gelöscht wird (Standard: new_dir)."""
    cleanup_dir = cleanup_dir or new_dir
    lines = [
        "@echo off",
        "chcp 65001 >nul",
        "rem SimVault-Update: warten, bis das Programm beendet ist, dann Dateien kopieren und neu starten",
        ":warten",
        f'tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul',
        "if not errorlevel 1 (",
        "  timeout /t 1 /nobreak >nul",
        "  goto warten",
        ")",
        f'robocopy "{new_dir}" "{target_dir}" /E /R:3 /W:1 /NFL /NDL /NJH /NJS /NP >nul',
        f'start "" "{os.path.join(target_dir, "SimVault.exe")}"',
        f'rmdir /S /Q "{cleanup_dir}" >nul 2>&1',
        '(goto) 2>nul & del "%~f0"',
    ]
    with open(script_path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write("\n".join(lines) + "\n")
    return script_path


def install(zip_path, work_base):
    """Bereitet den Austausch vor und startet das Skript. Danach muss sich SimVault beenden.
    Gibt True zurück, wenn der Austausch läuft; False, wenn das hier nicht geht (dann ZIP von Hand entpacken)."""
    if not can_self_update():
        return False
    work = os.path.join(work_base, "entpackt")
    new_dir = extract(zip_path, work)
    script = write_swap_script(new_dir, app_dir(), os.getpid(), os.path.join(work_base, "simvault_update.bat"), work)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen(["cmd", "/c", script], creationflags=flags, close_fds=True, cwd=work_base)
    return True

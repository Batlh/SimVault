# Modul: web_session.py
# Funktion: Zugriff auf CC-Seiten für Quellen und Downloads – mit den gespeicherten Anmeldungen.
#
# - get(url) / get_bytes(url): normale Abrufe, die Cookies aus dem verschlüsselten Speicher werden mitgeschickt
# - render(url): lädt die Seite im eingebauten Browser (mit JavaScript) und liefert das fertige HTML –
#   für Seiten, die ohne Browser nichts anzeigen oder einfache Abrufe blocken (Cloudflare & Co.).
#   Ohne Programmfenster gibt es keinen Browser; dann fällt render() auf get() zurück.
# - download(url, folder): lädt eine Datei herunter. Kommt statt der Datei eine Webseite zurück
#   (Anmeldung, Captcha, Wartezeit), gibt es NeedsBrowser – die Seite muss im Browser geöffnet werden.

import os
import re
import logging
import urllib.request
from urllib.parse import unquote, urlparse

from secure_store import cookie_header

log = logging.getLogger(__name__)

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0 Safari/537.36 SimVault")
TIMEOUT = 30
CHUNK = 1 << 16


class NeedsBrowser(Exception):
    """Statt einer Datei kam eine Webseite – die Seite muss im (eingebauten) Browser geöffnet werden."""


class Cancelled(Exception):
    pass


def safe_filename(name, fallback="download"):
    name = os.path.basename(unquote(name or "").replace("\\", "/")).strip().strip(".")
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    return name[:150] or fallback


def filename_from(response, url):
    disposition = response.headers.get("Content-Disposition", "")
    match = re.search(r"filename\*=(?:UTF-8'')?([^;]+)", disposition, re.I) or \
        re.search(r'filename="?([^";]+)"?', disposition, re.I)
    if match:
        return safe_filename(match.group(1).strip())
    return safe_filename(urlparse(response.geturl() or url).path)


def unique_path(folder, name):
    base, ext = os.path.splitext(name)
    path = os.path.join(folder, name)
    n = 2
    while os.path.exists(path):
        path = os.path.join(folder, f"{base} ({n}){ext}")
        n += 1
    return path


class WebSession:
    """store: SecureStore (oder None); renderer: Funktion url -> HTML (eingebauter Browser) oder None."""

    def __init__(self, store=None, renderer=None):
        self.store = store
        self.renderer = renderer

    def _cookies(self):
        if not self.store:
            return []
        try:
            return self.store.all_cookies()
        except Exception as e:          # Anmeldungen nicht lesbar: ohne Cookies weiter
            log.warning("Anmeldungen nicht lesbar: %s", e)
            return []

    def open(self, url, referer=None):
        headers = {"User-Agent": USER_AGENT, "Accept-Language": "de,en;q=0.8"}
        cookie = cookie_header(self._cookies(), url)
        if cookie:
            headers["Cookie"] = cookie
        if referer:
            headers["Referer"] = referer
        return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=TIMEOUT)

    def get(self, url):
        with self.open(url) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, "replace")

    def get_bytes(self, url, limit=5 << 20):
        with self.open(url) as response:
            return response.read(limit)

    def render(self, url):
        if self.renderer:
            return self.renderer(url)
        return self.get(url)

    def download(self, url, folder, progress=None, should_stop=None, referer=None):
        """Lädt url nach folder. Gibt den Pfad der Datei zurück."""
        from downloads import download_guard, blocked_message
        wait, hint = download_guard.check(url)
        if wait:
            raise OSError(blocked_message(wait, hint))
        os.makedirs(folder, exist_ok=True)
        with self.open(url, referer) as response:
            ctype = (response.headers.get("Content-Type") or "").lower()
            name = filename_from(response, url)
            if "text/html" in ctype or (not os.path.splitext(name)[1] and "text/" in ctype):
                raise NeedsBrowser("Statt der Datei kam eine Webseite (Anmeldung, Captcha oder Wartezeit) – "
                                   "im eingebauten Browser öffnen und dort herunterladen.")
            total = int(response.headers.get("Content-Length") or 0)
            target = unique_path(folder, name)
            part = target + ".part"
            done = 0
            try:
                with open(part, "wb") as f:
                    while True:
                        if should_stop and should_stop():
                            raise Cancelled()
                        block = response.read(CHUNK)
                        if not block:
                            break
                        f.write(block)
                        done += len(block)
                        if progress:
                            progress(f"lade {name}: {done / 1048576:.1f}"
                                     + (f" / {total / 1048576:.1f} MB" if total else " MB"))
                if total and done < total:
                    raise OSError(f"Download unvollständig ({done} von {total} Bytes)")
                os.replace(part, target)
            finally:
                if os.path.exists(part):
                    os.remove(part)
        return target

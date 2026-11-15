# Modul: gui/browser.py – eingebauter Browser (Chromium über Qt WebEngine)
#
# Wozu:
# - Anmelden bei CC-Seiten (Patreon, LoversLab, TSR …) in einem sichtbaren Fenster – inklusive 2FA und
#   Captchas, die der Nutzer selbst löst. SimVault sieht nie ein Passwort, nur die Cookies danach.
# - CC-Seiten durchstöbern und herunterladen: Downloads werden abgefangen, landen im Download-Ordner
#   und werden (wenn eingestellt) sofort entpackt und installiert.
# - Seiten für Quellen „rendern“ (JavaScript ausführen), die ohne Browser nichts liefern.
#
# Cookies: Der Browser arbeitet „off the record“ – Chromium schreibt nichts auf die Platte. Gespeichert
# wird nur über den verschlüsselten Speicher (secure_store.py, AES-256-GCM): beim Start werden die
# gespeicherten Anmeldungen in den Browser geladen, „Anmeldung speichern“ legt sie wieder verschlüsselt ab.

import os
import threading
from urllib.parse import urlparse

from PySide6.QtCore import QDateTime, QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkCookie
from PySide6.QtWebEngineCore import (QWebEngineDownloadRequest, QWebEnginePage, QWebEngineProfile,
                                     QWebEngineUrlRequestInterceptor)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget


def base_domain(host):
    """example.co.uk -> co.uk wäre falsch, für CC-Seiten reicht aber: die letzten zwei Teile."""
    parts = (host or "").lower().strip(".").split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else (host or "").lower()


def _to_dict(cookie, fallback_host=""):
    domain = cookie.domain() or fallback_host
    expires = cookie.expirationDate()
    return {"name": bytes(cookie.name()).decode("utf-8", "replace"),
            "value": bytes(cookie.value()).decode("utf-8", "replace"),
            "domain": domain, "path": cookie.path() or "/", "secure": cookie.isSecure(),
            "httponly": cookie.isHttpOnly(),
            "expires": expires.toSecsSinceEpoch() if expires.isValid() else 0}


def _to_qt(c):
    cookie = QNetworkCookie(c["name"].encode("utf-8"), c["value"].encode("utf-8"))
    cookie.setDomain(c.get("domain") or "")
    cookie.setPath(c.get("path") or "/")
    cookie.setSecure(bool(c.get("secure")))
    cookie.setHttpOnly(bool(c.get("httponly")))
    if c.get("expires"):
        cookie.setExpirationDate(QDateTime.fromSecsSinceEpoch(int(c["expires"])))
    return cookie


class _DownloadLimiter(QWebEngineUrlRequestInterceptor):
    """Hält Datei-Anfragen an, bevor sie die Seite erreichen, wenn die Seite sie als zu häufig werten würde
    (NewSea zählt schon die Anfrage, ein Abbruch erst beim Download wäre zu spät)."""

    def __init__(self, blocked, parent=None):
        super().__init__(parent)
        self.blocked = blocked                    # Signal(str): Meldung

    def interceptRequest(self, info):
        from downloads import download_guard, blocked_message
        wait, hint = download_guard.check(info.requestUrl().toString())
        if wait:
            info.block(True)
            self.blocked.emit(blocked_message(wait, hint))


class BrowserCore(QObject):
    """Gemeinsames Browser-Profil (im Speicher), Cookies, Downloads und das Rendern für Quellen."""
    download_finished = Signal(str, str)      # Pfad, URL
    download_failed = Signal(str, str)        # Dateiname, Grund
    download_progress = Signal(str)
    download_blocked = Signal(str)            # Meldung: Datei absichtlich nicht geladen
    _render_request = Signal(str, object)

    def __init__(self, store, download_folder, parent=None):
        super().__init__(parent)
        self.store = store
        self.download_folder = download_folder
        self.profile = QWebEngineProfile(self)            # ohne Namen = off the record, nichts auf der Platte
        self.profile.setHttpUserAgent(self.profile.httpUserAgent() + " SimVault")
        self.cookies = {}                                 # (Domain, Pfad, Name) -> Dict
        store_ = self.profile.cookieStore()
        store_.cookieAdded.connect(self._added)
        store_.cookieRemoved.connect(self._removed)
        self.load_error = ""
        try:
            for c in (store.all_cookies() if store else []):
                store_.setCookie(_to_qt(c), QUrl(f"https://{c.get('domain', '').lstrip('.')}/"))
        except Exception as e:                            # Anmeldungen nicht lesbar -> ohne weiter
            self.load_error = str(e)
        self.profile.downloadRequested.connect(self._download)
        self._limiter = _DownloadLimiter(self.download_blocked, self)
        self.profile.setUrlRequestInterceptor(self._limiter)
        self._render_request.connect(self._render)
        self._pages = []

    # -- Cookies -----------------------------------------------------------------
    def _added(self, cookie):
        c = _to_dict(cookie)
        self.cookies[(c["domain"], c["path"], c["name"])] = c

    def _removed(self, cookie):
        c = _to_dict(cookie)
        self.cookies.pop((c["domain"], c["path"], c["name"]), None)

    def cookies_for(self, host):
        domain = base_domain(host)
        return [c for c in self.cookies.values()
                if c["domain"].lstrip(".") == domain or c["domain"].lstrip(".").endswith("." + domain)]

    def save_login(self, source_id, host):
        """Speichert die Cookies der Seite verschlüsselt unter source_id. Gibt die Anzahl zurück."""
        cookies = self.cookies_for(host)
        if self.store and cookies:
            self.store.save(source_id, cookies)
        return len(cookies)

    # -- Downloads ---------------------------------------------------------------
    def _download(self, request):
        from web_session import safe_filename, unique_path
        os.makedirs(self.download_folder, exist_ok=True)
        name = safe_filename(request.downloadFileName() or "download")
        target = unique_path(self.download_folder, name)
        request.setDownloadDirectory(os.path.dirname(target))
        request.setDownloadFileName(os.path.basename(target))
        url = request.url().toString()

        def state_changed(state):
            if state == QWebEngineDownloadRequest.DownloadCompleted:
                self.download_finished.emit(target, url)
            elif state in (QWebEngineDownloadRequest.DownloadCancelled, QWebEngineDownloadRequest.DownloadInterrupted):
                self.download_failed.emit(name, request.interruptReasonString() or "abgebrochen")

        def received():
            total = request.totalBytes()
            done = request.receivedBytes() / 1048576
            self.download_progress.emit(f"lade {name}: {done:.1f}" + (f" / {total / 1048576:.1f} MB" if total > 0 else " MB"))

        request.stateChanged.connect(state_changed)
        request.receivedBytesChanged.connect(received)
        request.accept()

    # -- Rendern für Quellen (aus einem Hintergrund-Thread aufrufbar) -----------------
    def render(self, url, timeout=45, settle_ms=1500):
        """Lädt url im (unsichtbaren) Browser, wartet, bis JavaScript gelaufen ist, und gibt das HTML zurück."""
        holder = {"event": threading.Event(), "html": None, "error": None, "settle": settle_ms}
        self._render_request.emit(url, holder)
        if not holder["event"].wait(timeout):
            raise TimeoutError(f"Seite lädt nicht: {url}")
        if holder["error"]:
            raise OSError(holder["error"])
        return holder["html"]

    def _render(self, url, holder):
        page = QWebEnginePage(self.profile, self)
        self._pages.append(page)

        def finish(html=None, error=None):
            holder["html"], holder["error"] = html, error
            holder["event"].set()
            if page in self._pages:
                self._pages.remove(page)
            page.deleteLater()

        def loaded(ok):
            if not ok:
                finish(error=f"Seite nicht geladen: {url}")
                return
            QTimer.singleShot(holder["settle"], lambda: page.toHtml(lambda html: finish(html)))

        page.loadFinished.connect(loaded)
        page.load(QUrl(url))


class BrowserPane(QWidget):
    """Sichtbarer Browser mit Adresszeile und „Anmeldung speichern“."""
    login_saved = Signal(str, int)            # Quelle, Anzahl Cookies
    check_passed = Signal(str)                # Quelle, deren Prüfung (Captcha) gelöst ist
    checks_changed = Signal(list)             # Namen der wartenden Prüfungen

    def __init__(self, core, parent=None):
        super().__init__(parent)
        self.core = core
        self.login_source = None              # (id, Name) während einer Anmeldung
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        self.back = QPushButton("◀")
        self.forward = QPushButton("▶")
        self.reload = QPushButton("⟳")
        for b in (self.back, self.forward, self.reload):
            b.setFixedWidth(36)
        self.address = QLineEdit()
        self.address.setPlaceholderText("Adresse oder Suchbegriff …")
        self.save_login = QPushButton("Anmeldung speichern")
        self.save_login.setToolTip("Speichert die Anmeldung für diese Seite verschlüsselt (AES-256). "
                                   "Passwörter werden nie gespeichert.")
        for w in (self.back, self.forward, self.reload):
            bar.addWidget(w)
        bar.addWidget(self.address, 1)
        bar.addWidget(self.save_login)
        lay.addLayout(bar)
        self.hint = QLabel()
        self.hint.setObjectName("Muted")
        self.hint.setWordWrap(True)
        self.hint.hide()
        hint_row = QHBoxLayout()
        hint_row.addWidget(self.hint, 1)
        self.retry = QPushButton("Erneut suchen")
        self.retry.setToolTip("Prüfung gelöst? Dann bei dieser Quelle noch einmal suchen.")
        self.retry.hide()
        hint_row.addWidget(self.retry)
        lay.addLayout(hint_row)
        self.checks = []                      # offene Prüfungen: {"id", "name", "url"}
        self.view = QWebEngineView()
        self.view.setPage(QWebEnginePage(core.profile, self.view))
        lay.addWidget(self.view, 1)

        self.back.clicked.connect(self.view.back)
        self.forward.clicked.connect(self.view.forward)
        self.reload.clicked.connect(self.view.reload)
        self.address.returnPressed.connect(self._go)
        self.view.urlChanged.connect(lambda u: self.address.setText(u.toString()))
        self.save_login.clicked.connect(self._save_login)
        self.retry.clicked.connect(self._check_done)
        self.view.loadFinished.connect(self._check_loaded)

    def open(self, url):
        self.view.load(QUrl(url))

    def _go(self):
        text = self.address.text().strip()
        if not text:
            return
        if " " in text or "." not in text:
            from urllib.parse import quote_plus
            text = "https://www.google.com/search?q=" + quote_plus("sims 4 " + text)
        elif not text.startswith(("http://", "https://")):
            text = "https://" + text
        self.open(text)

    # -- Prüfungen (Captcha), die eine Suche aufgehalten haben ----------------------------
    def start_checks(self, checks):
        """Zeigt die Prüfseiten nacheinander; ist eine gelöst, kommt check_passed(Quelle)."""
        known = {c["id"] for c in self.checks}
        self.checks += [c for c in checks if c["id"] not in known]
        if self.checks:
            self._show_check()
        self.checks_changed.emit([c["name"] for c in self.checks])

    def _show_check(self):
        c = self.checks[0]
        rest = len(self.checks) - 1
        self.hint.setText(f"{c['name']} will prüfen, ob du ein Mensch bist – bitte hier lösen. Danach sucht "
                          f"SimVault dort von selbst noch einmal." + (f" (Danach noch {rest} weitere.)" if rest else ""))
        self.hint.show()
        self.retry.show()
        self.open(c["url"])

    def _check_loaded(self, ok):
        if not ok or not self.checks:
            return
        host = base_domain(urlparse(self.view.url().toString()).hostname or "")
        if host != base_domain(urlparse(self.checks[0]["url"]).hostname or ""):
            return

        def look(html):
            from sources.base import is_challenge
            if self.checks and not is_challenge(html):
                self._check_done()
        # kurz warten: nach dem Lösen leitet die Prüfseite selbst weiter
        QTimer.singleShot(1500, lambda: self.view.page().toHtml(look))

    def _check_done(self):
        if not self.checks:
            self.retry.hide()
            return
        c = self.checks.pop(0)
        self.checks_changed.emit([x["name"] for x in self.checks])
        self.check_passed.emit(c["id"])
        if self.checks:
            self._show_check()
        else:
            self.retry.hide()
            self.hint.setText(f"Prüfung bei {c['name']} erledigt – SimVault sucht dort noch einmal.")

    def start_login(self, source):
        """Öffnet die Anmeldeseite einer Quelle."""
        self.login_source = (source.id, source.name)
        self.hint.setText(f"Bei {source.name} anmelden – auch Zwei-Faktor-Codes und Captchas löst du hier selbst. "
                          "Danach „Anmeldung speichern“ klicken.")
        self.hint.show()
        self.open(source.login_url or source.homepage)

    def _save_login(self):
        host = urlparse(self.view.url().toString()).hostname or ""
        source_id = self.login_source[0] if self.login_source else base_domain(host)
        count = self.core.save_login(source_id, host)
        self.hint.setText(f"Anmeldung für {self.login_source[1] if self.login_source else base_domain(host)} "
                          f"gespeichert ({count} Cookies, verschlüsselt)." if count else
                          "Für diese Seite gibt es noch keine Cookies – erst anmelden.")
        self.hint.show()
        self.login_source = None
        self.login_saved.emit(source_id, count)

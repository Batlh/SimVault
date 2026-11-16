# Seite: Websuche – CC im Netz suchen, im eingebauten Browser stöbern, herunterladen und installieren
#
# Treffer:   Quellen, die echte Ergebnisse liefern (Voll-Quellen/Erweiterungen), zeigen Titel, Bild und Ersteller.
#            Alle anderen Quellen erscheinen als Knöpfe, die ihre Suche im eingebauten Browser öffnen.
# Browser:   sichtbares Chromium-Fenster – Anmelden, Captchas, Downloads. Was hier heruntergeladen wird,
#            landet im Download-Ordner und wird (wenn eingestellt) gleich installiert.
# Downloads: alle Downloads mit Status; „Installieren“ entpackt und legt Pakete, Scripts und Bibliotheks-
#            Dateien an die richtige Stelle – ohne Doppeltes und ohne zu überschreiben.

import os

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
                               QTabWidget, QVBoxLayout, QWidget)

from simvault.app import core
from simvault.web import downloads
from ..widgets import open_path, page_header


class WebPage(QWidget):
    def __init__(self, state):
        super().__init__()
        self.state = state
        self.results = []
        self.pending = []                       # Downloads, die auf die Installation warten
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.addWidget(page_header("Websuche", "CC im Netz suchen, im eingebauten Browser herunterladen – SimVault "
                                              "entpackt und installiert Downloads selbst, ohne Doppeltes."))
        top = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText("Suchbegriff, z. B. Ersteller und Name: „Kijiko eyelash“")
        self.query.returnPressed.connect(self.search)
        self.go = QPushButton("Suchen")
        self.go.setObjectName("Primary")
        self.go.clicked.connect(self.search)
        top.addWidget(self.query, 1)
        top.addWidget(self.go)
        lay.addLayout(top)
        self.link_row = QHBoxLayout()
        self.link_box = QWidget()
        self.link_box.setLayout(self.link_row)
        lay.addWidget(self.link_box)

        self.tabs = QTabWidget()
        # Treffer
        res = QWidget()
        rl = QVBoxLayout(res)
        self.info = QLabel("Noch keine Suche.")
        self.info.setObjectName("Muted")
        self.info.setWordWrap(True)
        rl.addWidget(self.info)
        self.list = QListWidget()
        self.list.setViewMode(QListWidget.IconMode)
        self.list.setIconSize(QSize(150, 150))
        self.list.setGridSize(QSize(190, 230))
        self.list.setResizeMode(QListWidget.Adjust)
        self.list.setWordWrap(True)
        self.list.setMovement(QListWidget.Static)
        self.list.itemDoubleClicked.connect(self._open_result)
        rl.addWidget(self.list, 1)
        rb = QHBoxLayout()
        open_btn = QPushButton("Im Browser öffnen")
        open_btn.clicked.connect(lambda: self._open_result(self.list.currentItem()))
        self.dl_btn = QPushButton("Herunterladen und installieren")
        self.dl_btn.clicked.connect(self._download_result)
        rb.addWidget(open_btn)
        rb.addWidget(self.dl_btn)
        rb.addStretch(1)
        rl.addLayout(rb)
        self.tabs.addTab(res, "Treffer")

        # Browser (wird erst beim ersten Öffnen gebaut – spart Start-Zeit und Speicher)
        self.browser_tab = QWidget()
        self.browser_lay = QVBoxLayout(self.browser_tab)
        self.browser_lay.setContentsMargins(0, 0, 0, 0)
        self.browser = None
        self.browser_core = None
        self.tabs.addTab(self.browser_tab, "Browser")

        # Downloads
        dl = QWidget()
        dlay = QVBoxLayout(dl)
        self.auto = QCheckBox("Downloads aus dem Browser sofort installieren")
        self.auto.setChecked(bool(state.cfg.get("auto_install", True)))
        self.auto.toggled.connect(self._auto_toggled)
        dlay.addWidget(self.auto)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Datei", "Zeit", "Status", "Ergebnis"])
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        dlay.addWidget(self.table, 1)
        db = QHBoxLayout()
        self.install_btn = QPushButton("Installieren")
        self.install_btn.setObjectName("Primary")
        self.install_btn.clicked.connect(self._install_selected)
        folder_btn = QPushButton("Download-Ordner öffnen")
        folder_btn.clicked.connect(lambda: open_path(core.download_folder(self.state.cfg)))
        remove_btn = QPushButton("Aus der Liste entfernen")
        remove_btn.clicked.connect(self._remove_selected)
        db.addWidget(self.install_btn)
        db.addWidget(folder_btn)
        db.addWidget(remove_btn)
        db.addStretch(1)
        dlay.addLayout(db)
        self.tabs.addTab(dl, "Downloads")
        lay.addWidget(self.tabs, 1)

        self.items = downloads.DownloadList(core.download_folder(state.cfg))
        self._fill_downloads()
        self.tabs.currentChanged.connect(lambda i: self.ensure_browser() if self.tabs.widget(i) is self.browser_tab
                                         else None)
        state.web_search.connect(self.search_for)
        state.show_checks.connect(lambda: self.tabs.setCurrentWidget(self.browser_tab))
        state.open_in_browser.connect(self.open_url)
        state.login_requested.connect(self.login)
        state.runner.busy_changed.connect(lambda busy: not busy and self._next_install())
        state.runner.busy_changed.connect(lambda busy: not busy and self._next_research())
        self._query = ""
        self._checks = []
        self._research = []                   # Quellen, bei denen nach gelöster Prüfung neu gesucht wird
        self._attempts = {}                   # Quelle -> wie oft schon nach einer Prüfung neu gesucht

    # -- Browser ---------------------------------------------------------------------
    def ensure_browser(self):
        if self.browser is not None:
            return self.browser
        from ..browser import BrowserCore, BrowserPane
        self.browser_core = BrowserCore(core.secure_store(self.state.cfg), core.download_folder(self.state.cfg), self)
        self.browser = BrowserPane(self.browser_core)
        self.browser_lay.addWidget(self.browser)
        self.browser_core.download_finished.connect(self._browser_download)
        self.browser_core.download_failed.connect(
            lambda name, why: self.state.message.emit(f"Download {name} fehlgeschlagen: {why}"))
        self.browser_core.download_progress.connect(self.state.message.emit)
        self.browser_core.download_blocked.connect(self._download_blocked)
        self.browser.check_passed.connect(self._check_passed)
        self.browser.checks_changed.connect(self.state.checks_waiting.emit)
        self.browser.login_saved.connect(lambda sid, n: self.state.message.emit(
            f"Anmeldung gespeichert ({n} Cookies, verschlüsselt)." if n else "Keine Cookies zum Speichern."))
        if self.browser_core.load_error:
            self.browser.hint.setText(f"Gespeicherte Anmeldungen nicht lesbar: {self.browser_core.load_error}")
            self.browser.hint.show()
        return self.browser

    def _download_blocked(self, message):
        self.state.message.emit(message)
        self.browser.hint.setText(message)
        self.browser.hint.show()

    def open_url(self, url):
        self.ensure_browser().open(url)
        self.tabs.setCurrentWidget(self.browser_tab)

    def login(self, source):
        self.ensure_browser().start_login(source)
        self.tabs.setCurrentWidget(self.browser_tab)

    def renderer(self):
        """Funktion url -> HTML für Quellen (aus dem Hintergrund aufrufbar)."""
        self.ensure_browser()
        return self.browser_core.render

    # -- Suche -------------------------------------------------------------------------
    def set_busy(self, busy):
        self.go.setEnabled(not busy)
        self.dl_btn.setEnabled(not busy)

    def search_for(self, query):
        self.query.setText(query)
        self.search()

    def search(self):
        query = self.query.text().strip()
        if not query:
            return
        from simvault.web import sources
        enabled = sources.enabled_sources(self.state.cfg)
        full = [s for s in enabled if s.can_search]
        self._show_links({s.name: s.search_url(query) for s in enabled if s.search_url(query)})
        if not full:
            self.results = []
            self.list.clear()
            self.info.setText("Keine eingeschaltete Quelle liefert eigene Trefferlisten – die Knöpfe oben öffnen die "
                              "Suche der jeweiligen Seite im eingebauten Browser. Quellen mit Trefferlisten kommen "
                              "als Erweiterung dazu (Seite „Quellen“).")
            self.tabs.setCurrentIndex(0)
            return
        cfg = self.state.cfg
        session = core.web_session(cfg, renderer=self.renderer())
        self.info.setText(f"Suche „{query}“ …")
        self._query, self._checks, self._research, self._attempts = query, [], [], {}
        checks = self._checks
        self.state.runner.start(lambda progress, should_stop: core.web_search(cfg, query, session, progress,
                                                                                should_stop, checks=checks),
                                on_done=self._searched, on_error=lambda m: QMessageBox.warning(self, "Websuche", m))

    # -- Prüfungen (Captcha) ---------------------------------------------------------
    def _check_passed(self, source_id):
        self._attempts[source_id] = self._attempts.get(source_id, 0) + 1
        if source_id not in self._research:
            self._research.append(source_id)
        self._next_research()

    def _next_research(self):
        if not self._research or not self._query or self.state.runner.busy:
            return
        source_id = self._research.pop(0)
        cfg, query = self.state.cfg, self._query
        session = core.web_session(cfg, renderer=self.renderer())
        checks = self._checks
        self.state.runner.start(
            lambda progress, should_stop: core.web_search(cfg, query, session, progress, should_stop,
                                                          only={source_id}, checks=checks),
            on_done=lambda result: self._merged(source_id, result),
            on_error=lambda m: self.state.message.emit(f"Websuche: {m}"))

    def _merged(self, source_id, result):
        found, _links, errors = result
        if self._query and found is not None:
            results = [r for r in self.results if r.source_id != source_id] + found
            self._searched((results, _links, errors), switch=False)

    def _show_links(self, links):
        while self.link_row.count():
            w = self.link_row.takeAt(0).widget()
            if w:
                w.deleteLater()
        for name, url in links.items():
            b = QPushButton(name)
            b.setToolTip(url)
            b.clicked.connect(lambda _c=False, u=url: self.open_url(u))
            self.link_row.addWidget(b)
        self.link_row.addStretch(1)

    def _searched(self, result, switch=True):
        results, _links, errors = result
        self.results = results
        self.list.clear()
        for r in results:
            text = r.title + (f"\nvon {r.creator}" if r.creator else "") + f"\n{r.extra.get('quelle', '')}" \
                + (f" · {r.extra['zugang']}" if r.extra.get("zugang") else "")
            item = QListWidgetItem(text)
            pix = QPixmap()
            if r.extra.get("bild") and pix.loadFromData(r.extra["bild"]):
                item.setIcon(QIcon(pix.scaled(150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
            item.setToolTip(r.description or r.url)
            self.list.addItem(item)
        msg = f"{len(results)} Treffer."
        if errors:
            msg += " Nicht erreichbar: " + "; ".join(f"{n} ({m[:80]})" for n, m in errors)
        self.info.setText(msg)
        pending = [c for c in self._checks if c["id"] not in self._research and self._attempts.get(c["id"], 0) < 3]
        self._checks[:] = []
        if pending:                           # Captcha zeigen, statt still keine Treffer zu liefern
            self.ensure_browser().start_checks(pending)
            self.tabs.setCurrentWidget(self.browser_tab)
        elif switch:
            self.tabs.setCurrentIndex(0)

    def _result(self, item=None):
        item = item or self.list.currentItem()
        return self.results[self.list.row(item)] if item is not None else None

    def _open_result(self, item):
        r = self._result(item)
        if r:
            self.open_url(r.url)

    def _download_result(self):
        r = self._result()
        if not r:
            return
        cfg = self.state.cfg
        session = core.web_session(cfg)

        def job(progress, should_stop):
            return core.download_result(cfg, r, progress, should_stop, session)

        def done(result):
            items, rest = result
            if items is None:                       # Wartezeit/Anmeldung: im eingebauten Browser herunterladen
                self.state.message.emit("Der Download läuft über die Seite – im Browser starten, SimVault installiert "
                                        "die Datei danach selbst.")
                self.open_url(rest)
                return
            self.items = rest
            self._fill_downloads()
            self.pending.extend(items)
            self.tabs.setCurrentIndex(2)

        self.state.runner.start(job, on_done=done, on_error=lambda m: QMessageBox.warning(self, "Download", m))

    # -- Downloads ---------------------------------------------------------------------
    def _auto_toggled(self, on):
        raw = dict(self.state.raw)
        raw["auto_install"] = on
        self.state.save_config(raw)

    def _browser_download(self, path, url):
        item = self.items.add(path, url, "Browser")
        self._fill_downloads()
        self.state.message.emit(f"Heruntergeladen: {os.path.basename(path)}")
        if self.auto.isChecked():
            self.pending.append(item)
            self._next_install()

    def _next_install(self):
        """Installiert wartende Downloads nacheinander (immer nur eine Aufgabe gleichzeitig)."""
        if not self.pending or self.state.runner.busy:
            return
        item = self.pending.pop(0)
        cfg = self.state.cfg
        self.items.update(item, "wird installiert")
        self._fill_downloads()

        def done(result):
            self.items.update(item, "installiert" if result["installiert"] else
                              ("übersprungen" if not result["fehler"] else "Fehler"), downloads.summary(result))
            self._fill_downloads()
            details = [f"+ {os.path.relpath(p, cfg['mods_folder']) if p.startswith(cfg['mods_folder']) else p}"
                       for _k, p in result["installiert"][:10]]
            details += [f"= {n}: {why}" for n, why in result["uebersprungen"][:5]]
            details += [f"! {n}: {why}" for n, why in result["fehler"][:5]]
            self.state.message.emit(f"{os.path.basename(item['datei'])}: {downloads.summary(result)}")
            if result["fehler"] and not result["installiert"]:
                QMessageBox.warning(self, "Installieren", "\n".join(details))

        def failed(message):
            self.items.update(item, "Fehler", message.splitlines()[0])
            self._fill_downloads()

        self.state.runner.start(lambda progress, should_stop: core.install_download(cfg, item["datei"], progress),
                                on_done=done, on_error=failed)

    def _selected(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        return [self.items.items[r] for r in rows if r < len(self.items.items)]

    def _install_selected(self):
        for item in self._selected():
            if item not in self.pending:
                self.pending.append(item)
        self._next_install()

    def _remove_selected(self):
        for item in self._selected():
            self.items.remove(item)
        self._fill_downloads()

    def _fill_downloads(self):
        self.table.setRowCount(len(self.items.items))
        for row, it in enumerate(self.items.items):
            from simvault.app import i18n
            for col, text in enumerate([os.path.basename(it["datei"]), it["zeit"].replace("T", " "),
                                        i18n.tr(it["status"]), i18n.tr(it["ergebnis"])]):
                cell = QTableWidgetItem(text)
                cell.setToolTip(it["datei"] if col == 0 else text)
                self.table.setItem(row, col, cell)
        self.table.resizeColumnsToContents()

# Seite: Quellen – mitgelieferte Quellen und Erweiterungen anzeigen, an-/ausschalten, Suche testen

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QTableWidget, QTableWidgetItem, QTextBrowser, QVBoxLayout, QWidget)

import core
import sources
from ..widgets import open_path, page_header


class SourcesPage(QWidget):
    def __init__(self, state):
        super().__init__()
        self.state = state
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.addWidget(page_header("Quellen", "Webseiten für die CC-Suche. Neue Quellen ergänzt du als Erweiterung: "
                                             "eine .json-Datei (nur Such-Link) oder eine .py-Datei (echte Treffer, "
                                             "auch mit Login) im Erweiterungs-Ordner – Anleitung: plugins/README.md."))
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["Aktiv", "Name", "Art", "Login", "Angemeldet", "18+", "Herkunft"])
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)
        self.table.itemChanged.connect(self._toggled)
        lay.addWidget(self.table, 1)

        btns = QHBoxLayout()
        open_btn = QPushButton("Erweiterungs-Ordner öffnen")
        open_btn.clicked.connect(self._open_plugins)
        reload_btn = QPushButton("Neu laden")
        reload_btn.clicked.connect(self.refresh)
        self.login_btn = QPushButton("Anmelden …")
        self.login_btn.setToolTip("Öffnet die Anmeldeseite im eingebauten Browser. Gespeichert werden nur die Cookies "
                                  "danach – verschlüsselt (AES-256), nie das Passwort.")
        self.login_btn.clicked.connect(self._login)
        self.logout_btn = QPushButton("Abmelden")
        self.logout_btn.clicked.connect(self._logout)
        btns.addWidget(open_btn)
        btns.addWidget(reload_btn)
        btns.addStretch(1)
        btns.addWidget(self.login_btn)
        btns.addWidget(self.logout_btn)
        lay.addLayout(btns)
        import secure_store
        self.protection = QLabel(f"Anmeldungen: verschlüsselt mit AES-256-GCM, Schlüssel geschützt durch "
                                 f"{secure_store.key_protection()}. Passwörter werden nie gespeichert.")
        self.protection.setObjectName("Muted")
        self.protection.setWordWrap(True)
        lay.addWidget(self.protection)

        self.errors = QLabel()
        self.errors.setWordWrap(True)
        self.errors.setStyleSheet("color: #e5534b;")
        lay.addWidget(self.errors)

        test = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText("Suche testen, z. B. „Kijiko eyelash“ …")
        go = QPushButton("Links erzeugen")
        web = QPushButton("Im Programm suchen")
        web.clicked.connect(lambda: self.query.text().strip() and self.state.web_search.emit(self.query.text().strip()))
        go.clicked.connect(self._test)
        self.query.returnPressed.connect(self._test)
        test.addWidget(self.query, 1)
        test.addWidget(go)
        test.addWidget(web)
        lay.addLayout(test)
        self.links = QTextBrowser()
        self.links.setOpenLinks(False)
        self.links.anchorClicked.connect(lambda u: self.state.open_in_browser.emit(u.toString()))
        self.links.setMaximumHeight(160)
        lay.addWidget(self.links)

        state.config_changed.connect(self.refresh)
        self.refresh()

    def _logins(self):
        try:
            return core.secure_store(self.state.cfg).logins()
        except Exception:
            return {}

    def refresh(self):
        self._loading = True
        self.srcs, errors = sources.load_sources(self.state.cfg)
        logins = self._logins()
        self.table.setRowCount(len(self.srcs))
        for row, s in enumerate(self.srcs):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            check.setCheckState(Qt.Checked if sources.is_enabled(s, self.state.cfg) else Qt.Unchecked)
            check.setData(Qt.UserRole, s.id)
            self.table.setItem(row, 0, check)
            saved = logins.get(s.id)
            when = ""
            if saved:
                from datetime import datetime
                when = datetime.fromtimestamp(saved["gespeichert"]).strftime("%d.%m.%Y")
            for col, text in enumerate([s.name, "Treffer" if s.can_search else "Such-Link",
                                        "nötig" if s.needs_login else ("möglich" if s.login_url else ""),
                                        f"ja, seit {when}" if saved else "", "ja" if s.adult else "",
                                        s.origin], start=1):
                item = QTableWidgetItem(text)
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.table.setItem(row, col, item)
        self.table.resizeColumnsToContents()
        self.errors.setText("\n".join(f"Erweiterung nicht geladen: {os.path.basename(p)} – {m}" for p, m in errors))
        self._loading = False

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()                     # Anmeldestatus kann sich im Browser geändert haben

    def _current(self):
        row = self.table.currentRow()
        return self.srcs[row] if 0 <= row < len(self.srcs) else None

    def _login(self):
        src = self._current()
        if not src:
            QMessageBox.information(self, "Anmelden", "Bitte zuerst eine Quelle in der Liste auswählen.")
            return
        if not (src.login_url or src.homepage):
            QMessageBox.information(self, "Anmelden", f"Für {src.name} ist keine Anmeldeseite bekannt.")
            return
        self.state.login_requested.emit(src)

    def _logout(self):
        src = self._current()
        if not src:
            return
        try:
            core.secure_store(self.state.cfg).forget(src.id)
        except Exception as e:
            QMessageBox.warning(self, "Abmelden", str(e))
        self.state.message.emit(f"Anmeldung für {src.name} gelöscht (wirkt im Browser nach dem nächsten Start).")
        self.refresh()

    def _toggled(self, item):
        if self._loading or item.column() != 0:
            return
        raw = dict(self.state.raw)
        enabled = dict(raw.get("sources_enabled") or {})
        enabled[item.data(Qt.UserRole)] = item.checkState() == Qt.Checked
        raw["sources_enabled"] = enabled
        self.state.save_config(raw)

    def _open_plugins(self):
        folder = sources.user_plugin_dir()
        os.makedirs(folder, exist_ok=True)
        readme = os.path.join(folder, "LIESMICH.txt")
        if not os.path.exists(readme):
            with open(readme, "w", encoding="utf-8") as f:
                f.write("Hier eigene Quellen ablegen: .json (Such-Link) oder .py (echte Treffer).\n"
                        "Anleitung und Beispiele: plugins/README.md im SimVault-Ordner bzw. auf GitHub.\n")
        open_path(folder)

    def _test(self):
        import cc_searcher
        query = self.query.text().strip()
        if not query:
            return
        links = cc_searcher.search_links(query, self.state.cfg)
        self.links.setHtml("<br>".join(f"<a href='{u}'>{n}</a>" for n, u in links.items()))

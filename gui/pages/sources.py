# Seite: Quellen – mitgelieferte Quellen und Erweiterungen anzeigen, an-/ausschalten, Suche testen

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QTableWidget,
                               QTableWidgetItem, QTextBrowser, QVBoxLayout, QWidget)

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
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Aktiv", "Name", "Art", "Login", "18+", "Herkunft"])
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.table.itemChanged.connect(self._toggled)
        lay.addWidget(self.table, 1)

        btns = QHBoxLayout()
        open_btn = QPushButton("Erweiterungs-Ordner öffnen")
        open_btn.clicked.connect(self._open_plugins)
        reload_btn = QPushButton("Neu laden")
        reload_btn.clicked.connect(self.refresh)
        btns.addWidget(open_btn)
        btns.addWidget(reload_btn)
        btns.addStretch(1)
        lay.addLayout(btns)

        self.errors = QLabel()
        self.errors.setWordWrap(True)
        self.errors.setStyleSheet("color: #e5534b;")
        lay.addWidget(self.errors)

        test = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText("Suche testen, z. B. „Kijiko eyelash“ …")
        go = QPushButton("Links erzeugen")
        go.clicked.connect(self._test)
        self.query.returnPressed.connect(self._test)
        test.addWidget(self.query, 1)
        test.addWidget(go)
        lay.addLayout(test)
        self.links = QTextBrowser()
        self.links.setOpenExternalLinks(True)
        self.links.setMaximumHeight(160)
        lay.addWidget(self.links)

        state.config_changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        self._loading = True
        self.srcs, errors = sources.load_sources(self.state.cfg)
        self.table.setRowCount(len(self.srcs))
        for row, s in enumerate(self.srcs):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            check.setCheckState(Qt.Checked if sources.is_enabled(s, self.state.cfg) else Qt.Unchecked)
            check.setData(Qt.UserRole, s.id)
            self.table.setItem(row, 0, check)
            for col, text in enumerate([s.name, "Treffer" if s.can_search else "Such-Link",
                                        "ja" if s.needs_login else "", "ja" if s.adult else "",
                                        s.origin], start=1):
                item = QTableWidgetItem(text)
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.table.setItem(row, col, item)
        self.table.resizeColumnsToContents()
        self.errors.setText("\n".join(f"Erweiterung nicht geladen: {os.path.basename(p)} – {m}" for p, m in errors))
        self._loading = False

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

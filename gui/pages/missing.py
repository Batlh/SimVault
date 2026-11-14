# Seite: Fehlende CC – Teile, die verwendet werden, aber nicht installiert sind,
#        und die Bibliotheks-Haushalte mit Ersteller, Beschreibung und Links

import html

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMenu, QPushButton, QSplitter, QTableView, QTabWidget,
                               QTextBrowser, QVBoxLayout, QWidget)

from ..widgets import DictTableModel, FilterProxy, fit_columns, open_url, page_header


class MissingPage(QWidget):
    navigate = Signal(str)

    def __init__(self, state):
        super().__init__()
        self.state = state
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.addWidget(page_header("Fehlende CC", "CAS-Teile und Objekte, die in Spielständen oder der Bibliothek "
                                                 "verwendet werden, aber nicht installiert sind."))
        self.info = QLabel()
        self.info.setObjectName("Muted")
        self.info.setWordWrap(True)
        lay.addWidget(self.info)

        tabs = QTabWidget()
        # Tab 1: Teile
        parts = QWidget()
        pl = QVBoxLayout(parts)
        top = QHBoxLayout()
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filtern (ID, Art, Sim, Haushalt …)")
        search_btn = QPushButton("Auf dem PC suchen")
        search_btn.setObjectName("Primary")
        search_btn.clicked.connect(lambda: self.navigate.emit("CC-Suche"))
        top.addWidget(self.filter, 1)
        top.addWidget(search_btn)
        pl.addLayout(top)
        self.model = DictTableModel([
            ("ID", "id"), ("Art", "art"), ("Anzahl", "anzahl"), ("Verwendet von", "verwendet_von"),
            ("Quellen", "quellen"), ("Gefunden in", "gefunden_in")])
        self.proxy = FilterProxy()
        self.proxy.setSourceModel(self.model)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().hide()
        fit_columns(self.table, stretch=3, fit=(0, 2), widths={1: 190, 4: 130, 5: 200})
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._copy_menu)
        pl.addWidget(self.table)
        self.filter.textChanged.connect(self.proxy.setFilterFixedString)
        tabs.addTab(parts, "Teile")

        # Tab 2: Bibliothek
        lib = QSplitter()
        self.households = QListWidget()
        self.detail = QTextBrowser()
        # Links (CC-Listen in der Beschreibung, Suche) im eingebauten Browser öffnen: dort heruntergeladene
        # CC wird gleich installiert
        self.detail.setOpenLinks(False)
        self.detail.anchorClicked.connect(self._link)
        lib.addWidget(self.households)
        lib.addWidget(self.detail)
        lib.setSizes([320, 700])
        self.households.currentRowChanged.connect(self._show_household)
        tabs.addTab(lib, "Bibliothek")
        lay.addWidget(tabs, 1)

        state.analysis_changed.connect(self.refresh)
        state.found_changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        a = self.state.analysis
        missing = (a or {}).get("missing") or {"teile": [], "bibliothek": []}
        found_at = {}
        for item in (self.state.found or {}).get("dateien", []):
            for i in item["ids"]:
                found_at.setdefault(i, []).append(item["datei"])
        rows = [dict(p, gefunden_in=found_at.get(p["id"], [])) for p in missing["teile"]]
        self.model.set_rows(rows)
        self.table.sortByColumn(2, Qt.DescendingOrder)
        if a:
            found = sum(1 for r in rows if r["gefunden_in"])
            self.info.setText(f"{len(rows)} fehlende Teile, davon {found} auf dem PC gefunden. "
                              f"{a.get('missing_info') or ''}")
        else:
            self.info.setText("Noch keine Analyse – auf der Übersicht „Analyse starten“.")
        self.households.clear()
        self._households = missing["bibliothek"]
        for h in self._households:
            by = f" – {h['ersteller']}" if h["ersteller"] else ""
            QListWidgetItem(f"{h['name']}{by}  ({len(h['fehlend'])} fehlend)", self.households)
        if self._households:
            self.households.setCurrentRow(0)
        else:
            self.detail.setHtml("<p>Keine Bibliotheks-Einträge mit fehlender CC.</p>")

    def _show_household(self, row):
        if row < 0 or row >= len(self._households):
            return
        h = self._households[row]
        from collections import Counter
        arts = Counter(p["art"].split(" (")[0] for p in h["fehlend"])
        desc = html.escape(h["beschreibung"])
        for link in h["links"]:
            desc = desc.replace(html.escape(link), f"<a href='{html.escape(link)}'>{html.escape(link)}</a>")
        picture = ""
        if h.get("bild"):
            import thumbnails
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QTextDocument
            from ..widgets import thumbnail_pixmap
            data = thumbnails.tray_image(h["bild"])
            pixmap = thumbnail_pixmap(data, 300) if data else None
            if pixmap:
                self.detail.document().addResource(QTextDocument.ImageResource, QUrl("tray://bild"), pixmap)
                picture = "<p><img src='tray://bild'></p>"
        orig = (f"<br>ursprünglich von {html.escape(h['original_ersteller'])}"
                if h["original_ersteller"] and h["original_ersteller"] != h["ersteller"] else "")
        self.detail.setHtml(
            f"{picture}<h2>{html.escape(h['name'])}</h2>"
            f"<p>{html.escape(h['typ'])} von <b>{html.escape(h['ersteller'] or 'unbekannt')}</b>{orig}"
            f" · {html.escape(h['datum'])}</p>"
            f"<p><b>Fehlt:</b> {html.escape(', '.join(f'{n}× {a}' for a, n in arts.most_common()))}</p>"
            f"<p>{desc}</p>"
            f"<p><a href='simvault:suche'>In SimVault im Netz suchen</a> · "
            f"<a href='{html.escape(h['suche'])}'>Google-Suche nach Haushalt und CC</a></p>"
            "<p style='color:#8b949e'>Links öffnen sich im eingebauten Browser – was du dort herunterlädst, "
            "installiert SimVault gleich.</p>")

    def _link(self, url):
        if url.scheme() == "simvault":
            row = self.households.currentRow()
            if 0 <= row < len(self._households):
                h = self._households[row]
                self.state.web_search.emit(" ".join(t for t in (h["ersteller"], h["name"]) if t))
        elif url.scheme() in ("http", "https"):
            self.state.open_in_browser.emit(url.toString())

    def _copy_menu(self, pos):
        idx = self.table.indexAt(pos)
        if not idx.isValid():
            return
        row = self.model.rows[self.proxy.mapToSource(idx).row()]
        menu = QMenu(self)
        menu.addAction("ID kopieren", lambda: self._copy(row["id"]))
        menu.exec(self.table.viewport().mapToGlobal(pos))

    @staticmethod
    def _copy(text):
        from PySide6.QtGui import QGuiApplication
        QGuiApplication.clipboard().setText(text)

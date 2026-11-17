# Seite: Mods – alle Mod-Dateien mit Status, Filter und Vorschaubildern

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QMenu, QPushButton, QScrollArea, QSplitter, QTableView, QVBoxLayout,
                               QWidget)

from simvault.analysis import thumbnails
from ..widgets import DictTableModel, FilterProxy, fit_columns, open_path, open_url, page_header, thumbnail_pixmap

STATUSES = ["alle", "genutzt", "ungenutzt", "nicht nachweisbar", "nicht prüfbar", "defekt"]


def _mb(n):
    return round(n / (1024 * 1024), 1)


class ModsPage(QWidget):
    def __init__(self, state):
        super().__init__()
        self.state = state
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.addWidget(page_header("Mods", "Alle .package- und .ts4script-Dateien mit Nutzung. "
                                          "„ungenutzt“ = CAS-/Objekt-CC, die in keinem Spielstand und "
                                          "keinem Bibliothekseintrag vorkommt."))
        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filtern …")
        self.status = QComboBox()
        self.status.addItems(STATUSES)
        filters.addWidget(self.search, 1)
        filters.addWidget(QLabel("Status:"))
        filters.addWidget(self.status)
        lay.addLayout(filters)

        self.model = DictTableModel([
            ("Datei", "datei"), ("Ordner", "ordner"), ("Kategorie", "kategorie"), ("Status", "status"),
            ("Spielstände", "spielstaende"), ("Tray", "tray"), ("MB", "mb"),
        ], color_key="status")
        self.proxy = FilterProxy()
        self.proxy.setSourceModel(self.model)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().hide()
        fit_columns(self.table, stretch=4, fit=(2, 3, 5, 6), widths={0: 280, 1: 130})
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._menu)

        detail = QWidget()
        dl = QVBoxLayout(detail)
        dl.setContentsMargins(12, 0, 0, 0)
        self.title = QLabel("Datei auswählen")
        self.title.setWordWrap(True)
        self.title.setStyleSheet("font-weight: 600;")
        self.meta = QLabel()
        self.meta.setObjectName("Muted")
        self.meta.setWordWrap(True)
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setSpacing(6)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.grid_host)
        btns = QHBoxLayout()
        self.show_btn = QPushButton("Im Explorer zeigen")
        self.show_btn.clicked.connect(self._show_in_explorer)
        self.web_btn = QPushButton("Im Netz suchen …")
        self.web_btn.clicked.connect(self._search_menu)
        btns.addWidget(self.show_btn)
        btns.addWidget(self.web_btn)
        dl.addWidget(self.title)
        dl.addWidget(self.meta)
        dl.addWidget(scroll, 1)
        dl.addLayout(btns)

        split = QSplitter()
        split.addWidget(self.table)
        split.addWidget(detail)
        split.setSizes([760, 380])
        lay.addWidget(split, 1)

        self.search.textChanged.connect(self.proxy.setFilterFixedString)
        self.status.currentTextChanged.connect(
            lambda s: self.proxy.set_field_filter("status", None if s == "alle" else s))
        self.table.selectionModel().selectionChanged.connect(self._selected)
        state.analysis_changed.connect(self.refresh)
        self.current = None
        self.refresh()

    def refresh(self):
        a = self.state.analysis
        rows = []
        if a:
            for r in a["usage"]:
                m = r["mod"]
                rows.append({"datei": os.path.basename(m.rel_path), "ordner": os.path.dirname(m.rel_path),
                             "kategorie": m.category, "status": r["status"],
                             "spielstaende": r["saves"], "tray": r["tray"] or "", "mb": _mb(m.size),
                             "_mod": m})
        self.model.set_rows(rows)
        self.table.sortByColumn(0, Qt.AscendingOrder)

    def _row(self):
        idx = self.table.selectionModel().selectedRows()
        if not idx:
            return None
        return self.model.rows[self.proxy.mapToSource(idx[0]).row()]

    def _selected(self, *_):
        row = self._row()
        self.current = row
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        if not row:
            return
        m = row["_mod"]
        self.title.setText(os.path.basename(m.rel_path))
        saves = ", ".join(row["spielstaende"]) or "–"
        self.meta.setText(f"{m.rel_path}\n{m.category} · {row['status']} · {row['mb']} MB · "
                          f"{m.resource_count} Ressourcen\nSpielstände: {saves}")
        if m.kind != "package":
            return
        images = thumbnails.thumbnails(m.path, limit=24)
        if not images:
            note = QLabel("Keine Vorschaubilder in diesem Paket.")
            note.setObjectName("Muted")
            self.grid.addWidget(note, 0, 0)
        for i, (_inst, data) in enumerate(images):
            pix = thumbnail_pixmap(data, 150)
            if pix is None:
                continue
            label = QLabel()
            label.setPixmap(pix)
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet("background: #1b1e22; border-radius: 6px; padding: 4px;")
            self.grid.addWidget(label, i // 2, i % 2)

    def _show_in_explorer(self):
        if self.current:
            open_path(os.path.dirname(self.current["_mod"].path))

    def _search_menu(self):
        if not self.current:
            return
        from simvault.finder import cc_searcher
        menu = QMenu(self)
        for name, url in cc_searcher.search_links(self.current["datei"], self.state.cfg).items():
            menu.addAction(name, lambda u=url: open_url(u))
        menu.exec(self.web_btn.mapToGlobal(self.web_btn.rect().bottomLeft()))

    def _menu(self, pos):
        if self._row():
            menu = QMenu(self)
            menu.addAction("Im Explorer zeigen", self._show_in_explorer)
            menu.addAction("Im Netz suchen …", self._search_menu)
            menu.exec(self.table.viewport().mapToGlobal(pos))

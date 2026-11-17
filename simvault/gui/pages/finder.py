# Seite: CC-Suche – fehlende CC auf dem PC suchen (Ordner, Laufwerke, ZIP/RAR/7z) und zurückholen

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QFileDialog, QGroupBox, QHBoxLayout, QHeaderView,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
                               QSplitter, QTableView, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from simvault.app import core
from simvault.finder import cc_finder
from .. import theme
from ..widgets import DictTableModel, FilterProxy, fit_columns, open_path, page_header


class FinderPage(QWidget):
    def __init__(self, state):
        super().__init__()
        self.state = state
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.addWidget(page_header("CC-Suche", "Sucht die fehlende CC in Ordnern, auf weiteren Laufwerken und in "
                                              "ZIP-/RAR-/7z-Archiven. Entpacktes wird sofort wieder gelöscht."))
        split = QSplitter(Qt.Vertical)

        # Oben: Suchorte und Start
        top = QWidget()
        tl = QHBoxLayout(top)
        tl.setContentsMargins(0, 0, 0, 0)
        where = QGroupBox("Wo suchen?")
        wl = QVBoxLayout(where)
        self.locations = QListWidget()
        wl.addWidget(self.locations)
        row = QHBoxLayout()
        add = QPushButton("Ordner hinzufügen …")
        add.clicked.connect(self._add_folder)
        self.drives = QCheckBox("weitere Laufwerke (D:, E:, USB …)")
        self.whole = QCheckBox("auch ganz C:")
        self.drives.toggled.connect(self._fill_locations)
        self.whole.toggled.connect(self._fill_locations)
        row.addWidget(add)
        row.addWidget(self.drives)
        row.addWidget(self.whole)
        row.addStretch(1)
        wl.addLayout(row)
        tl.addWidget(where, 1)

        actions = QVBoxLayout()
        self.start_btn = QPushButton("Suche starten")
        self.start_btn.setObjectName("Primary")
        self.start_btn.clicked.connect(self.start)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setObjectName("Muted")
        actions.addWidget(self.start_btn)
        actions.addWidget(self.summary)
        actions.addStretch(1)
        restore_box = QGroupBox("Zurückholen")
        rl = QVBoxLayout(restore_box)
        self.exclude = QLineEdit()
        self.exclude.setPlaceholderText("auslassen, z. B.: WickedWhims")
        self.backup_first = QCheckBox("vorher Mods-Ordner sichern")
        self.backup_first.setChecked(True)
        self.restore_btn = QPushButton("Funde in den Mods-Ordner holen")
        self.restore_btn.clicked.connect(self.restore)
        rl.addWidget(self.exclude)
        rl.addWidget(self.backup_first)
        rl.addWidget(self.restore_btn)
        actions.addWidget(restore_box)
        tl.addLayout(actions)
        split.addWidget(top)

        # Unten: Funde und nicht lesbare Archive
        bottom = QSplitter()
        self.model = DictTableModel([
            ("Datei", "datei"), ("Teile", "anzahl_ids"), ("Art", "arten"), ("Für", "verwendet_von"),
            ("Fundort", lambda d: f"{d['pfad']} → {d['archiv_eintrag']}" if d.get("archiv_eintrag") else d["pfad"]),
            ("weitere Orte", lambda d: len(d.get("weitere_fundorte") or []))])
        self.proxy = FilterProxy()
        self.proxy.setSourceModel(self.model)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().hide()
        fit_columns(self.table, stretch=4, fit=(1, 5), widths={0: 230, 2: 120, 3: 200})
        self.table.doubleClicked.connect(self._open_location)
        self.unreadable = QTreeWidget()
        self.unreadable.setHeaderLabels(["Nicht durchsuchbar", "Grund"])
        self.unreadable.setColumnWidth(0, 260)
        bottom.addWidget(self.table)
        bottom.addWidget(self.unreadable)
        bottom.setSizes([850, 400])
        split.addWidget(bottom)
        split.setSizes([260, 500])
        lay.addWidget(split, 1)

        self.extra_folders = []
        state.config_changed.connect(self._load_options)
        state.found_changed.connect(self.refresh)
        self._load_options()
        self.refresh()

    # -- Suchorte ---------------------------------------------------------------
    def _load_options(self):
        self.drives.blockSignals(True)
        self.drives.setChecked(bool(self.state.cfg.get("search_drives", True)))
        self.drives.blockSignals(False)
        self._fill_locations()

    def _fill_locations(self):
        self.locations.clear()
        locs = core.search_locations(self.state.cfg, (self.state.cfg.get("search_folders") or [])
                                     + self.extra_folders or None,
                                     drives=self.drives.isChecked(), whole_pc=self.whole.isChecked())
        for path in locs:
            item = QListWidgetItem(path)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            self.locations.addItem(item)
        if not locs:
            hint = QListWidgetItem("Keine Standard-Orte gefunden – mit „Ordner hinzufügen …“ Ordner auswählen "
                                   "oder „weitere Laufwerke“ anhaken.")
            hint.setFlags(Qt.NoItemFlags)
            self.locations.addItem(hint)

    def _add_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Ordner zum Durchsuchen wählen", os.path.expanduser("~"))
        if path:
            self.extra_folders.append(os.path.normpath(path))
            self._fill_locations()

    def _checked_locations(self):
        return [self.locations.item(i).text() for i in range(self.locations.count())
                if self.locations.item(i).flags() & Qt.ItemIsUserCheckable
                and self.locations.item(i).checkState() == Qt.Checked]

    # -- Suche -------------------------------------------------------------------
    def set_busy(self, busy):
        self.start_btn.setEnabled(not busy)
        self.restore_btn.setEnabled(not busy and bool((self.state.found or {}).get("dateien")))

    def start(self):
        folders = self._checked_locations()
        if not folders:
            QMessageBox.information(self, "CC-Suche", "Bitte mindestens einen Suchort auswählen.")
            return
        state, cfg = self.state, self.state.cfg

        def job(progress, should_stop):
            analysis = state.analysis
            if not analysis or not analysis.get("missing"):
                progress("Ermittle zuerst die fehlende CC …")
                analysis = core.analyze(cfg, progress=progress)
            parts = analysis["missing"]["teile"]
            if not parts:
                return analysis, None
            found = core.find(cfg, parts, folders, progress=progress, should_stop=should_stop)
            progress("Schreibe Bericht …")
            core.write_report(cfg, analysis, found=found)
            return analysis, found

        self.state.runner.start(job, on_done=self._done, on_error=self._error)

    def _done(self, result):
        analysis, found = result
        if analysis is not self.state.analysis:
            self.state.set_analysis(analysis)
        if found is None:
            QMessageBox.information(self, "CC-Suche", "Es fehlt keine CC – nichts zu suchen. 🎉")
            return
        self.state.set_found(found)
        self.state.message.emit(f"Suche fertig: {found['gefunden']} von {found['gesucht']} fehlenden Teilen gefunden.")

    def _error(self, message):
        if message != "Abgebrochen.":
            QMessageBox.warning(self, "CC-Suche", message)
        self.state.message.emit(message.splitlines()[0])

    def refresh(self):
        found = self.state.found or {}
        self.model.set_rows(found.get("dateien", []))
        self.table.sortByColumn(1, Qt.DescendingOrder)
        self.unreadable.clear()
        unreadable = found.get("nicht_lesbar", [])
        sims = QTreeWidgetItem(self.unreadable, [f"mit Sims-Bezug ({sum(1 for u in unreadable if u.get('sims'))})"])
        rest = QTreeWidgetItem(self.unreadable, [f"sonstige ({sum(1 for u in unreadable if not u.get('sims'))})"])
        for u in unreadable:
            QTreeWidgetItem(sims if u.get("sims") else rest, [u["pfad"], u["grund"]])
        sims.setExpanded(True)
        sims.setForeground(0, QColor(theme.WARN if sims.childCount() else theme.MUTED))
        if found:
            self.summary.setText(f"{found.get('gefunden', 0)} von {found.get('gesucht', 0)} fehlenden Teilen "
                                 f"gefunden, in {len(found.get('dateien', []))} Datei(en).")
        else:
            self.summary.setText("Noch keine Suche.")
        self.restore_btn.setEnabled(bool(found.get("dateien")) and not self.state.runner.busy)

    def _open_location(self, index):
        item = self.model.rows[self.proxy.mapToSource(index).row()]
        open_path(os.path.dirname(item["pfad"]))

    # -- Zurückholen -------------------------------------------------------------
    def restore(self):
        found = (self.state.found or {}).get("dateien") or []
        if not found:
            return
        exclude = [x.strip() for x in self.exclude.text().replace(";", ",").split(",") if x.strip()]
        target = os.path.join(self.state.cfg["mods_folder"], cc_finder.RESTORE_SUBFOLDER)
        text = (f"{len(found)} Datei(en) werden nach\n{target}\nkopiert (es wird nichts überschrieben)."
                + (f"\nAusgelassen wird alles mit: {', '.join(exclude)}" if exclude else "")
                + ("\n\nVorher wird der Mods-Ordner als ZIP gesichert." if self.backup_first.isChecked() else ""))
        if QMessageBox.question(self, "Zurückholen", text) != QMessageBox.Yes:
            return
        cfg, backup_first = self.state.cfg, self.backup_first.isChecked()

        self._skipped = []
        skipped = self._skipped

        def job(progress, should_stop):
            return core.restore(cfg, found, exclude=exclude, backup_first=backup_first, progress=progress,
                                skipped=skipped)

        self.state.runner.start(job, on_done=self._restored, on_error=self._error)

    def _restored(self, result):
        backup_path, created, failed = result
        msg = f"{len(created)} Datei(en) zurückgeholt."
        if backup_path:
            msg += f"\nBackup: {backup_path}"
        if failed:
            msg += "\n\nNicht geklappt:\n" + "\n".join(f"• {n}: {r}" for n, r in failed[:10])
        skipped = [s for s in getattr(self, "_skipped", []) if "--ohne" not in s[1]]
        if skipped:
            msg += (f"\n\n{len(skipped)} Fund(e) nicht kopiert, damit nichts doppelt im Mods-Ordner landet "
                    "(Teile schon vorhanden oder in einem anderen Fund enthalten).")
        msg += ("\n\nTipp: Danach auf der Übersicht erneut „Analyse starten“ – die Seite „Konflikte“ zeigt dann, "
                "ob sich Zurückgeholtes mit Vorhandenem überschneidet.")
        QMessageBox.information(self, "Zurückholen", msg)
        open_path(os.path.join(self.state.cfg["mods_folder"], cc_finder.RESTORE_SUBFOLDER))

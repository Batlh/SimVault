# Seite: Reparatur – kaputte CC und Spielstände finden und reparieren, was sich sicher reparieren lässt

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QHBoxLayout, QLabel, QMessageBox, QPushButton,
                               QTableView, QTextBrowser, QVBoxLayout, QWidget)

import core
import repair
from ..widgets import DictTableModel, FilterProxy, fit_columns, open_path, page_header


class RepairPage(QWidget):
    def __init__(self, state):
        super().__init__()
        self.state = state
        self.items = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.addWidget(page_header(
            "Reparatur",
            "Prüft CC-Dateien und Spielstände. Reparierbar sind: falsch benannte Archive, einzelne kaputte "
            "Ressourcen in einem Paket und Spielstände, von denen das Spiel noch eine intakte ältere Fassung hat. "
            "Leere oder abgeschnittene Downloads kann niemand reparieren – die müssen neu geladen werden. "
            "Vor jeder Reparatur wird das Original im Backup-Ordner gesichert."))

        top = QHBoxLayout()
        self.quick = QPushButton("Prüfen")
        self.quick.setObjectName("Primary")
        self.quick.clicked.connect(lambda: self.check(False))
        self.deep = QPushButton("Gründlich prüfen")
        self.deep.setToolTip("Entpackt jede einzelne Ressource – findet auch Schäden mitten in einer Datei, dauert länger.")
        self.deep.clicked.connect(lambda: self.check(True))
        self.fix = QPushButton("Reparieren")
        self.fix.clicked.connect(self.repair)
        self.fix.setEnabled(False)
        self.only_broken = QCheckBox("nur beschädigte zeigen")
        self.only_broken.setChecked(True)
        self.only_broken.toggled.connect(self._apply_filter)
        for w in (self.quick, self.deep, self.fix, self.only_broken):
            top.addWidget(w)
        top.addStretch(1)
        lay.addLayout(top)

        self.info = QLabel("Noch nicht geprüft.")
        self.info.setObjectName("Muted")
        self.info.setWordWrap(True)
        lay.addWidget(self.info)

        self.model = DictTableModel([
            ("Typ", "typ"), ("Datei", "datei"), ("Zustand", "zustand"),
            ("Reparierbar", lambda it: "" if it["zustand"] == repair.OK else ("ja" if it["reparierbar"] else "nein")),
            ("Problem", "problem")], color_key="zustand")
        self.proxy = FilterProxy()
        self.proxy.setSourceModel(self.model)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().hide()
        fit_columns(self.table, stretch=4, fit=(0, 2, 3), widths={1: 380})
        self.table.selectionModel().currentRowChanged.connect(self._show)
        self.table.doubleClicked.connect(self._open)
        lay.addWidget(self.table, 3)
        self.detail = QTextBrowser()
        self.detail.setMaximumHeight(120)
        lay.addWidget(self.detail, 1)
        self._apply_filter()

    def set_busy(self, busy):
        self.quick.setEnabled(not busy)
        self.deep.setEnabled(not busy)
        self.fix.setEnabled(not busy and any(it["reparierbar"] for it in self.items))

    def _apply_filter(self):
        self.proxy.set_field_filter("zustand", repair.BROKEN if self.only_broken.isChecked() else None)

    def check(self, deep):
        cfg = self.state.cfg
        self.state.runner.start(lambda progress, should_stop: core.check_health(cfg, deep, progress, should_stop),
                                on_done=lambda items: self._checked(items, deep),
                                on_error=lambda m: QMessageBox.warning(self, "Prüfung", m))

    def _checked(self, items, deep):
        self.items = items
        self.model.set_rows(items)
        broken = [it for it in items if it["zustand"] == repair.BROKEN]
        fixable = sum(1 for it in broken if it["reparierbar"])
        saves = sum(1 for it in items if it["typ"] == "Spielstand")
        self.info.setText(f"{len(items) - saves} CC-Dateien und {saves} Spielstände "
                          f"{'gründlich ' if deep else ''}geprüft: {len(broken)} beschädigt, "
                          f"davon {fixable} reparierbar."
                          + ("" if deep else " „Gründlich prüfen“ findet auch Schäden mitten in einer Datei."))
        self.fix.setText(f"Reparieren ({fixable})")
        self.fix.setEnabled(fixable > 0)
        self.detail.clear()
        self.state.message.emit("Prüfung fertig.")

    def _row(self, index):
        return self.model.rows[self.proxy.mapToSource(index).row()] if index.isValid() else None

    def _show(self, current, _previous=None):
        it = self._row(current)
        if not it:
            return
        import html
        if it["zustand"] == repair.OK:
            self.detail.setHtml(f"<p><b>{html.escape(it['datei'])}</b> ist in Ordnung.</p>")
        else:
            self.detail.setHtml(f"<p><b>{html.escape(it['datei'])}</b></p><p>{html.escape(it['problem'])}</p>"
                                f"<p><b>Lösung:</b> {html.escape(it['loesung'])}</p>")

    def _open(self, index):
        it = self._row(index)
        if it:
            import os
            open_path(os.path.dirname(it["pfad"]))

    def repair(self):
        todo = [it for it in self.items if it["zustand"] == repair.BROKEN and it["reparierbar"]]
        if not todo:
            return
        saves = [it for it in todo if it["typ"] == "Spielstand"]
        text = f"{len(todo)} Datei(en) reparieren? Die Originale werden vorher im Backup-Ordner gesichert."
        if saves:
            text += (f"\n\nAchtung: {len(saves)} Spielstand/Spielstände werden durch eine ältere Fassung ersetzt – "
                     "der Fortschritt seit dieser Fassung geht verloren.")
        if QMessageBox.question(self, "Reparieren", text) != QMessageBox.Yes:
            return
        cfg, items = self.state.cfg, self.items
        self.state.runner.start(lambda progress, should_stop: core.repair_items(cfg, items, progress),
                                on_done=self._repaired,
                                on_error=lambda m: QMessageBox.warning(self, "Reparatur", m))

    def _repaired(self, result):
        backup_dir, results = result
        ok = sum(1 for _n, good, _m in results if good)
        lines = "\n".join(f"{'✔' if good else '✘'} {name} – {message}" for name, good, message in results[:15])
        QMessageBox.information(self, "Reparatur", f"{ok} von {len(results)} repariert.\n\n{lines}\n\n"
                                                   f"Originale gesichert in:\n{backup_dir}")
        QTimer.singleShot(0, lambda: self.check(False))     # neu prüfen, sobald die Reparatur-Aufgabe beendet ist

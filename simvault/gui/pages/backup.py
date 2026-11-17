# Seite: Backup – Mods oder Spielstände sichern, Backups wiederherstellen, alte aufräumen

import os

from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout,
                               QMessageBox, QPushButton, QSpinBox, QTableView, QVBoxLayout, QWidget)

from simvault.app import core
from ..widgets import DictTableModel, fit_columns, open_path, page_header


class BackupPage(QWidget):
    def __init__(self, state):
        super().__init__()
        self.state = state
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.addWidget(page_header("Backup", "Voll-Backup = alles als ZIP. Delta = nur neue/geänderte Dateien seit "
                                            "dem letzten Delta-Backup. Beim Wiederherstellen eines Deltas spielt "
                                            "SimVault automatisch das letzte Voll-Backup und alle Deltas danach ein."))
        row = QHBoxLayout()
        box = QGroupBox("Neues Backup")
        form = QFormLayout(box)
        self.target = QComboBox()
        self.target.addItem("Mods-Ordner", "mods")
        self.target.addItem("Spielstände", "saves")
        self.mode = QComboBox()
        self.mode.addItem("Voll-Backup (ZIP)", "full")
        self.mode.addItem("Delta (nur Änderungen)", "delta")
        self.run = QPushButton("Backup erstellen")
        self.run.setObjectName("Primary")
        self.run.clicked.connect(self.start)
        form.addRow("Was:", self.target)
        form.addRow("Art:", self.mode)
        form.addRow("", self.run)
        row.addWidget(box, 1)

        auto = QGroupBox("Alte Backups aufräumen")
        af = QFormLayout(auto)
        self.auto = QCheckBox("nach jedem neuen Backup automatisch")
        self.keep = QSpinBox()
        self.keep.setRange(0, 999)
        self.keep.setSpecialValueText("egal")
        self.keep.setSuffix(" Voll-Backups je Ordner behalten")
        self.days = QSpinBox()
        self.days.setRange(0, 3650)
        self.days.setSpecialValueText("egal")
        self.days.setPrefix("älter als ")
        self.days.setSuffix(" Tage löschen")
        for w in (self.auto, self.keep, self.days):
            (w.toggled if w is self.auto else w.valueChanged).connect(self._save_rules)
        self.clean = QPushButton("Jetzt aufräumen …")
        self.clean.clicked.connect(self.cleanup)
        af.addRow(self.auto)
        af.addRow(self.keep)
        af.addRow(self.days)
        af.addRow(self.clean)
        row.addWidget(auto, 1)
        lay.addLayout(row)

        existing = QGroupBox("Vorhandene Backups")
        el = QVBoxLayout(existing)
        self.model = DictTableModel([
            ("Datum", lambda b: b["zeit"].strftime("%d.%m.%Y %H:%M")), ("Art", "art_name"), ("Ordner", "quelle"),
            ("Größe", lambda b: f"{b['groesse'] / 1048576:.1f} MB"), ("Name", "name")])
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().hide()
        fit_columns(self.table, stretch=4, fit=(0, 1, 2, 3))
        self.table.doubleClicked.connect(lambda _i: self._open_selected())
        btns = QHBoxLayout()
        self.restore_btn = QPushButton("Wiederherstellen …")
        self.restore_btn.setObjectName("Primary")
        self.restore_btn.clicked.connect(self.restore)
        self.only_missing = QCheckBox("nur Fehlendes ergänzen")
        self.only_missing.setToolTip("Vorhandene Dateien bleiben, wie sie sind – es kommt nur zurück, was fehlt.")
        self.exact = QCheckBox("genau auf Backup-Stand bringen")
        self.exact.setToolTip("Dateien, die das Backup nicht kennt, werden in den Backup-Ordner beiseitegelegt "
                              "(nicht gelöscht).")
        open_btn = QPushButton("Backup-Ordner öffnen")
        open_btn.clicked.connect(lambda: open_path(self._folder()))
        for w in (self.restore_btn, self.only_missing, self.exact):
            btns.addWidget(w)
        btns.addStretch(1)
        btns.addWidget(open_btn)
        el.addWidget(self.table)
        el.addLayout(btns)
        lay.addWidget(existing, 1)
        state.config_changed.connect(self.refresh)
        self.refresh()

    def _folder(self):
        folder = self.state.cfg["backup_folder"]
        os.makedirs(folder, exist_ok=True)
        return folder

    def set_busy(self, busy):
        for w in (self.run, self.restore_btn, self.clean):
            w.setEnabled(not busy)

    def _selected(self):
        index = self.table.currentIndex()
        return self.model.rows[index.row()] if index.isValid() else None

    def _open_selected(self):
        backup = self._selected()
        if backup:
            open_path(backup["pfad"] if os.path.isdir(backup["pfad"]) else os.path.dirname(backup["pfad"]))

    # -- Sichern -----------------------------------------------------------------
    def start(self):
        cfg, target, mode = self.state.cfg, self.target.currentData(), self.mode.currentData()
        self.state.runner.start(lambda progress, should_stop: core.backup(cfg, target, mode),
                                on_done=self._done, on_error=lambda m: QMessageBox.warning(self, "Backup", m))

    def _done(self, path):
        self.refresh()
        self.state.message.emit(f"Backup erstellt: {path}")

    # -- Wiederherstellen --------------------------------------------------------
    def restore(self):
        backup = self._selected()
        if not backup:
            QMessageBox.information(self, "Wiederherstellen", "Bitte zuerst ein Backup in der Liste auswählen.")
            return
        if backup["art"] == "beiseite":
            QMessageBox.information(self, "Wiederherstellen", "Das sind beiseitegelegte Dateien einer früheren "
                                                              "Wiederherstellung – bei Bedarf von Hand zurückschieben.")
            self._open_selected()
            return
        only_missing, exact = self.only_missing.isChecked(), self.exact.isChecked()
        text = f"{backup['art_name']} vom {backup['zeit']:%d.%m.%Y %H:%M} zurückspielen?\n\n"
        if backup["art"] == "delta":
            text += "Eingespielt werden das letzte Voll-Backup davor und alle Deltas bis zu diesem.\n"
        text += ("Vorhandene Dateien bleiben unverändert, nur Fehlendes kommt zurück." if only_missing
                 else "Vorhandene Dateien werden durch den Stand aus dem Backup ersetzt.")
        if exact and backup["art"] in ("backup", "delta"):
            text += "\nDateien, die das Backup nicht kennt, werden beiseitegelegt (nicht gelöscht)."
        text += "\n\nDas Spiel sollte dabei geschlossen sein."
        if QMessageBox.question(self, "Wiederherstellen", text) != QMessageBox.Yes:
            return
        cfg, name = self.state.cfg, backup["name"]
        self.state.runner.start(
            lambda progress, should_stop: core.restore_backup(cfg, name, not only_missing, exact, progress),
            on_done=self._restored, on_error=lambda m: QMessageBox.warning(self, "Wiederherstellen", m))

    def _restored(self, out):
        text = f"{out['wiederhergestellt']} Datei(en) wiederhergestellt nach:\n" + "\n".join(out["ziele"])
        if out["uebersprungen"]:
            text += f"\n\n{out['uebersprungen']} vorhandene Datei(en) nicht angefasst."
        if out["beiseite"]:
            text += f"\n\n{out['verschoben']} Datei(en) beiseitegelegt in:\n{out['beiseite']}"
        QMessageBox.information(self, "Wiederherstellen", text)
        self.refresh()
        self.state.message.emit("Backup wiederhergestellt – Analyse neu starten, um den Stand zu aktualisieren.")

    # -- Aufräumen ---------------------------------------------------------------
    def _save_rules(self, *_):
        if getattr(self, "_loading", False):
            return
        raw = dict(self.state.raw)
        raw["backup_cleanup"] = {"enabled": self.auto.isChecked(), "keep_last": self.keep.value(),
                                 "max_age_days": self.days.value()}
        self._loading = True          # save_config lädt die Einstellungen neu -> refresh nicht in sich selbst rufen
        try:
            self.state.save_config(raw)
        finally:
            self._loading = False

    def cleanup(self):
        doomed = core.cleanup_backups(self.state.cfg, dry_run=True)
        if not doomed:
            QMessageBox.information(self, "Aufräumen", "Nach den eingestellten Regeln ist nichts zu löschen.")
            return
        size = sum(b["groesse"] for b in doomed) / 1048576
        lines = "\n".join(f"• {b['zeit']:%d.%m.%Y}  {b['art_name']}  {b['name']}" for b in doomed[:12])
        more = f"\n… und {len(doomed) - 12} weitere" if len(doomed) > 12 else ""
        if QMessageBox.question(self, "Aufräumen", f"{len(doomed)} Backup(s) endgültig löschen ({size:.1f} MB)?\n\n"
                                                   f"{lines}{more}\n\nDas neueste Voll-Backup jedes Ordners bleibt "
                                                   "in jedem Fall.") != QMessageBox.Yes:
            return
        removed, freed = core.cleanup_backups(self.state.cfg)
        self.refresh()
        self.state.message.emit(f"{len(removed)} Backup(s) gelöscht, {freed / 1048576:.1f} MB frei.")

    def refresh(self):
        if not getattr(self, "_loading", False):
            rules = self.state.cfg.get("backup_cleanup") or {}
            self._loading = True
            self.auto.setChecked(bool(rules.get("enabled")))
            self.keep.setValue(int(rules.get("keep_last", 10)))
            self.days.setValue(int(rules.get("max_age_days", 30)))
            self._loading = False
        self.model.set_rows(core.list_backups(self.state.cfg))

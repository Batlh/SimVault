# Seite: Backup – Mods oder Spielstände sichern, vorhandene Backups anzeigen

import os
from datetime import datetime

from PySide6.QtWidgets import (QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QListWidget, QMessageBox,
                               QPushButton, QVBoxLayout, QWidget)

import core
from ..widgets import open_path, page_header


class BackupPage(QWidget):
    def __init__(self, state):
        super().__init__()
        self.state = state
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.addWidget(page_header("Backup", "Voll-Backup = alles als ZIP. Delta = nur neue/geänderte Dateien seit "
                                            "dem letzten Delta-Backup (zum Wiederherstellen: letztes Voll-Backup "
                                            "plus alle Deltas danach)."))
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
        lay.addWidget(box)

        existing = QGroupBox("Vorhandene Backups")
        el = QVBoxLayout(existing)
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda it: open_path(os.path.join(self.state.cfg["backup_folder"],
                                                                              it.data(256))))
        btns = QHBoxLayout()
        open_btn = QPushButton("Backup-Ordner öffnen")
        open_btn.clicked.connect(lambda: open_path(self._folder()))
        btns.addWidget(open_btn)
        btns.addStretch(1)
        el.addWidget(self.list)
        el.addLayout(btns)
        lay.addWidget(existing, 1)
        state.config_changed.connect(self.refresh)
        self.refresh()

    def _folder(self):
        folder = self.state.cfg["backup_folder"]
        os.makedirs(folder, exist_ok=True)
        return folder

    def set_busy(self, busy):
        self.run.setEnabled(not busy)

    def start(self):
        cfg, target, mode = self.state.cfg, self.target.currentData(), self.mode.currentData()
        self.state.runner.start(lambda progress, should_stop: core.backup(cfg, target, mode),
                                on_done=self._done, on_error=lambda m: QMessageBox.warning(self, "Backup", m))

    def _done(self, path):
        self.refresh()
        self.state.message.emit(f"Backup erstellt: {path}")

    def refresh(self):
        self.list.clear()
        folder = self.state.cfg.get("backup_folder")
        if not folder or not os.path.isdir(folder):
            return
        for name in sorted(os.listdir(folder), reverse=True):
            path = os.path.join(folder, name)
            if name.endswith("_hashes.json"):
                continue
            size = os.path.getsize(path) if os.path.isfile(path) else 0
            when = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%d.%m.%Y %H:%M")
            label = f"{name}    ({when}{', %.1f MB' % (size / 1048576) if size else ''})"
            self.list.addItem(label)
            self.list.item(self.list.count() - 1).setData(256, name)

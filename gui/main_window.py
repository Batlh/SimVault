# Modul: gui/main_window.py – Hauptfenster: Seitenleiste links, Seiten rechts, Statusleiste unten

from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
                               QProgressBar, QPushButton, QStackedWidget, QVBoxLayout, QWidget)

from .state import AppState
from .pages.overview import OverviewPage
from .pages.mods import ModsPage
from .pages.missing import MissingPage
from .pages.finder import FinderPage
from .pages.backup import BackupPage
from .pages.sources import SourcesPage
from .pages.settings import SettingsPage

VERSION = "0.5"


class MainWindow(QMainWindow):
    def __init__(self, config_path=None):
        super().__init__()
        self.setWindowTitle("SimVault – Sims 4 CC-Verwaltung")
        self.resize(1280, 820)
        self.state = AppState(config_path)

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        side = QWidget()
        side.setObjectName("Sidebar")
        side.setFixedWidth(210)
        side_lay = QVBoxLayout(side)
        side_lay.setContentsMargins(0, 0, 0, 8)
        title = QLabel("SimVault")
        title.setObjectName("AppTitle")
        side_lay.addWidget(title)
        self.nav = QListWidget()
        self.nav.setObjectName("Sidebar")
        self.nav.setIconSize(QSize(18, 18))
        side_lay.addWidget(self.nav, 1)
        version = QLabel(f"Version {VERSION}")
        version.setObjectName("Muted")
        version.setContentsMargins(16, 0, 0, 0)
        side_lay.addWidget(version)
        root.addWidget(side)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self.pages = [
            ("Übersicht", OverviewPage(self.state)),
            ("Mods", ModsPage(self.state)),
            ("Fehlende CC", MissingPage(self.state)),
            ("CC-Suche", FinderPage(self.state)),
            ("Backup", BackupPage(self.state)),
            ("Quellen", SourcesPage(self.state)),
            ("Einstellungen", SettingsPage(self.state)),
        ]
        for name, page in self.pages:
            self.nav.addItem(QListWidgetItem(name))
            self.stack.addWidget(page)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)
        for _name, page in self.pages:
            if hasattr(page, "navigate"):
                page.navigate.connect(self.go_to)

        # Statusleiste: Meldung, Fortschrittsbalken, Abbrechen
        bar = self.statusBar()
        self.status_label = QLabel("Bereit.")
        self.busy = QProgressBar()
        self.busy.setRange(0, 0)
        self.busy.setFixedWidth(160)
        self.busy.hide()
        self.cancel = QPushButton("Abbrechen")
        self.cancel.hide()
        self.cancel.clicked.connect(self.state.runner.stop)
        bar.addWidget(self.status_label, 1)
        bar.addPermanentWidget(self.busy)
        bar.addPermanentWidget(self.cancel)
        self.state.runner.progress.connect(self.status_label.setText)
        self.state.runner.busy_changed.connect(self._busy)
        self.state.message.connect(self.status_label.setText)

        if not self.state.cfg.get("sims_folder"):
            self.go_to("Einstellungen")
            QMessageBox.information(self, "Willkommen bei SimVault",
                                    "Der Sims-4-Ordner wurde nicht automatisch gefunden.\n"
                                    "Bitte unter „Einstellungen“ festlegen.")

    def go_to(self, name):
        for i, (page_name, _page) in enumerate(self.pages):
            if page_name == name:
                self.nav.setCurrentRow(i)

    def _busy(self, busy):
        self.busy.setVisible(busy)
        self.cancel.setVisible(busy)
        for _name, page in self.pages:
            if hasattr(page, "set_busy"):
                page.set_busy(busy)
        if not busy and self.status_label.text().startswith(("Mods:", "Spielstand", "Fehlende CC", "durchsuche")):
            self.status_label.setText("Fertig.")

    def closeEvent(self, event):
        if self.state.runner.busy:
            if QMessageBox.question(self, "SimVault", "Es läuft noch eine Aufgabe. Trotzdem beenden?") \
                    != QMessageBox.Yes:
                event.ignore()
                return
            self.state.runner.stop()
        event.accept()

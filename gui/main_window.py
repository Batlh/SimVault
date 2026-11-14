# Modul: gui/main_window.py – Hauptfenster: Seitenleiste links, Seiten rechts, Statusleiste unten

import os

from PySide6.QtCore import QSize, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
                               QProgressBar, QPushButton, QStackedWidget, QVBoxLayout, QWidget)

from .state import AppState
from .pages.overview import OverviewPage
from .pages.mods import ModsPage
from .pages.missing import MissingPage
from .pages.finder import FinderPage
from .pages.conflicts import ConflictsPage
from .pages.web import WebPage
from .pages.repair import RepairPage
from .pages.backup import BackupPage
from .pages.sources import SourcesPage
from .pages.settings import SettingsPage, choose_game_folder

from version import __version__ as VERSION


class MainWindow(QMainWindow):
    update_checked = Signal(object)          # Ergebnis der Update-Prüfung aus dem Hintergrund

    def __init__(self, config_path=None, first_run=False):
        super().__init__()
        self.resize(1280, 820)
        self.state = AppState(config_path)
        import i18n
        i18n.set_language(self.state.cfg.get("ui_language", "auto"))
        from PySide6.QtWidgets import QApplication
        self._i18n_filter = i18n.install(QApplication.instance())
        self._update_info = None

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        side = QWidget()
        side.setObjectName("Sidebar")
        side.setFixedWidth(210)
        side_lay = QVBoxLayout(side)
        side_lay.setContentsMargins(0, 0, 0, 8)
        self.logo = QLabel()
        self.logo.setContentsMargins(16, 14, 0, 0)
        self.logo.hide()
        side_lay.addWidget(self.logo)
        self.title = QLabel("SimVault")
        self.title.setObjectName("AppTitle")
        side_lay.addWidget(self.title)
        self.nav = QListWidget()
        self.nav.setObjectName("Sidebar")
        self.nav.setIconSize(QSize(18, 18))
        side_lay.addWidget(self.nav, 1)
        self.update_btn = QPushButton("Update verfügbar")
        self.update_btn.setObjectName("Primary")
        self.update_btn.hide()
        self.update_btn.clicked.connect(self.show_update)
        side_lay.addWidget(self.update_btn)
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
            ("Websuche", WebPage(self.state)),
            ("Konflikte", ConflictsPage(self.state)),
            ("Reparatur", RepairPage(self.state)),
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
            if hasattr(page, "check_update"):
                page.check_update.connect(lambda: self.check_update(manual=True))

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
        self.state.runner.progress.connect(self._status)
        self.state.runner.busy_changed.connect(self._busy)
        self.state.message.connect(self._status)
        # nachträglich gesetzte Texte (Zähler, Hinweise) ebenfalls übersetzen
        for signal in (self.nav.currentRowChanged, self.state.analysis_changed, self.state.found_changed,
                       self.state.config_changed, self.state.runner.busy_changed):
            signal.connect(lambda *_a: QTimer.singleShot(0, self._retranslate))

        for signal in (self.state.web_search, self.state.open_in_browser, self.state.login_requested):
            signal.connect(lambda *_a: self.go_to("Websuche"))
        self.state.config_changed.connect(self._apply_branding)
        self._apply_branding()
        QTimer.singleShot(0, self._retranslate)
        self.update_checked.connect(self._update_checked)
        if first_run and (self.state.cfg.get("updates") or {}).get("check_on_start", True):
            QTimer.singleShot(1500, self.check_update)

        if not self.state.cfg.get("sims_folder"):
            self.go_to("Einstellungen")
            QMessageBox.information(self, "Willkommen bei SimVault",
                                    "Der Sims-4-Ordner wurde nicht automatisch gefunden.\n"
                                    "Bitte unter „Einstellungen“ festlegen.")
        elif first_run and not self.state.raw.get("game_folder") and not self.state.raw.get("game_folder_asked"):
            QTimer.singleShot(600, self._suggest_game_folder)

    def _suggest_game_folder(self):
        """Beim ersten Start: Sims-4-Installation suchen und zur Auswahl vorschlagen."""
        import core
        self.status_label.setText("Suche die Sims-4-Installation …")
        self.state.runner.start(lambda progress, should_stop: core.find_game_folders(True, should_stop),
                                on_done=self._game_folder_found)

    def _game_folder_found(self, found):
        raw = dict(self.state.raw)
        raw["game_folder_asked"] = True
        if found:
            choice = choose_game_folder(self, found)
            if choice:
                raw["game_folder"] = choice
                self.status_label.setText(f"Spielordner: {choice}")
        else:
            self.status_label.setText("Sims-4-Installation nicht gefunden – unter „Einstellungen“ festlegen.")
        self.state.save_config(raw)

    # -- Custom Branding: eigener Programmname und eigenes Logo ---------------------
    def _apply_branding(self):
        branding = self.state.cfg.get("branding") or {}
        name = branding.get("app_name") or "SimVault"
        self.title.setText(name)
        self.setWindowTitle(f"{name} – Sims 4 CC-Verwaltung")
        logo = branding.get("logo_path")
        pixmap = QPixmap(logo) if logo and os.path.isfile(logo) else QPixmap()
        if pixmap.isNull():
            self.logo.hide()
        else:
            self.logo.setPixmap(pixmap.scaledToHeight(48))
            self.logo.show()

    # -- Auto-Updater ---------------------------------------------------------------
    def check_update(self, manual=False):
        """Fragt im Hintergrund auf GitHub nach einer neueren Version (blockiert das Fenster nicht)."""
        import threading
        import core

        def work():
            try:
                info = core.check_update()
            except Exception as e:           # kein Internet o. Ä.: beim Start still, bei Klick melden
                info = {"fehler": str(e)}
            info["manuell"] = manual
            self.update_checked.emit(info)

        threading.Thread(target=work, daemon=True).start()

    def _update_checked(self, info):
        if info.get("fehler"):
            if info["manuell"]:
                QMessageBox.warning(self, "Update", f"GitHub ist gerade nicht erreichbar:\n{info['fehler']}")
            return
        if info["neuer"]:
            self._update_info = info
            self.update_btn.setText(f"Update auf {info['neueste']}")
            self.update_btn.show()
            if info["manuell"]:
                self.show_update()
            else:
                self.status_label.setText(f"Version {info['neueste']} ist verfügbar – links unten auf „Update“ klicken.")
        elif info["manuell"]:
            QMessageBox.information(self, "Update", f"SimVault ist aktuell (Version {info['aktuell']}).")

    def show_update(self):
        import updater
        from .widgets import open_url
        info = self._update_info
        if not info:
            return
        box = QMessageBox(self)
        box.setWindowTitle("Update verfügbar")
        box.setText(f"Version {info['neueste']} ist da (installiert: {info['aktuell']}).")
        box.setInformativeText("Was sich geändert hat, steht unter „Details“. Einstellungen, Berichte, Backups "
                               "und eigene Erweiterungen bleiben erhalten.")
        box.setDetailedText(info["notizen"] or "Keine Beschreibung.")
        install = box.addButton("Jetzt aktualisieren" if updater.can_self_update() else "Herunterladen",
                                QMessageBox.AcceptRole)
        page = box.addButton("Release-Seite öffnen", QMessageBox.ActionRole)
        box.addButton("Später", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is page:
            open_url(info["url"])
        elif box.clickedButton() is install:
            import core
            self.state.runner.start(lambda progress, should_stop: core.download_update(info, progress, should_stop),
                                    on_done=self._update_downloaded,
                                    on_error=lambda m: QMessageBox.warning(self, "Update", m))

    def _update_downloaded(self, zip_path):
        import core
        from .widgets import open_path
        if not zip_path:
            return
        try:
            swapping = core.install_update(zip_path)
        except OSError as e:
            QMessageBox.warning(self, "Update", f"Automatisch ging es nicht ({e}).\nDas ZIP liegt hier:\n{zip_path}")
            swapping = False
        if swapping:
            QMessageBox.information(self, "Update", "SimVault wird jetzt beendet, aktualisiert und neu gestartet.")
            QTimer.singleShot(0, self._quit_for_update)
        else:
            QMessageBox.information(self, "Update", "Das Update wurde heruntergeladen:\n" + zip_path +
                                    "\n\nSimVault beenden, das ZIP entpacken und den Inhalt über den alten "
                                    "Programmordner kopieren.")
            open_path(os.path.dirname(zip_path))

    def _quit_for_update(self):
        from PySide6.QtWidgets import QApplication
        self.state.runner.stop()
        QApplication.instance().quit()

    def go_to(self, name):
        for i, (page_name, _page) in enumerate(self.pages):
            if page_name == name:
                self.nav.setCurrentRow(i)

    def _status(self, text):
        import i18n
        self.status_label.setText(i18n.tr(text))

    def _retranslate(self):
        import i18n
        i18n.translate_widget(self)
        if i18n.language() != "de":
            self.setWindowTitle(self.windowTitle().replace("Sims 4 CC-Verwaltung", "Sims 4 CC manager"))

    def _busy(self, busy):
        self.busy.setVisible(busy)
        self.cancel.setVisible(busy)
        for _name, page in self.pages:
            if hasattr(page, "set_busy"):
                page.set_busy(busy)
        if not busy and self.status_label.text().startswith(("Mods:", "Spielstand", "Fehlende CC", "durchsuche", "Konflikte", "Prüfe", "Repariere")):
            self.status_label.setText("Fertig.")

    def closeEvent(self, event):
        if self.state.runner.busy:
            if QMessageBox.question(self, "SimVault", "Es läuft noch eine Aufgabe. Trotzdem beenden?") \
                    != QMessageBox.Yes:
                event.ignore()
                return
            self.state.runner.stop()
        event.accept()

# Seite: Einstellungen – Ordner, Entpacker, Suchoptionen (gespeichert in config.json)

import os

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QMessageBox, QPushButton, QSpinBox, QVBoxLayout, QWidget)

import core
import archive_tools
import game_locator
from ..widgets import PathEdit, open_path, page_header


class SettingsPage(QWidget):
    check_update = Signal()          # „Jetzt nach Updates suchen“ – das Hauptfenster übernimmt

    def __init__(self, state):
        super().__init__()
        self.state = state
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.addWidget(page_header("Einstellungen"))

        folders = QGroupBox("Ordner")
        f = QFormLayout(folders)
        self.sims = PathEdit(placeholder="z. B. Dokumente\\Electronic Arts\\Die Sims 4")
        self.game = PathEdit(placeholder="optional – Spiel-Installation für sichere Fehlend-Erkennung")
        self.backup = PathEdit()
        self.reports = PathEdit()
        self.temp = PathEdit(placeholder="leer = System-Temp (z. B. auf D: legen, wenn C: knapp ist)")
        f.addRow("Sims-4-Ordner:", self.sims)
        game_row = QHBoxLayout()
        self.find_game = QPushButton("Automatisch suchen")
        self.find_game.setToolTip("Sucht die Sims-4-Installation: EA App/Origin, Steam, Epic und alle Laufwerke.")
        self.find_game.clicked.connect(self.search_game)
        game_row.addWidget(self.game, 1)
        game_row.addWidget(self.find_game)
        f.addRow("Spielordner:", game_row)
        f.addRow("Backups:", self.backup)
        f.addRow("Berichte:", self.reports)
        f.addRow("Temp-Ordner:", self.temp)
        lay.addWidget(folders)

        search = QGroupBox("CC-Suche")
        s = QFormLayout(search)
        ex_row = QHBoxLayout()
        self.extractor = QComboBox()
        self.extractor_path = PathEdit(folder=False, placeholder="Pfad zu 7z.exe, UnRAR.exe oder tar.exe")
        ex_row.addWidget(self.extractor)
        ex_row.addWidget(self.extractor_path, 1)
        self.extractor.currentIndexChanged.connect(self._extractor_changed)
        self.hint = QLabel()
        self.hint.setObjectName("Muted")
        self.hint.setWordWrap(True)
        self.drives = QCheckBox("weitere Laufwerke (D:, E:, USB …) mit durchsuchen")
        self.max_mb = QSpinBox()
        self.max_mb.setRange(100, 100000)
        self.max_mb.setSuffix(" MB")
        s.addRow("Entpacker für RAR/7z:", ex_row)
        s.addRow("", self.hint)
        s.addRow("", self.drives)
        s.addRow("Archive größer als … überspringen:", self.max_mb)
        lay.addWidget(search)

        program = QGroupBox("Programm")
        pf = QFormLayout(program)
        up_row = QHBoxLayout()
        self.update_on_start = QCheckBox("beim Start nach einer neuen Version suchen")
        update_now = QPushButton("Jetzt nach Updates suchen")
        update_now.clicked.connect(self.check_update.emit)
        up_row.addWidget(self.update_on_start, 1)
        up_row.addWidget(update_now)
        self.app_name = QLineEdit()
        self.app_name.setPlaceholderText("SimVault")
        self.logo = PathEdit(folder=False, placeholder="optional – eigenes Logo (PNG/JPG) für Fenster und Berichte")
        pf.addRow("Updates:", up_row)
        import i18n
        self.language = QComboBox()
        self.language.addItem("Automatisch (Windows-Sprache)", "auto")
        for code, label in i18n.LANGUAGES.items():
            self.language.addItem(label, code)
        lang_note = QLabel("Die Sprache wechselt nach einem Neustart von SimVault.")
        lang_note.setObjectName("Muted")
        lang_row = QHBoxLayout()
        lang_row.addWidget(self.language)
        lang_row.addWidget(lang_note, 1)
        pf.addRow("Sprache:", lang_row)
        pf.addRow("Programmname:", self.app_name)
        pf.addRow("Logo:", self.logo)
        lay.addWidget(program)

        bottom = QHBoxLayout()
        save = QPushButton("Speichern")
        save.setObjectName("Primary")
        save.clicked.connect(self.save)
        self.cfg_label = QLabel()
        self.cfg_label.setObjectName("Muted")
        open_cfg = QPushButton("Einstellungsdatei öffnen")
        open_cfg.clicked.connect(lambda: open_path(os.path.dirname(self.state.config_path)))
        bottom.addWidget(save)
        bottom.addWidget(open_cfg)
        bottom.addWidget(self.cfg_label, 1)
        lay.addLayout(bottom)
        lay.addStretch(1)

        state.config_changed.connect(self.load)
        self.load()

    def load(self):
        raw, cfg = self.state.raw, self.state.cfg
        self.sims.setText(raw.get("sims_folder") or cfg.get("sims_folder"))
        self.game.setText(raw.get("game_folder") or cfg.get("game_folder"))
        self.backup.setText(cfg.get("backup_folder"))
        self.reports.setText(cfg.get("report_folder"))
        self.temp.setText(raw.get("temp_folder", ""))
        self.drives.setChecked(bool(raw.get("search_drives", True)))
        self.max_mb.setValue(int(raw.get("max_archive_mb", 4096)))
        self.cfg_label.setText(self.state.config_path)
        self.language.setCurrentIndex(max(self.language.findData(raw.get("ui_language", "auto")), 0))
        self.update_on_start.setChecked(bool((raw.get("updates") or {}).get("check_on_start", True)))
        branding = raw.get("branding") or {}
        name = branding.get("app_name", "")
        self.app_name.setText("" if name == "SimVault" else name)
        self.logo.setText(branding.get("logo_path", ""))

        self.tools = archive_tools.find_tools()
        self.extractor.blockSignals(True)
        self.extractor.clear()
        self.extractor.addItem("Automatisch", "")
        for kind, path in self.tools:
            self.extractor.addItem(f"{archive_tools.TOOL_NAMES[kind]}", path)
        self.extractor.addItem("Eigener Pfad …", "custom")
        self.extractor.addItem("Keiner (RAR/7z überspringen)", "none")
        current = raw.get("extractor", "")
        index = self.extractor.findData(current)
        if index < 0 and current:
            index = self.extractor.findData("custom")
            self.extractor_path.setText(current)
        self.extractor.setCurrentIndex(max(index, 0))
        self.extractor.blockSignals(False)
        self._extractor_changed()

    def set_busy(self, busy):
        self.find_game.setEnabled(not busy)

    def search_game(self):
        self.state.runner.start(lambda progress, should_stop: core.find_game_folders(True, should_stop),
                                on_done=self._game_found,
                                on_error=lambda m: QMessageBox.warning(self, "Spielordner", m))

    def _game_found(self, found):
        choice = choose_game_folder(self, found)
        if choice:
            self.game.setText(choice)
            self.state.message.emit("Spielordner übernommen – „Speichern“ nicht vergessen.")

    def _extractor_changed(self):
        data = self.extractor.currentData()
        self.extractor_path.setVisible(data == "custom")
        if not any(k == "7z" for k, _p in self.tools):
            self.hint.setText("Tipp: 7-Zip öffnet RAR und alle 7z-Archive (winget install 7zip.7zip). "
                              "UnRAR kann nur RAR, das Windows-tar viele 7z nicht.")
        else:
            self.hint.setText("")

    def save(self):
        raw = dict(self.state.raw)
        sims = self.sims.text()
        if sims and not os.path.isdir(sims):
            QMessageBox.warning(self, "Einstellungen", f"Den Sims-4-Ordner gibt es nicht:\n{sims}")
            return
        raw["sims_folder"] = sims
        game = self.game.text()
        if game and not game_locator.is_game_folder(game):
            if QMessageBox.question(self, "Einstellungen",
                                    f"In diesem Ordner liegt kein „Data\\Client“ – das ist vermutlich nicht die "
                                    f"Sims-4-Installation:\n{game}\n\nTrotzdem speichern?") != QMessageBox.Yes:
                return
        raw["game_folder"] = game
        raw["game_folder_asked"] = True
        raw["backup_folder"] = self.backup.text() or "./backups"
        raw["report_folder"] = self.reports.text() or "./reports"
        raw["temp_folder"] = self.temp.text()
        raw["updates"] = {"check_on_start": self.update_on_start.isChecked()}
        raw["ui_language"] = self.language.currentData()
        raw["branding"] = dict(raw.get("branding") or {}, app_name=self.app_name.text().strip() or "SimVault",
                               logo_path=self.logo.text())
        raw["search_drives"] = self.drives.isChecked()
        raw["max_archive_mb"] = self.max_mb.value()
        data = self.extractor.currentData()
        raw["extractor"] = self.extractor_path.text() if data == "custom" else data
        self.state.save_config(raw)
        self.state.message.emit("Einstellungen gespeichert.")


def choose_game_folder(parent, found):
    """Zeigt die gefundenen Installationen zur Auswahl. Gibt den gewählten Pfad zurück oder ""."""
    if not found:
        QMessageBox.information(parent, "Spielordner",
                                "Es wurde keine Sims-4-Installation gefunden.\n"
                                "Bitte den Ordner von Hand wählen (der mit „Data“, „Game“, „EP01“ …).")
        return ""
    labels = [game_locator.describe(c) for c in found]
    label, ok = QInputDialog.getItem(parent, "Sims-4-Installation gefunden",
                                     "Diesen Ordner als Spielordner verwenden?\n"
                                     "(macht die Erkennung fehlender CC genau)", labels, 0, False)
    return found[labels.index(label)]["pfad"] if ok and label in labels else ""

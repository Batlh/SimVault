# Modul: simvault/gui/state.py – gemeinsamer Zustand aller Seiten (Einstellungen, letzte Analyse, letzte Suche)

from PySide6.QtCore import QObject, Signal

from simvault.app import core
from .worker import Runner


class AppState(QObject):
    config_changed = Signal()
    analysis_changed = Signal()
    found_changed = Signal()
    message = Signal(str)           # kurze Meldung für die Statusleiste
    web_search = Signal(str)        # im Netz suchen (Seite „Websuche“)
    open_in_browser = Signal(str)   # Adresse im eingebauten Browser öffnen
    login_requested = Signal(object)  # Quelle, bei der man sich anmelden will
    checks_waiting = Signal(list)   # Namen der Seiten, deren Prüfung (Captcha) wartet – leer = keine
    show_checks = Signal()          # wartende Prüfung jetzt zeigen

    def __init__(self, config_path=None):
        super().__init__()
        self.config_path = config_path
        self.raw, self.cfg = core.load(config_path)
        self.config_path = self.cfg["_config_path"]
        self.runner = Runner(self)
        self.analysis = None        # Ergebnis von core.analyze
        self.found = None           # Fundstellen-Dict von core.find
        self.last_report = None
        self._load_last_found()

    def reload_config(self):
        self.raw, self.cfg = core.load(self.config_path)
        self.config_changed.emit()

    def save_config(self, raw):
        core.save(raw, self.config_path)
        self.reload_config()

    def set_analysis(self, analysis):
        self.analysis = analysis
        self.analysis_changed.emit()

    def set_found(self, found):
        self.found = found
        self.found_changed.emit()

    def missing_parts(self):
        if self.analysis and self.analysis.get("missing"):
            return self.analysis["missing"]["teile"]
        return []

    def _load_last_found(self):
        try:
            path, data = core.latest_report(self.cfg, with_found=True)
        except Exception:
            return
        if data:
            self.found = data.get("fundstellen")
            self.last_report = path

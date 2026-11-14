# Seite: Übersicht – Zahlen auf einen Blick, Analyse starten, Bericht öffnen

import os
from collections import Counter
from datetime import datetime

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout,
                               QWidget, QCheckBox)

import core
from .. import theme
from ..widgets import StatCard, open_path, page_header


class OverviewPage(QWidget):
    navigate = Signal(str)

    def __init__(self, state):
        super().__init__()
        self.state = state
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.addWidget(page_header("Übersicht", "Mods-Ordner, Spielstände und Bibliothek auf einen Blick."))

        grid = QGridLayout()
        grid.setSpacing(12)
        self.cards = {
            "mods": StatCard("Mod-Dateien"),
            "genutzt": StatCard("genutzt", color=theme.ACCENT),
            "ungenutzt": StatCard("ungenutzt", color=theme.WARN),
            "fehlend": StatCard("fehlende CC-Teile", color=theme.ERROR),
            "probleme": StatCard("Probleme im Mods-Ordner"),
            "gefunden": StatCard("auf dem PC gefunden", color=theme.ACCENT),
        }
        for i, card in enumerate(self.cards.values()):
            grid.addWidget(card, i // 3, i % 3)
        lay.addLayout(grid)

        opts = QHBoxLayout()
        self.all_saves = QCheckBox("alle Spielstände")
        self.all_saves.setChecked(True)
        self.tray = QCheckBox("Bibliothek einbeziehen")
        self.tray.setChecked(True)
        opts.addWidget(self.all_saves)
        opts.addWidget(self.tray)
        opts.addStretch(1)
        lay.addSpacing(10)
        lay.addLayout(opts)

        buttons = QHBoxLayout()
        self.run = QPushButton("Analyse starten")
        self.run.setObjectName("Primary")
        self.run.clicked.connect(self.start)
        self.report = QPushButton("Bericht öffnen")
        self.report.clicked.connect(self.open_report)
        self.report.setEnabled(False)
        to_missing = QPushButton("Fehlende CC ansehen")
        to_missing.clicked.connect(lambda: self.navigate.emit("Fehlende CC"))
        to_search = QPushButton("CC auf dem PC suchen")
        to_search.clicked.connect(lambda: self.navigate.emit("CC-Suche"))
        to_conflicts = QPushButton("Konflikte ansehen")
        to_conflicts.clicked.connect(lambda: self.navigate.emit("Konflikte"))
        for b in (self.run, self.report, to_missing, to_search, to_conflicts):
            buttons.addWidget(b)
        buttons.addStretch(1)
        lay.addLayout(buttons)

        self.info = QLabel()
        self.info.setObjectName("Muted")
        self.info.setWordWrap(True)
        lay.addWidget(self.info)
        self.issues = QLabel()
        self.issues.setWordWrap(True)
        lay.addWidget(self.issues)
        lay.addStretch(1)

        state.analysis_changed.connect(self.refresh)
        state.found_changed.connect(self.refresh)
        state.config_changed.connect(self.refresh)
        self.refresh()

    def set_busy(self, busy):
        self.run.setEnabled(not busy)

    def start(self):
        cfg = self.state.cfg
        if not cfg.get("mods_folder") or not os.path.isdir(cfg["mods_folder"]):
            QMessageBox.warning(self, "SimVault", "Mods-Ordner nicht gefunden – bitte unter „Einstellungen“ "
                                                  "den Sims-4-Ordner festlegen.")
            return
        all_saves, tray = self.all_saves.isChecked(), self.tray.isChecked()

        def job(progress, should_stop):
            analysis = core.analyze(cfg, all_saves=all_saves, tray=tray, progress=progress)
            progress("Schreibe Bericht …")
            analysis["report_files"] = core.write_report(cfg, analysis)
            return analysis

        self.state.runner.start(job, on_done=self._done, on_error=self._error)

    def _done(self, analysis):
        self.state.last_report = next((f for f in analysis.get("report_files", []) if f.endswith(".html")), None)
        self.state.set_analysis(analysis)
        self.state.message.emit(f"Analyse fertig – {datetime.now():%H:%M}")

    def _error(self, message):
        QMessageBox.warning(self, "Analyse", message)

    def open_report(self):
        if self.state.last_report:
            html = os.path.splitext(self.state.last_report)[0] + ".html"
            open_path(html if os.path.exists(html) else self.state.last_report)

    def refresh(self):
        a = self.state.analysis
        found = self.state.found
        self.report.setEnabled(bool(self.state.last_report))
        if a:
            usage = Counter(r["status"] for r in a["usage"])
            self.cards["mods"].set(len(a["mod_scan"].mods))
            self.cards["genutzt"].set(usage.get("genutzt", 0))
            self.cards["ungenutzt"].set(usage.get("ungenutzt", 0))
            self.cards["fehlend"].set(len(a["missing"]["teile"]) if a.get("missing") else "–")
            conflicts = (a.get("conflicts") or {}).get("konflikte", [])
            issues = [i for i in a["mod_scan"].issues if i.kind != "Konflikt"]
            self.cards["probleme"].set(len(issues) + len(conflicts))
            saves = ", ".join(os.path.basename(s) for s in a["saves"]) or "keine"
            self.info.setText(f"Spielstände: {saves}\n{a.get('missing_info') or ''}")
            lines = [f"• {i.severity} – {i.kind}: {len(i.files)} Datei(en)" for i in issues[:8]]
            if conflicts:
                kinds = Counter(c["art"] for c in conflicts)
                removable = len(a["conflicts"]["entfernbar"])
                lines.append("• Überschneidungen geprüft: " + ", ".join(f"{n}× {k}" for k, n in kinds.items())
                             + (f" – {removable} Datei(en) überflüssig" if removable else ""))
            self.issues.setText("\n".join(lines))
        else:
            for key in ("mods", "genutzt", "ungenutzt", "fehlend", "probleme"):
                self.cards[key].set("–")
            self.info.setText("Noch keine Analyse in dieser Sitzung – „Analyse starten“ liest Mods, "
                              "Spielstände und Bibliothek ein.")
            self.issues.setText("")
        if found:
            self.cards["gefunden"].set(f"{found.get('gefunden', 0)} / {found.get('gesucht', 0)}")
        else:
            self.cards["gefunden"].set("–")

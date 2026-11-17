# Seite: Konflikte – was sich im Mods-Ordner überschneidet, wie schlimm das ist und was zu tun ist

import os
from collections import Counter

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QTableView, QTextBrowser, QVBoxLayout, QWidget)

from simvault.app import core
from ..widgets import DictTableModel, FilterProxy, fit_columns, open_path, page_header

HELP = {
    "Konflikt": "Gleiche CC in unterschiedlichen Fassungen – das Spiel nutzt nur eine. Hier musst du dich entscheiden.",
    "Überschreibung": "Mehrere Mods ersetzen dasselbe Original-Teil des Spiels – nur eine kann gelten.",
    "Doppelt": "Inhalt ist identisch und eine Datei steckt komplett in einer anderen – die kann weg.",
    "Überschneidung": "Gemeinsamer Inhalt ist identisch, jede Datei hat aber noch Eigenes – harmlos.",
}


class ConflictsPage(QWidget):
    def __init__(self, state):
        super().__init__()
        self.state = state
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.addWidget(page_header("Konflikte", "Dieselbe CC in mehreren Dateien: SimVault vergleicht den Inhalt, "
                                               "gleicht mit Spielständen und Bibliothek ab und sagt, was zu tun ist."))
        self.info = QLabel()
        self.info.setObjectName("Muted")
        self.info.setWordWrap(True)
        lay.addWidget(self.info)

        top = QHBoxLayout()
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filtern (Datei, Art …)")
        self.clean = QPushButton("Aufräumen")
        self.clean.setToolTip("Sortiert überflüssige Dateien aus und entfernt veraltete Doppel – nur was sicher geht.")
        self.clean.setObjectName("Primary")
        self.clean.clicked.connect(self.clean_up)
        open_mods = QPushButton("Mods-Ordner öffnen")
        open_mods.clicked.connect(lambda: open_path(self.state.cfg.get("mods_folder")))
        top.addWidget(self.filter, 1)
        top.addWidget(self.clean)
        top.addWidget(open_mods)
        lay.addLayout(top)

        self.model = DictTableModel([
            ("Art", "art"), ("Dateien", "namen"), ("Gemeinsam", "teile"), ("Identisch", "identisch"),
            ("Unterschiedlich", "unterschiedlich"), ("In Benutzung", "genutzt"),
            ("Spielstände", "spielstaende")], color_key="art")
        self.proxy = FilterProxy()
        self.proxy.setSourceModel(self.model)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().hide()
        fit_columns(self.table, stretch=1, fit=(0, 2, 3, 4, 5), widths={6: 200})
        self.table.selectionModel().currentRowChanged.connect(self._show)
        lay.addWidget(self.table, 3)
        self.detail = QTextBrowser()
        self.detail.setMaximumHeight(170)
        lay.addWidget(self.detail, 1)
        self.filter.textChanged.connect(self.proxy.setFilterFixedString)

        state.analysis_changed.connect(self.refresh)
        self.refresh()

    def _result(self):
        return (self.state.analysis or {}).get("conflicts") or {"konflikte": [], "entfernbar": [], "aufloesbar": []}

    def _todo(self):
        result = self._result()
        return len(result["entfernbar"]) + len(result.get("aufloesbar", []))

    def set_busy(self, busy):
        self.clean.setEnabled(not busy and self._todo() > 0)

    def refresh(self):
        result = self._result()
        self.model.set_rows(result["konflikte"])
        self.table.sortByColumn(-1, Qt.AscendingOrder)      # Reihenfolge der Prüfung: das Wichtigste zuerst
        removable = result["entfernbar"]
        solvable = result.get("aufloesbar", [])
        self.clean.setText(f"Aufräumen ({self._todo()})")
        self.clean.setEnabled(self._todo() > 0)
        if not self.state.analysis:
            self.info.setText("Noch keine Analyse – auf der Übersicht „Analyse starten“.")
        elif not result["konflikte"]:
            self.info.setText("Keine Überschneidungen im Mods-Ordner gefunden.")
        else:
            kinds = Counter(c["art"] for c in result["konflikte"])
            size = sum(e["groesse"] for e in removable) / 1048576
            extra = f" · {len(removable)} überflüssige Datei(en), {size:.1f} MB" if removable else ""
            extra += f" · {len(solvable)} Konflikt(e) sicher auflösbar" if solvable else ""
            self.info.setText(" · ".join(f"{n}× {k}" for k, n in kinds.items()) + extra)
        self.detail.setHtml("<p style='color:#8b949e'>Zeile anklicken für die Empfehlung.</p>")
        if result["konflikte"]:
            self.table.selectRow(0)

    def _show(self, current, _previous=None):
        if not current.isValid():
            return
        c = self.model.rows[self.proxy.mapToSource(current).row()]
        import html
        files = "".join(f"<li>{html.escape(f)}{' &nbsp;<b>(überflüssig)</b>' if f in c['entfernbar'] else ''}</li>"
                        for f in c["dateien"])
        where = ", ".join(c["spielstaende"]) or ("nur in der Bibliothek" if c["bibliothek"] else "nirgends")
        self.detail.setHtml(
            f"<p><b>{html.escape(c['art'])}</b> – {html.escape(HELP.get(c['art'], ''))}</p><ul>{files}</ul>"
            f"<p><b>Empfehlung:</b> {html.escape(c['empfehlung'])}</p>"
            f"<p>In Benutzung: {c['genutzt']} von {c['teile']} Teilen ({html.escape(where)})</p>")

    def clean_up(self):
        result = self._result()
        files = [e["datei"] for e in result["entfernbar"]]
        solvable = result.get("aufloesbar", [])
        if not files and not solvable:
            return
        lines = [f"• {f} – steckt identisch in anderen Dateien, wird aussortiert" for f in files[:8]]
        for sol in solvable[:8]:
            what = ("wird aussortiert" if sol["aktion"] == "aussortieren"
                    else f"{sol['ressourcen']} veraltete Doppel werden entfernt, der Rest bleibt")
            lines.append(f"• {sol['verlierer']} – aktueller in {os.path.basename(sol['behalten'])}: {what}")
        answer = QMessageBox.question(
            self, "Aufräumen",
            "Das lässt sich sicher auflösen:\n\n" + "\n".join(lines) + "\n\n"
            "Aussortierte Dateien werden nach „SimVault_aussortiert“ verschoben (nicht gelöscht), von geänderten "
            "Paketen kommt das Original in den Backup-Ordner. Fortfahren?")
        if answer != QMessageBox.Yes:
            return
        out = core.clean_conflicts(self.state.cfg, result)
        text = []
        if out["verschoben"]:
            text.append(f"{len(out['verschoben'])} Datei(en) verschoben nach:\n{out['ordner']}")
        if out["bereinigt"]:
            text.append("\n".join(f"{n} veraltete Doppel aus {os.path.basename(f)} entfernt" for f, n in out["bereinigt"])
                        + f"\nOriginale: {out['backup']}")
        if out["fehler"]:
            text.append("Nicht geklappt:\n" + "\n".join(f"• {n}: {r}" for n, r in out["fehler"][:8]))
        QMessageBox.information(self, "Aufgeräumt", "\n\n".join(text) +
                                "\n\nStarte die Analyse neu, um den Stand zu aktualisieren.")
        touched = {os.path.normcase(f) for f in out["verschoben"]} | {os.path.normcase(f) for f, _n in out["bereinigt"]}
        result["entfernbar"] = [e for e in result["entfernbar"] if os.path.normcase(e["datei"]) not in touched]
        result["aufloesbar"] = [s for s in solvable if os.path.normcase(s["verlierer"]) not in touched]
        result["konflikte"] = [c for c in result["konflikte"]
                               if not any(os.path.normcase(f) in touched for f in c["dateien"])]
        self.refresh()

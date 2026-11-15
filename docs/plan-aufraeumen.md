# Plan: Repository aufräumen und sortieren

Stand: 15.11.2026 – geplant, noch nicht umgesetzt.

## Warum

Im Hauptordner liegen inzwischen 25 Python-Module nebeneinander (`dbpf.py`, `conflicts.py`, `web_session.py` …).
Wer neu dazukommt, findet nicht, was wohin gehört, und jede neue Funktion macht es unübersichtlicher.
Erzeugte Dateien (`backups/`, `reports/`, `*.db`, `__pycache__/`) sind schon per `.gitignore` draußen.

## Vorschlag für die Ordner

```
SimVault/
├─ main.py                 Kommandozeile (bleibt oben, damit „py -3 main.py …“ weiter geht)
├─ simvault_gui.py         Programmfenster starten (bleibt oben)
├─ simvault/               das eigentliche Programm als Paket
│  ├─ app/                 core, config, version, updater, i18n, i18n_texts_en
│  ├─ analysis/            dbpf, mod_folder_scanner, savegame_analyzer, missing_cc, conflicts, repair, thumbnails
│  ├─ finder/              cc_finder, cc_searcher, archive_tools, game_locator
│  ├─ web/                 web_session, downloads, secure_store, sources/ (TSR, CurseForge …)
│  ├─ storage/             database, report_generator, backup_manager
│  └─ gui/                 Programmfenster (heute gui/)
├─ plugins/                Erweiterungen der Nutzer (bleibt, Beispiel-Quellen)
├─ tests/                  nach Bereichen aufteilen: test_analysis.py, test_web.py … statt einer Riesendatei
├─ assets/                 Symbol, Logo
├─ scripts/                release_notes.py
├─ docs/                   Pläne, Screenshots, Entwickler-Doku (Dateiformate: DBPF, Blueprint/Room …)
└─ .github/                workflows/, ISSUE_TEMPLATE/
```

Ordnernamen englisch wie die Modulnamen; Kommentare und Texte bleiben, wie sie sind.

## Worauf achten

- **Mit `git mv` verschieben**, damit die Geschichte jeder Datei erhalten bleibt (`git log --follow`).
- **Alle Importe anpassen** (`import dbpf` → `from simvault.analysis import dbpf`). Danach komplette Tests,
  dazu `python main.py --help` und das Programmfenster einmal starten.
- **Erweiterungen nicht kaputt machen:** Plugins schreiben `from sources.base import Source`. Ein kleines
  Kompatibilitäts-Modul `sources/` (leitet auf `simvault.web.sources` weiter) bleibt mindestens bis zur
  nächsten großen Version; `API_VERSION` nicht ändern.
- **PyInstaller:** `simvault.spec` (hiddenimports, Pfade zu assets) und den Windows-Build-Workflow anpassen,
  danach einmal den Build laufen lassen und die EXE starten.
- **Pfade im Code**, die relativ zum Programmordner sind (assets, plugins, config.json), prüfen.
- **README/CHANGELOG/Plan-Dateien** auf neue Pfade aktualisieren.
- In **einem** Durchgang erledigen (eigener Branch, ein Pull Request), nicht nebenbei zu neuen Funktionen –
  sonst entstehen Konflikte mit laufender Arbeit.
- Zusätzlich sinnvoll: `CONTRIBUTING.md` (wie man Tests startet, wohin neue Quellen gehören, Commit-Stil),
  Testdatei aufteilen, `docs/formate.md` mit dem, was über DBPF/Blueprint/Room herausgefunden wurde.

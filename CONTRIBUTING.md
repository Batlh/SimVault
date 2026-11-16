# Mitmachen bei SimVault

Danke, dass du helfen willst! Hier steht, wie der Code aufgebaut ist und wie man ihn prüft.

## Aufbau

| Ordner | Inhalt |
|---|---|
| `main.py` | Kommandozeile (`py -3 main.py --help`) |
| `simvault_gui.py` | startet das Programmfenster |
| `simvault/app/` | Ablauf (`core.py`), Einstellungen (`config.py`), Version, Updates, Sprachen (`i18n.py`, `i18n_texts_en.py`) |
| `simvault/analysis/` | Dateien lesen und prüfen: DBPF-Pakete, Spielstände, fehlende CC, Konflikte, Reparatur, Vorschaubilder |
| `simvault/finder/` | CC auf dem PC finden, Archive entpacken, Spielordner erkennen |
| `simvault/web/` | Abrufe, Downloads, verschlüsselte Anmeldungen, Quellen (`sources/` – eine Klasse je CC-Seite) |
| `simvault/storage/` | Berichte, Backups, Datenbank |
| `simvault/gui/` | Programmfenster (Qt/PySide6), eine Datei je Seite in `pages/` |
| `plugins/` | eigene Quellen der Nutzer – Anleitung in `plugins/README.md` |
| `sources/` | nur Übergang: alte Erweiterungen schreiben `from sources.base import Source` |
| `tests/` | Tests nach Bereichen, gemeinsame Hilfen in `helpers.py` |
| `docs/` | Pläne und Dateiformate (`formate.md`) |

Regel: `simvault/app/core.py` verbindet alles; Oberfläche und Kommandozeile rufen nur `core` auf und rechnen
nichts selbst. Module in `analysis/` brauchen weder Qt noch Internet.

## Tests

```bash
pip install -r requirements.txt          # für Programmfenster-Tests: requirements-gui.txt
python -m unittest discover -s tests -v
```

Die Tests bauen ihre Pakete, Spielstände und Webseiten selbst – es werden keine echten Sims-Dateien und kein
Internet gebraucht. Sie laufen fest auf Deutsch (`SIMVAULT_LANG=de`). Neue Funktion = neuer Test in der
passenden Datei (`test_analysis.py`, `test_finder.py`, `test_web.py`, `test_sites.py`, `test_app.py`).

## Neue CC-Seite

Eigene Klasse in `simvault/web/sources/sites.py` (Vorlage: eine der vorhandenen), in `builtin.py` eintragen,
eine gespeicherte Beispielseite als Test in `tests/test_sites.py`. Seiten, die automatische Abrufe nicht
mögen, bekommen eine Prüfung (Captcha) im eingebauten Browser angezeigt – niemals automatisch lösen.
Downloads respektieren die Regeln der Seite (z. B. `DOWNLOAD_LIMITS` in `simvault/web/downloads.py`).

## Texte und Sprachen

Neue Texte für Kommandozeile und Berichte über `t("Vorlage {}", wert)` aus `simvault.app.i18n` und die englische
Fassung in `simvault/app/i18n_texts_en.py` eintragen – ein Test meldet fehlende Übersetzungen.
Texte im Programmfenster stehen im Katalog `EN` in `simvault/app/i18n.py`.

## Commits und Releases

- Kurze deutsche Commit-Nachricht: erste Zeile was, darunter warum.
- Jede sichtbare Änderung bekommt eine Zeile unter `## [Unveröffentlicht]` in `CHANGELOG.md` – daraus entstehen
  die Release-Notizen (`scripts/release_notes.py`).
- Release: Abschnitt in `CHANGELOG.md` auf die Version umbenennen, dann den Workflow „Windows-Build“ mit der
  Version (z. B. `v0.6.0`) starten.

# Plan: Debug-Log, Absturz-Fänger und Fehlerberichte für GitHub

Stand: 17.11.2026 – geplant, noch nicht gebaut. Pfade passen zur neuen Ordnerstruktur (PR #2). Tests kommen in `tests/test_app.py`.

## Warum

Die Windows-EXE hat kein Konsolenfenster: Meldungen von `logging` landen nirgends, Abstürze verschwinden spurlos.
Wer einen Fehler melden will, hat nichts in der Hand. Ziel: Nutzer können mit zwei Klicks einen brauchbaren,
**datenschutzfreundlichen** Fehlerbericht als GitHub-Issue anlegen.

## 1. Log-Datei

- Ort: `%APPDATA%\SimVault\logs\simvault.log` (Linux: `~/.config/simvault/logs/`), gleiche Basis wie
  `NewSea._cache_path()` – am besten eine gemeinsame Funktion `paths.user_data_dir()`.
- `RotatingFileHandler`: 5 Dateien × 1 MB, UTF-8, Format mit Zeit, Ebene, Modul.
- Immer INFO; DEBUG über Einstellung `"debug_log": true` (Einstellungen → „Ausführliches Protokoll“) oder `-v`.
- Eingebaut in `simvault/gui/app.py` (statt `basicConfig`) und `main.py::_setup_logging` (Konsole + Datei).
- Kopfzeile pro Start: SimVault-Version, Windows-/Python-/Qt-Version, Sprache.

## 2. Absturz-Fänger

- `sys.excepthook` und `threading.excepthook`: Stacktrace ins Log (ERROR), im Programmfenster ein Dialog
  „Unerwarteter Fehler“ mit „Fehler melden“.
- `simvault/gui/worker.py::Task.run`: Ausnahmen bereits als `failed` – zusätzlich `log.exception(...)`.
- Harte Abstürze (Segfault, z. B. Qt WebEngine): `faulthandler.enable(file=…)` in
  `logs/absturz.txt`. Beim Start: Datei vorhanden und nicht leer → Dialog
  „SimVault ist beim letzten Mal abgestürzt – Fehlerbericht ansehen?“, danach umbenennen (`absturz_<zeit>.txt`).
- Marker-Datei `laeuft.lock` beim Start anlegen, beim sauberen Beenden löschen → erkennt auch Abstürze ohne
  Stacktrace.

## 3. „Fehler melden“

- Neues Modul `simvault/app/bugreport.py` (ohne Qt, testbar):
  - `collect(cfg, log_lines=300)` → Text: Version, System, Einstellungen (ohne Geheimnisse), letzte Log-Zeilen,
    letzter Absturz.
  - `anonymize(text)`: Windows-Benutzername und Home-Pfad → `%USERNAME%` / `~`; E-Mail-Adressen, Tokens,
    Cookie-/Passwort-Werte, `database.password`, Inhalte von `logins.bin` **nie** aufnehmen; URLs mit
    Query-Parametern kürzen.
  - `issue_url(title, body)` → `https://github.com/Batlh/SimVault/issues/new?template=fehler.yml&title=…&body=…`;
    zu lang (> ~6000 Zeichen URL) → Bericht als Datei `simvault_fehlerbericht_<zeit>.txt` speichern, Link ohne
    Body öffnen, Hinweis „Datei anhängen“.
- GUI: Dialog mit editierbarer **Vorschau** des kompletten Textes, Knöpfe „Auf GitHub melden“,
  „Als Datei speichern“, „Abbrechen“. Nichts wird ohne Klick verschickt. Zu finden unter Einstellungen
  (und Hilfe-Knopf in der Seitenleiste) sowie in beiden Absturz-Dialogen.
- Kommandozeile: `py -3 main.py bugreport` gibt den anonymisierten Bericht aus bzw. speichert ihn.

## 4. GitHub-Vorlagen

- `.github/ISSUE_TEMPLATE/fehler.yml` (Formular): Was hast du gemacht? / Was ist passiert? / Was hättest du
  erwartet? / Fehlerbericht aus SimVault (Textfeld, `render: text`) / Version / Windows-Version.
- `.github/ISSUE_TEMPLATE/wunsch.yml`: Idee, wofür, Beispiel-Seite oder -Datei.
- `.github/ISSUE_TEMPLATE/config.yml`: `blank_issues_enabled: true`.

## 5. Tests & Doku

- `anonymize`: Benutzername in Pfaden, E-Mail, Passwort in config, Cookie-Werte → alle weg.
- `collect` mit einer Beispiel-config: keine Geheimnisse, Version enthalten.
- `issue_url`: richtige Kodierung, Fallback bei zu langem Text.
- Absturz-Erkennung: Marker-Datei vorhanden → `previous_crash()` meldet es.
- i18n: alle neuen Texte deutsch/englisch (Test „jede Vorlage übersetzt“ auf `simvault/app/bugreport.py` erweitern).
- README-Abschnitt „Fehler melden“, CHANGELOG.

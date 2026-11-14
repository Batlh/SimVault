# Modul: i18n.py
# Funktion: Mehrsprachigkeit der Oberfläche. Ausgangssprache ist Deutsch; für Englisch gibt es unten den Katalog.
#
# Einstellung "ui_language" in config.json: "auto" (Sprache von Windows), "de" oder "en".
# Übersetzt werden alle sichtbaren Texte der Fenster (Knöpfe, Beschriftungen, Spalten, Hinweise, Dialoge)
# über translate_widget(); Texte mit Zahlen darin laufen über Muster wie "Aufräumen ({})".
# Eine weitere Sprache = ein weiterer Katalog wie EN (Schlüssel: deutscher Text, Wert: Übersetzung).
#
# Noch deutsch bleiben: die Kommandozeile, die Berichte und einige ausführliche Meldungen.

import re
import locale

LANGUAGES = {"de": "Deutsch", "en": "English"}
_lang = "de"


def detect():
    """Sprache des Systems: "de" bei deutschem Windows, sonst "en"."""
    code = ""
    try:
        from PySide6.QtCore import QLocale
        code = QLocale.system().name()
    except Exception:
        try:
            code = locale.getlocale()[0] or ""
        except Exception:
            code = ""
    return "de" if code.lower().startswith("de") else "en"


def set_language(code):
    global _lang
    code = (code or "auto").lower()
    _lang = detect() if code == "auto" else (code if code in LANGUAGES else "de")
    return _lang


def language():
    return _lang


def tr(text):
    """Übersetzt text in die eingestellte Sprache (unbekannte Texte bleiben, wie sie sind)."""
    if _lang == "de" or not text:
        return text
    catalog = CATALOGS.get(_lang, {})
    if text in catalog:
        return catalog[text]
    for pattern, target in _patterns(_lang):
        m = pattern.fullmatch(text)
        if m:
            return target.format(*[tr(g) for g in m.groups()])
    return text


_compiled = {}


def _patterns(lang):
    if lang not in _compiled:
        items = []
        for src, dst in CATALOGS.get(lang, {}).items():
            if "{}" in src:
                regex = re.escape(src).replace(r"\{\}", "(.+?)")
                items.append((re.compile(regex, re.S), dst))
        _compiled[lang] = items
    return _compiled[lang]


# ---------------------------------------------------------------------------
# Fenster übersetzen
# ---------------------------------------------------------------------------

def _apply(obj, key, getter, setter):
    """Übersetzt einen Text; merkt sich Original und Übersetzung, damit nichts doppelt übersetzt wird."""
    current = getter()
    if not current:
        return
    stored = obj.property(key)                      # nur Text speichern (Qt-Eigenschaften mögen keine Listen)
    if isinstance(stored, str) and current == stored:
        return                                      # schon übersetzt
    target = tr(current)
    if target != current:
        obj.setProperty(key, target)
        setter(target)


def translate_widget(root):
    """Übersetzt root und alle Kind-Elemente (sofort sichtbar, auch nachträglich gesetzte Texte)."""
    if _lang == "de" or root is None:
        return
    from PySide6.QtWidgets import (QAbstractButton, QComboBox, QGroupBox, QLabel, QLineEdit, QListWidget,
                                   QTabWidget, QTableWidget, QTextBrowser, QWidget)
    widgets = [root] + root.findChildren(QWidget)
    # Der eingebaute Browser (Chromium) und alles darin bleibt unangetastet
    browsers = [w for w in widgets if "WebEngine" in w.metaObject().className()]
    for w in widgets:
        cls = w.metaObject().className()
        if "WebEngine" in cls or "Quick" in cls or "RenderWidget" in cls \
                or any(b is not w and b.isAncestorOf(w) for b in browsers):
            continue
        if isinstance(w, (QAbstractButton, QLabel)):
            _apply(w, "_tr_text", w.text, w.setText)
        if isinstance(w, QLineEdit):
            _apply(w, "_tr_ph", w.placeholderText, w.setPlaceholderText)
        if isinstance(w, QGroupBox):
            _apply(w, "_tr_title", w.title, w.setTitle)
        if w.toolTip():
            _apply(w, "_tr_tip", w.toolTip, w.setToolTip)
        if w.isWindow() and w.windowTitle():
            _apply(w, "_tr_wt", w.windowTitle, w.setWindowTitle)
        if isinstance(w, QTabWidget):
            for i in range(w.count()):
                text = w.tabText(i)
                if tr(text) != text:
                    w.setTabText(i, tr(text))
        if isinstance(w, QComboBox):
            for i in range(w.count()):
                text = w.itemText(i)
                if tr(text) != text:
                    w.setItemText(i, tr(text))
        if isinstance(w, QTableWidget):
            for i in range(w.columnCount()):
                item = w.horizontalHeaderItem(i)
                if item and tr(item.text()) != item.text():
                    item.setText(tr(item.text()))
        if isinstance(w, QListWidget):
            for i in range(w.count()):
                item = w.item(i)
                if tr(item.text()) != item.text():
                    item.setText(tr(item.text()))
        if isinstance(w, QTextBrowser):
            pass                                    # ausführliche HTML-Texte bleiben deutsch


def install(app=None):
    """Übersetzt Meldungsfenster (QMessageBox, Auswahl-Dialoge). Das Hauptfenster übersetzt sich selbst.
    Bewusst kein anwendungsweiter Event-Filter: der verträgt sich nicht mit dem eingebauten Browser."""
    if _lang == "de" or getattr(install, "_done", False):
        return None
    from PySide6.QtWidgets import QInputDialog, QMessageBox
    for name in ("information", "warning", "question", "critical"):
        original = getattr(QMessageBox, name)

        def wrapped(parent, title, text, *args, _original=original, **kwargs):
            return _original(parent, tr(title), tr(text), *args, **kwargs)

        setattr(QMessageBox, name, staticmethod(wrapped))
    original_item = QInputDialog.getItem

    def get_item(parent, title, label, *args, **kwargs):
        return original_item(parent, tr(title), tr(label), *args, **kwargs)

    QInputDialog.getItem = staticmethod(get_item)
    install._done = True
    return True


# ---------------------------------------------------------------------------
# Englisch
# ---------------------------------------------------------------------------

EN = {
    # Navigation
    "Übersicht": "Overview", "Mods": "Mods", "Fehlende CC": "Missing CC", "CC-Suche": "CC finder",
    "Websuche": "Web search", "Konflikte": "Conflicts", "Reparatur": "Repair", "Backup": "Backup",
    "Quellen": "Sources", "Einstellungen": "Settings", "Bereit.": "Ready.", "Fertig.": "Done.",
    "Abbrechen": "Cancel", "Update verfügbar": "Update available", "Version {}": "Version {}",
    # Übersicht
    "Mods-Ordner, Spielstände und Bibliothek auf einen Blick.": "Mods folder, savegames and library at a glance.",
    "Mod-Dateien": "Mod files", "genutzt": "used", "ungenutzt": "unused", "fehlende CC-Teile": "missing CC parts",
    "Probleme im Mods-Ordner": "Problems in the Mods folder", "auf dem PC gefunden": "found on this PC",
    "alle Spielstände": "all savegames", "Bibliothek einbeziehen": "include library",
    "Analyse starten": "Start analysis", "Bericht öffnen": "Open report", "Fehlende CC ansehen": "Show missing CC",
    "CC auf dem PC suchen": "Search PC for CC", "Konflikte ansehen": "Show conflicts",
    "Noch keine Analyse in dieser Sitzung – „Analyse starten“ liest Mods, Spielstände und Bibliothek ein.":
        "No analysis yet in this session – “Start analysis” reads mods, savegames and library.",
    "Noch keine Analyse – auf der Übersicht „Analyse starten“.": "No analysis yet – click “Start analysis” on the overview.",
    "Spielstände: {}": "Savegames: {}", "Analyse fertig – {}": "Analysis done – {}",
    # Mods
    "Alle .package- und .ts4script-Dateien mit Nutzung. „ungenutzt“ = CAS-/Objekt-CC, die in keinem Spielstand und "
    "keinem Bibliothekseintrag vorkommt.": "All .package and .ts4script files with their usage. “unused” = CAS/object "
    "CC that appears in no savegame and no library entry.",
    "Filtern …": "Filter …", "alle": "all", "Datei": "File", "Kategorie": "Category", "Status": "Status",
    "Status:": "Status:", "Spielstände": "Savegames", "Bibliothek": "Library", "Größe": "Size",
    "Im Explorer zeigen": "Show in Explorer", "Im Netz suchen …": "Search the web …", "defekt": "broken",
    "nicht nachweisbar": "not provable", "nicht prüfbar": "not checkable", "Tuning/Sonstiges": "Tuning/other",
    "CAS + Objekt": "CAS + object", "Defekt": "Broken",
    # Fehlende CC
    "CAS-Teile und Objekte, die in Spielständen oder der Bibliothek verwendet werden, aber nicht installiert sind.":
        "CAS parts and objects that are used in savegames or the library but are not installed.",
    "Filtern (ID, Art, Sim, Haushalt, Grundstück …)": "Filter (ID, kind, Sim, household, lot …)",
    "Objekt": "Object", "Auf dem PC suchen": "Search this PC",
    "ID": "ID", "Art": "Kind", "Anzahl": "Count", "Verwendet von": "Used by", "Gefunden in": "Found in",
    "Teile": "Parts", "Keine Bibliotheks-Einträge mit fehlender CC.": "No library entries with missing CC.",
    "{} fehlende Teile, davon {} auf dem PC gefunden. {}": "{} missing parts, {} of them found on this PC. {}",
    "ID kopieren": "Copy ID",
    # CC-Suche (Fundgrube)
    "Sucht die fehlende CC in Ordnern, auf weiteren Laufwerken und in ZIP-/RAR-/7z-Archiven. Entpacktes wird sofort "
    "wieder gelöscht.": "Searches folders, other drives and ZIP/RAR/7z archives for the missing CC. Anything unpacked "
    "is deleted right away.",
    "Wo suchen?": "Where to search?", "Ordner hinzufügen …": "Add folder …", "weitere Orte": "more places",
    "weitere Laufwerke (D:, E:, USB …)": "other drives (D:, E:, USB …)", "auch ganz C:": "all of C: as well",
    "Suche starten": "Start search", "Fundort": "Location", "Für": "For",
    "Funde in den Mods-Ordner holen": "Bring finds into the Mods folder", "auslassen, z. B.: WickedWhims":
        "leave out, e.g. WickedWhims", "vorher Mods-Ordner sichern": "back up Mods folder first",
    "Zurückholen": "Restore",
    # Websuche
    "CC im Netz suchen, im eingebauten Browser herunterladen – SimVault entpackt und installiert Downloads selbst, "
    "ohne Doppeltes.": "Search the web for CC and download it in the built-in browser – SimVault unpacks and "
    "installs downloads itself, without duplicates.",
    "Suchbegriff, z. B. Ersteller und Name: „Kijiko eyelash“": "Search term, e.g. creator and name: “Kijiko eyelash”",
    "Suchen": "Search", "Treffer": "Results", "Browser": "Browser", "Downloads": "Downloads",
    "Noch keine Suche.": "No search yet.", "Im Browser öffnen": "Open in browser",
    "Herunterladen und installieren": "Download and install",
    "Downloads aus dem Browser sofort installieren": "Install browser downloads right away",
    "Zeit": "Time", "Ergebnis": "Result", "Installieren": "Install", "Download-Ordner öffnen": "Open download folder",
    "Aus der Liste entfernen": "Remove from list", "Adresse oder Suchbegriff …": "Address or search term …",
    "Anmeldung speichern": "Save login",
    "Der Download läuft über die Seite – im Browser starten, SimVault installiert die Datei danach selbst.":
        "The download runs through the site – start it in the browser, SimVault installs the file afterwards.", "{} Treffer.": "{} results.", "Suche „{}“ …": "Searching “{}” …",
    "heruntergeladen": "downloaded", "installiert": "installed", "übersprungen": "skipped", "Fehler": "Error",
    "wird installiert": "installing", "installiert: {}": "installed: {}", "{}; {} übersprungen": "{}; {} skipped",
    "{} übersprungen": "{} skipped", "{} Fehler": "{} errors", "nichts zu installieren": "nothing to install",
    "{}× Paket": "{}× package", "{}× Script": "{}× script", "{}× Bibliothek": "{}× library",
    "{}, {}": "{}, {}", "{}; {}": "{}; {}",
    "Speichert die Anmeldung für diese Seite verschlüsselt (AES-256). Passwörter werden nie gespeichert.":
        "Saves the login for this site encrypted (AES-256). Passwords are never stored.",
    # Konflikte
    "Dieselbe CC in mehreren Dateien: SimVault vergleicht den Inhalt, gleicht mit Spielständen und Bibliothek ab und "
    "sagt, was zu tun ist.": "The same CC in several files: SimVault compares the content, checks savegames and "
    "library and tells you what to do.",
    "Filtern (Datei, Art …)": "Filter (file, kind …)", "Aufräumen ({})": "Clean up ({})",
    "Mods-Ordner öffnen": "Open Mods folder", "Dateien": "Files", "Gemeinsam": "Shared", "Identisch": "Identical",
    "Unterschiedlich": "Different", "In Benutzung": "In use", "Konflikt": "Conflict", "Doppelt": "Duplicate",
    "Überschneidung": "Overlap", "Überschreibung": "Override",
    "Sortiert überflüssige Dateien aus und entfernt veraltete Doppel – nur was sicher geht.":
        "Moves redundant files out and removes outdated copies – only what is safe.",
    "Keine Überschneidungen im Mods-Ordner gefunden.": "No overlaps found in the Mods folder.",
    "Zeile anklicken für die Empfehlung.": "Click a row for the recommendation.",
    # Reparatur
    "Prüft CC-Dateien und Spielstände. Reparierbar sind: falsch benannte Archive, einzelne kaputte Ressourcen in einem "
    "Paket und Spielstände, von denen das Spiel noch eine intakte ältere Fassung hat. Leere oder abgeschnittene "
    "Downloads kann niemand reparieren – die müssen neu geladen werden. Vor jeder Reparatur wird das Original im "
    "Backup-Ordner gesichert.": "Checks CC files and savegames. Repairable: misnamed archives, single broken "
    "resources in a package, and savegames the game still has an intact older version of. Empty or truncated "
    "downloads cannot be repaired by anyone – download them again. The original is backed up before every repair.",
    "Prüfen": "Check", "Gründlich prüfen": "Check thoroughly", "Reparieren": "Repair",
    "Reparieren ({})": "Repair ({})", "nur beschädigte zeigen": "show broken only", "Noch nicht geprüft.": "Not checked yet.",
    "Typ": "Type", "Zustand": "Condition", "Reparierbar": "Repairable", "Problem": "Problem", "Spielstand": "Savegame",
    "in Ordnung": "OK", "ja": "yes", "nein": "no",
    "Entpackt jede einzelne Ressource – findet auch Schäden mitten in einer Datei, dauert länger.":
        "Unpacks every single resource – also finds damage in the middle of a file, takes longer.",
    # Backup
    "Voll-Backup = alles als ZIP. Delta = nur neue/geänderte Dateien seit dem letzten Delta-Backup. Beim "
    "Wiederherstellen eines Deltas spielt SimVault automatisch das letzte Voll-Backup und alle Deltas danach ein.":
        "Full backup = everything as a ZIP. Delta = only new/changed files since the last delta backup. When "
        "restoring a delta, SimVault automatically restores the last full backup and all deltas after it.",
    "Neues Backup": "New backup", "Was:": "What:", "Art:": "Kind:", "Mods-Ordner": "Mods folder",
    "Voll-Backup (ZIP)": "Full backup (ZIP)", "Delta (nur Änderungen)": "Delta (changes only)",
    "Backup erstellen": "Create backup", "Vorhandene Backups": "Existing backups", "Datum": "Date",
    "Wiederherstellen …": "Restore …", "Backup-Ordner öffnen": "Open backup folder",
    "Alte Backups aufräumen": "Clean up old backups", "Jetzt aufräumen …": "Clean up now …",
    "nach jedem neuen Backup automatisch": "automatically after every new backup",
    "nur Fehlendes ergänzen": "only add what is missing", "genau auf Backup-Stand bringen": "make it exactly like the backup",
    "Vorhandene Dateien bleiben, wie sie sind – es kommt nur zurück, was fehlt.":
        "Existing files stay as they are – only what is missing comes back.",
    "Dateien, die das Backup nicht kennt, werden in den Backup-Ordner beiseitegelegt (nicht gelöscht).":
        "Files the backup does not know are put aside in the backup folder (not deleted).",
    "Voll-Backup": "Full backup", "Delta": "Delta", "Auswahl": "Selection",
    # Quellen
    "Webseiten für die CC-Suche. Neue Quellen ergänzt du als Erweiterung: eine .json-Datei (nur Such-Link) oder eine "
    ".py-Datei (echte Treffer, auch mit Login) im Erweiterungs-Ordner – Anleitung: plugins/README.md.":
        "Websites for the CC search. Add new sources as extensions: a .json file (search link only) or a .py file "
        "(real results, also with login) in the extensions folder – guide: plugins/README.md.",
    "Aktiv": "Active", "Name": "Name", "Login": "Login", "Angemeldet": "Logged in", "18+": "18+", "Herkunft": "Origin",
    "Such-Link": "Search link", "nötig": "required", "möglich": "possible", "mitgeliefert": "built in",
    "ja, seit {}": "yes, since {}", "Erweiterungs-Ordner öffnen": "Open extensions folder", "Neu laden": "Reload",
    "Anmelden …": "Log in …", "Abmelden": "Log out", "Links erzeugen": "Create links",
    "Im Programm suchen": "Search in SimVault", "Suche testen, z. B. „Kijiko eyelash“ …": "Test a search, e.g. “Kijiko eyelash” …",
    "Öffnet die Anmeldeseite im eingebauten Browser. Gespeichert werden nur die Cookies danach – verschlüsselt "
    "(AES-256), nie das Passwort.": "Opens the login page in the built-in browser. Only the cookies afterwards are "
    "stored – encrypted (AES-256), never the password.",
    "Anmeldungen: verschlüsselt mit AES-256-GCM, Schlüssel geschützt durch {}. Passwörter werden nie gespeichert.":
        "Logins: encrypted with AES-256-GCM, key protected by {}. Passwords are never stored.",
    "Windows-Benutzerkonto (DPAPI)": "the Windows user account (DPAPI)",
    "Dateirechte (nur dieser Benutzer)": "file permissions (this user only)",
    # Einstellungen
    "Ordner": "Folders", "Sims-4-Ordner:": "Sims 4 folder:", "Spielordner:": "Game folder:", "Backups:": "Backups:",
    "Berichte:": "Reports:", "Temp-Ordner:": "Temp folder:", "Durchsuchen …": "Browse …",
    "Automatisch suchen": "Find automatically", "Entpacker für RAR/7z:": "Unpacker for RAR/7z:",
    "Automatisch": "Automatic", "Eigener Pfad …": "Own path …", "Keiner (RAR/7z überspringen)": "None (skip RAR/7z)",
    "Pfad zu 7z.exe, UnRAR.exe oder tar.exe": "Path to 7z.exe, UnRAR.exe or tar.exe",
    "weitere Laufwerke (D:, E:, USB …) mit durchsuchen": "also search other drives (D:, E:, USB …)",
    "Archive größer als … überspringen:": "Skip archives larger than:", "Speichern": "Save",
    "Einstellungsdatei öffnen": "Open settings file", "Programm": "Program", "Programmname:": "Program name:",
    "Logo:": "Logo:", "Updates:": "Updates:", "beim Start nach einer neuen Version suchen": "check for a new version on start",
    "Jetzt nach Updates suchen": "Check for updates now", "Sprache:": "Language:",
    "Automatisch (Windows-Sprache)": "Automatic (Windows language)",
    "Die Sprache wechselt nach einem Neustart von SimVault.": "The language changes after restarting SimVault.",
    "z. B. Dokumente\\Electronic Arts\\Die Sims 4": "e.g. Documents\\Electronic Arts\\The Sims 4",
    "optional – Spiel-Installation für sichere Fehlend-Erkennung": "optional – game installation for exact missing-CC detection",
    "leer = System-Temp (z. B. auf D: legen, wenn C: knapp ist)": "empty = system temp (e.g. put it on D: if C: is full)",
    "optional – eigenes Logo (PNG/JPG) für Fenster und Berichte": "optional – own logo (PNG/JPG) for window and reports",
    "Sucht die Sims-4-Installation: EA App/Origin, Steam, Epic und alle Laufwerke.":
        "Looks for the Sims 4 installation: EA app/Origin, Steam, Epic and all drives.",
    "Datei auswählen": "Choose file", "Einstellungen gespeichert.": "Settings saved.",
    # häufige Dialoge
    "Willkommen bei SimVault": "Welcome to SimVault", "Spielordner": "Game folder", "Anmelden": "Log in",
    "Installieren …": "Install …", "Aufräumen": "Clean up", "Aufgeräumt": "Cleaned up", "Prüfung": "Check",
    "Prüfung fertig.": "Check finished.", "Download": "Download", "Analyse": "Analysis",
    "Sims-4-Installation gefunden": "Sims 4 installation found",
    "Der Sims-4-Ordner wurde nicht automatisch gefunden.\nBitte unter „Einstellungen“ festlegen.":
        "The Sims 4 folder was not found automatically.\nPlease set it under “Settings”.",
    "Bitte zuerst eine Quelle in der Liste auswählen.": "Please select a source in the list first.",
    "Abgebrochen.": "Cancelled.",
}

CATALOGS = {"en": EN}

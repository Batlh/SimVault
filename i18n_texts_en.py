# Modul: i18n_texts_en.py
# Funktion: Englische Texte für die Kommandozeile (main.py) und die Berichte (report_generator.py).
# Schlüssel: deutscher Text bzw. deutsche Vorlage mit {} – genau so, wie er im Code an t()/tr() geht.
# Ein Test (tests/test_simvault.py) prüft, dass jede Vorlage aus main.py und report_generator.py hier steht.

EN_CLI = {
    # Werte aus der Analyse (Kategorien, Zustände, Arten)
    "CAS": "CAS", "Script": "Script", "Hinweis": "Note", "Warnung": "Warning",
    "Archiv": "Archive", "Beschädigt": "Damaged", "Duplikat": "Duplicate", "Leer": "Empty",
    "Paket zu tief": "Package too deep", "Script zu tief": "Script too deep", "Ordner fehlt": "Folder missing",
    "Paket": "Package", "Quellordner": "Source folder", "CAS-Teil": "CAS part",
    "{} (Steckplatz {})": "{} (slot {})",
    "Hut/Kopfschmuck": "Hat/headwear", "Haare": "Hair", "Kopf": "Head", "Zähne": "Teeth",
    "Ganzkörper-Outfit": "Full-body outfit", "Oberteil": "Top", "Unterteil": "Bottom", "Schuhe": "Shoes",
    "Accessoire": "Accessory", "Ohrringe": "Earrings", "Brille": "Glasses", "Halskette": "Necklace",
    "Handschuhe": "Gloves", "Armband links": "Bracelet left", "Armband rechts": "Bracelet right",
    "Lippenpiercing links": "Lip piercing left", "Lippenpiercing rechts": "Lip piercing right",
    "Nasenpiercing links": "Nose piercing left", "Nasenpiercing rechts": "Nose piercing right",
    "Augenbrauenpiercing links": "Brow piercing left", "Augenbrauenpiercing rechts": "Brow piercing right",
    "Ring Zeigefinger links": "Ring index finger left", "Ring Zeigefinger rechts": "Ring index finger right",
    "Ring Ringfinger links": "Ring ring finger left", "Ring Ringfinger rechts": "Ring ring finger right",
    "Ring Mittelfinger links": "Ring middle finger left", "Ring Mittelfinger rechts": "Ring middle finger right",
    "Bart": "Facial hair", "Lippenstift": "Lipstick", "Lidschatten": "Eyeshadow", "Eyeliner/Wimpern": "Eyeliner/lashes",
    "Rouge": "Blush", "Gesichtsbemalung": "Face paint", "Augenbrauen": "Eyebrows", "Augenfarbe": "Eye colour",
    "Socken": "Socks", "Mascara": "Mascara", "Strumpfhose": "Tights", "Hautüberlagerung": "Skin overlay",
    "Hautdetail": "Skin detail", "Tattoo": "Tattoo",
    "Delta": "Delta", "Auswahl": "Selection", "Originale (Reparatur)": "Originals (repair)",
    "Originale (Konflikte)": "Originals (conflicts)", "Beiseitegelegt (Wiederherstellung)": "Set aside (restore)",

    # Ausgaben
    "Scanne Mods-Ordner: {}": "Scanning Mods folder: {}",
    "Lese Spielstände und Bibliothek …": "Reading savegames and library …",
    "Abgleich mit Mods-Ordner und Spielordner ({})": "Compared with Mods folder and game folder ({})",
    "Abgleich mit dem Mods-Ordner; Spielordner nicht gefunden – EA-Inhalte werden an ihren kleineren IDs erkannt":
        "Compared with the Mods folder; game folder not found – EA content is recognised by its smaller IDs",
    "Ermittle fehlende CC aus {} Spielständen und der Bibliothek …":
        "Determining missing CC from {} savegames and the library …",
    "{} fehlende Teile. Durchsuche:": "{} missing parts. Searching:",
    "Sichere zuerst den Mods-Ordner nach {} …": "Backing up the Mods folder to {} first …",
    "Backup: {}": "Backup: {}",
    "Bericht: {} – {} Datei(en)": "Report: {} – {} file(s)",
    "Gleiche mit {} Spielständen und der Bibliothek ab …": "Comparing with {} savegames and the library …",
    "Backup ({}) erstellt: {}": "Backup ({}) created: {}",
    "Installiert: {}   Neuestes Release: {}": "Installed: {}   Latest release: {}",
    "1) Sims-4-Ordner (mit Mods, saves, Tray)": "1) Sims 4 folder (with Mods, saves, Tray)",
    "j": "y", "n": "n",
    "{} nicht gefunden: {}": "{} not found: {}",
    "Bitte den Pfad in config.json eintragen (sims_folder oder den einzelnen Ordner).":
        "Please enter the path in config.json (sims_folder or the individual folder).",
    "fehlt": "missing",
    "Konfigurationsdatei: {}": "Config file: {}",
    "{} Mod-Dateien gefunden.": "{} mod files found.",
    "Konflikte geprüft: {}": "Conflicts checked: {}",
    ", {} in Benutzung": ", {} in use",
    "{} überflüssige Datei(en) aussortieren ({:.1f} MB)": "move out {} redundant file(s) ({:.1f} MB)",
    "{} Konflikt(e) mit veralteter Fassung auflösen": "resolve {} conflict(s) with an outdated version",
    "Berichte:": "Reports:",
    "Spielstand nicht gefunden: {}": "Savegame not found: {}",
    "Kein Spielstand gefunden in {} – es wird nur die Bibliothek geprüft.":
        "No savegame found in {} – only the library is checked.",
    "Lese Spielinhalte aus {} (beim ersten Mal etwas länger) …":
        "Reading game content from {} (takes a bit longer the first time) …",
    'Keine Suchordner gefunden. Ordner angeben: python main.py find "D:\\Alte Mods"':
        'No search folders found. Give a folder: python main.py find "D:\\Old Mods"',
    "Es fehlt keine CC – nichts zu suchen. 🎉": "No CC is missing – nothing to search. 🎉",
    "Entpacker für RAR/7z: {} ({})": "Extractor for RAR/7z: {} ({})",
    "Kein Entpacker für RAR/7z – diese Archive werden übersprungen. Tipp: winget install 7zip.7zip, dann py -3 main.py setup":
        "No extractor for RAR/7z – these archives are skipped. Tip: winget install 7zip.7zip, then py -3 main.py setup",
    "Gefunden: {} von {} fehlenden Teilen in {} Datei(en).": "Found: {} of {} missing parts in {} file(s).",
    " (+{} weitere Fundorte)": " (+{} more locations)",
    "{} Archiv(e) konnten nicht durchsucht werden, davon {} mit Sims-Bezug:":
        "{} archive(s) could not be searched, {} of them Sims-related:",
    "{} Datei(en) zurückgeholt nach {}": "{} file(s) restored to {}",
    "{} Datei(en) nicht kopiert, damit nichts doppelt im Mods-Ordner landet:":
        "{} file(s) not copied so nothing ends up twice in the Mods folder:",
    'Tipp: Mit "py -3 main.py analyze --all-saves" prüfst du, was jetzt noch fehlt.':
        'Tip: "py -3 main.py analyze --all-saves" checks what is still missing.',
    'Kein Suchbericht mit Funden gefunden – zuerst "py -3 main.py find" ausführen.':
        'No search report with finds – run "py -3 main.py find" first.',
    "Prüfe CC-Dateien und Spielstände (gründlich – das dauert) …":
        "Checking CC files and savegames (thorough – this takes a while) …",
    "Prüfe CC-Dateien und Spielstände …": "Checking CC files and savegames …",
    "{} CC-Dateien und {} Spielstände geprüft: {} beschädigt.": "{} CC files and {} savegames checked: {} damaged.",
    "reparierbar": "repairable", "nicht reparierbar": "not repairable",
    "Originale gesichert in {}": "Originals backed up in {}",
    "Regeln: höchstens {} Voll-Backups je Ordner, nichts älter als {} Tage; das neueste Voll-Backup bleibt immer.":
        "Rules: at most {} full backups per folder, nothing older than {} days; the newest full backup always stays.",
    "SimVault ist aktuell.": "SimVault is up to date.",
    "SimVault einrichten – Enter übernimmt den Vorschlag in [Klammern].":
        "Set up SimVault – Enter accepts the suggestion in [brackets].",
    "2) Spielordner (die Installation – macht die Erkennung fehlender CC genau). Suche …":
        "2) Game folder (the installation – makes missing-CC detection exact). Searching …",
    "Nummer, eigener Pfad oder '-' für keinen": "Number, own path or '-' for none",
    "3) Entpacker für RAR- und 7z-Archive bei der CC-Suche:": "3) Extractor for RAR and 7z archives in the CC search:",
    "eigenen Pfad angeben (7z.exe, UnRAR.exe oder tar.exe)": "enter own path (7z.exe, UnRAR.exe or tar.exe)",
    "keinen – RAR/7z-Archive überspringen": "none – skip RAR/7z archives",
    "Auswahl": "Choice",
    "4) Bei der Suche auch alle weiteren Laufwerke (D:, E:, USB …) durchsuchen? (j/n)":
        "4) Also search all other drives (D:, E:, USB …)? (y/n)",
    "Gespeichert in {}": "Saved in {}",
    "Nutzung:": "Usage:",
    "{} Problem(e):": "{} problem(s):",
    "Konflikte: keine": "Conflicts: none",
    "{} gemeinsames Teil ({} identisch, {} unterschiedlich{})": "{} shared part ({} identical, {} different{})",
    "{} gemeinsame Teile ({} identisch, {} unterschiedlich{})": "{} shared parts ({} identical, {} different{})",
    "… {} weitere im Bericht": "… {} more in the report",
    "Sicher machbar: {} – mit: py -3 main.py conflicts --aufraeumen":
        "Safe to do: {} – with: py -3 main.py conflicts --clean",
    'Tipp: Mit "python main.py find" suchst du die fehlende CC auf deinem PC (Downloads, alte Mods-Ordner, ZIP-Archive).':
        'Tip: "python main.py find" searches your PC for the missing CC (downloads, old Mods folders, ZIP archives).',
    "{:>3} Teile ({})  {}{}": "{:>3} parts ({})  {}{}",
    "… {} weitere ohne erkennbaren Sims-Bezug (siehe Bericht)": "… {} more without visible Sims relation (see report)",
    "nicht geklappt: {} – {}": "failed: {} – {}",
    "Backup fehlgeschlagen ({}) – es wird nichts zurückgeholt.": "Backup failed ({}) – nothing is restored.",
    "Es wurde nichts gelöscht – zum Rückgängigmachen einfach zurück in den Mods-Ordner schieben.":
        "Nothing was deleted – to undo, simply move them back into the Mods folder.",
    "Originale der geänderten Pakete: {}": "Originals of the changed packages: {}",
    "{} davon lassen sich reparieren: py -3 main.py repair --ausfuehren":
        "{} of them can be repaired: py -3 main.py repair --apply",
    "Keine Backups in {}": "No backups in {}",
    'Welches Backup? Namen aus "py -3 main.py backup list" angeben.':
        'Which backup? Give a name from "py -3 main.py backup list".',
    "Eingespielt in dieser Reihenfolge: {}": "Restored in this order: {}",
    "{} Datei(en) wiederhergestellt nach {}": "{} file(s) restored to {}",
    "{} Datei(en), die das Backup nicht kennt, liegen jetzt in {}": "{} file(s) the backup doesn't know are now in {}",
    "Nichts aufzuräumen.": "Nothing to clean up.",
    "{} Backup(s) gelöscht, {:.1f} MB frei.": "{} backup(s) deleted, {:.1f} MB freed.",
    "GitHub ist gerade nicht erreichbar: {}": "GitHub cannot be reached right now: {}",
    "Neue Version {}: {}": "New version {}: {}",
    "Entpacken und den Inhalt über den alten Programmordner kopieren.":
        "Unpack it and copy the contents over the old program folder.",
    'Herunterladen: py -3 main.py update --laden   (aus dem Quellcode aktualisierst du mit "git pull")':
        'Download: py -3 main.py update --download   (from source code you update with "git pull")',
    "Heruntergeladen: {}": "Downloaded: {}",
    "Achtung: {} gibt es nicht – bitte später in config.json korrigieren.":
        "Warning: {} does not exist – please correct it in config.json later.",
    "Keine Installation gefunden – Pfad von Hand eingeben oder mit '-' überspringen.":
        "No installation found – enter the path by hand or skip with '-'.",
    "Achtung: In {} liegt kein Data\\Client – das ist vermutlich nicht die Installation.":
        "Warning: {} has no Data\\Client – this is probably not the installation.",
    "Es wurde kein Entpacker gefunden. Empfehlung: 7-Zip installieren (winget install 7zip.7zip)":
        "No extractor found. Recommendation: install 7-Zip (winget install 7zip.7zip)",
    "Hinweis: Ohne 7-Zip lassen sich viele 7z-Archive nicht öffnen (UnRAR kann nur RAR, das\n   Windows-tar keine LZMA-Komprimierung). Empfehlung: winget install 7zip.7zip":
        "Note: without 7-Zip many 7z archives can't be opened (UnRAR only does RAR, the\n   Windows tar can't do LZMA compression). Recommendation: winget install 7zip.7zip",
    'Neue config.json angelegt. Tipp: Mit "py -3 main.py setup" richtest du SimVault ein (Ordner, Entpacker für RAR/7z, Laufwerke).':
        'New config.json created. Tip: "py -3 main.py setup" sets up SimVault (folders, extractor for RAR/7z, drives).',
    "(nicht gesetzt)": "(not set)", "aus": "off", "RAR/7z werden übersprungen": "RAR/7z are skipped",
    "ja": "yes", "nein": "no",
    "{}/{} Dateien": "{}/{} files",
    "Fehlende CC: {} verschiedene Teile/Objekte": "Missing CC: {} different parts/objects",
    "Fehlende CC: keine gefunden": "Missing CC: none found",
    "[{}] {}: {} Datei(en)": "[{}] {}: {} file(s)",
    "für: {}": "for: {}",
    "Zurückholen ohne neue Suche: py -3 main.py restore   (einzelne Funde auslassen: --ohne WickedWhims)":
        "Restore without a new search: py -3 main.py restore   (leave out single finds: --skip WickedWhims)",
    "{} Datei(en) verschoben nach {}": "{} file(s) moved to {}",
    "{} veraltete Doppel aus {} entfernt": "{} outdated duplicates removed from {}",
    "Nichts davon lässt sich reparieren – die Dateien neu herunterladen.":
        "None of them can be repaired – download the files again.",
    ", {} vorhandene nicht angefasst": ", {} existing ones left alone",
    "{} Backup(s) würden gelöscht – ausführen mit: py -3 main.py backup cleanup --ausfuehren":
        "{} backup(s) would be deleted – run with: py -3 main.py backup cleanup --apply",
    "Datei nicht gefunden: {}": "File not found: {}",
    "Pfad zum Entpacker": "Path to the extractor",
    "Bibliotheks-Einträge mit fehlender CC: {}": "Library entries with missing CC: {}",
    " von {}": " by {}",
    "repariert": "repaired", "nicht geklappt": "failed",
    "{}: nicht heruntergeladen – {}": "{}: not downloaded – {}",
    "Nicht nutzbar – es wird automatisch gesucht.": "Not usable – searching automatically.",
    "{:>3} fehlend  {}{}": "{:>3} missing  {}{}",
    " und ": " and ",

    # Hilfe der Kommandozeile
    "SimVault – Sims 4 CC-Analyse und Backup": "SimVault – Sims 4 CC analysis and backup",
    "Pfad zur config.json": "path to config.json",
    "Sprache der Ausgabe (Standard: aus config.json)": "output language (default: from config.json)",
    "ausführliche Ausgabe": "verbose output",
    "Mods mit Spielständen/Bibliothek abgleichen (Standard)": "compare mods with savegames/library (default)",
    "bestimmte Spielstand-Datei(en)": "specific savegame file(s)",
    "alle Spielstände statt nur den neuesten": "all savegames instead of only the newest",
    "Bibliothek (Tray) nicht einbeziehen": "don't include the library (Tray)",
    "keine Suche nach fehlender CC": "no search for missing CC",
    "nur den Mods-Ordner prüfen": "check the Mods folder only",
    "Backup von Mods oder Spielständen; list / restore NAME / cleanup":
        "backup of mods or savegames; list / restore NAME / cleanup",
    "bei restore: Name des Backups (siehe backup list)": "for restore: name of the backup (see backup list)",
    "restore: vorhandene Dateien nicht überschreiben": "restore: don't overwrite existing files",
    "restore: Ordner genau auf den Backup-Stand bringen (Übriges wird beiseitegelegt)":
        "restore: bring the folder exactly to the backup state (anything else is set aside)",
    "cleanup: wirklich löschen (sonst nur anzeigen)": "cleanup: really delete (otherwise only show)",
    "Dateien (relativ zum Ordner) für selective": "files (relative to the folder) for selective",
    "fehlende CC auf dem PC suchen (Ordner und ZIP-Archive)": "search the PC for missing CC (folders and ZIP archives)",
    "Suchordner (Standard: Downloads, Desktop, alte Mods-Ordner, Mod-Manager … und alle weiteren Laufwerke)":
        "search folders (default: Downloads, Desktop, old Mods folders, mod managers … and all other drives)",
    "gefundene Pakete nach Mods/SimVault_wiederhergestellt kopieren":
        "copy found packages to Mods/SimVault_wiederhergestellt",
    "auch das komplette Systemlaufwerk C: durchsuchen (dauert länger)":
        "also search the whole system drive C: (takes longer)",
    "nur die Ordner durchsuchen, keine weiteren Laufwerke (D:, E: …)":
        "only search the folders, no other drives (D:, E: …)",
    "bei --restore den Mods-Ordner vorher nicht sichern": "with --restore, don't back up the Mods folder first",
    "beim Zurückholen Funde auslassen, deren Datei/Fundort diesen Text enthält":
        "when restoring, leave out finds whose file/location contains this text",
    "Funde aus dem letzten Suchbericht in den Mods-Ordner zurückholen":
        "restore finds from the last search report into the Mods folder",
    "Funde auslassen, deren Datei/Fundort TEXT enthält": "leave out finds whose file/location contains TEXT",
    "bestimmter Bericht (.json) statt des neuesten": "specific report (.json) instead of the newest",
    "Mods-Ordner vorher nicht sichern": "don't back up the Mods folder first",
    "Konflikte genau prüfen: gleich oder unterschiedlich, genutzt oder nicht":
        "check conflicts closely: identical or different, used or not",
    "überflüssige Dateien (stecken komplett in anderen) aus dem Mods-Ordner aussortieren":
        "move redundant files (fully contained in others) out of the Mods folder",
    "CC und Spielstände auf Schäden prüfen und reparieren": "check CC and savegames for damage and repair them",
    "jede Ressource entpacken (findet mehr, dauert länger)": "unpack every resource (finds more, takes longer)",
    "reparieren, was sich sicher reparieren lässt": "repair what can be repaired safely",
    "nach einer neueren SimVault-Version suchen": "look for a newer SimVault version",
    "das neue Release (ZIP) herunterladen": "download the new release (ZIP)",
    "Verbindung zur Datenbank prüfen (SQLite, MySQL/MariaDB, PostgreSQL)":
        "test the database connection (SQLite, MySQL/MariaDB, PostgreSQL)",
    "heruntergeladene CC installieren (Datei, Archiv oder URL)": "install downloaded CC (file, archive or URL)",
    "DATEI": "FILE",
    ".package, .ts4script, Bibliotheks-Datei, ZIP/RAR/7z oder URL":
        ".package, .ts4script, library file, ZIP/RAR/7z or URL",
    "einrichten: Ordner, Entpacker für RAR/7z, Laufwerke": "set up: folders, extractor for RAR/7z, drives",
    "verwendete Pfade anzeigen": "show the paths in use",
}

EN_REPORT = {}

# Changelog

Neue Einträge kommen oben unter `## [Unveröffentlicht]`. Beim Release wird der Abschnitt
der jeweiligen Version (z. B. `## [0.6.0]`) automatisch in die Release-Beschreibung übernommen,
zusammen mit der Liste aller Commits seit dem letzten Release.

## [Unveröffentlicht]

### Neu
- Konfliktprüfung: Überschneidungen im Mods-Ordner werden inhaltlich verglichen und eingeordnet (Doppelt, Überschneidung, Konflikt, Überschreibung), mit Spielständen und Bibliothek gegengeprüft und mit einer Empfehlung versehen. Neue Seite „Konflikte“ und Befehl `conflicts`.
- Bei echten Konflikten schaut SimVault in die CAS-Teile: neueres CAS-Format = aktualisierte Fassung, unterschiedliche Namen unter einer ID = zwei CC, die sich verdecken, sonst Variante oder anders gespeicherte Kopie.
- „Aufräumen“ löst auf, was sicher geht: überflüssige Dateien (stecken komplett und identisch in anderen) wandern nach `SimVault_aussortiert` (nicht gelöscht), veraltete Doppel werden aus dem betroffenen Paket entfernt (Original im Backup-Ordner).
- Spielordner wird automatisch gefunden (EA App/Origin, Steam, Epic, alle Laufwerke) und zur Auswahl vorgeschlagen: beim ersten Start, in den Einstellungen („Automatisch suchen“) und in `setup`.
- Reparatur: prüft CC und Spielstände; repariert falsch benannte Archive, Pakete mit einzelnen kaputten Ressourcen und Spielstände (letzte intakte Fassung des Spiels). Originale werden vorher gesichert. Neue Seite „Reparatur“ und Befehl `repair`.

- Backups wiederherstellen: Voll-Backup, Delta (letztes Voll-Backup plus alle Deltas bis zum gewählten), Auswahl und die Originale aus Reparatur/Konflikt-Aufräumen – wahlweise ersetzen, nur Fehlendes ergänzen oder genau auf Backup-Stand bringen (Übriges wird beiseitegelegt). Befehle `backup list` und `backup restore`.
- Alte Backups aufräumen nach Regel (Anzahl Voll-Backups je Ordner, Alter in Tagen; das neueste bleibt immer) – auf Knopfdruck oder automatisch nach jedem Backup. Befehl `backup cleanup`.
- Auto-Updater: sucht beim Start auf GitHub nach einer neuen Version, zeigt den Changelog, lädt herunter und tauscht das Programm nach dem Beenden aus. Befehl `update`.
- Vorschaubilder der Bibliothek: Haushalte mit fehlender CC zeigen ihr Bild – im Programm und im HTML-Bericht.
- Eigenes Branding: Programmname und Logo für Fenster und Berichte.
- Websuche mit eingebautem Browser: Quellen und CC-Links aus Bibliotheks-Haushalten öffnen sich im Programm; Downloads werden abgefangen, entpackt (ZIP/RAR/7z, auch verschachtelt) und gleich installiert – Pakete nach `Mods\SimVault_heruntergeladen`, Script-Mods eine Ebene tief, Sims/Häuser in die Bibliothek. Schon Installiertes und Kaputtes wird übersprungen, nichts überschrieben. Befehl `install` (Datei, Archiv oder URL).
- Trefferlisten mit Vorschaubild für Quellen, die echte Ergebnisse liefern (Voll-Quellen); Quellen können Seiten über den eingebauten Browser mit JavaScript laden lassen (`session.render`).
- Login-Manager: Anmelden im sichtbaren Browser-Fenster (inklusive Zwei-Faktor und Captchas von Hand); gespeichert werden nur die Cookies, verschlüsselt mit AES-256-GCM, Schlüssel durch das Windows-Benutzerkonto (DPAPI) geschützt. Der Browser selbst schreibt keine Cookies auf die Platte.
- Datenbank-Erweiterung: neben SQLite auch MySQL/MariaDB und PostgreSQL (Treiber selbst installieren), Befehl `db` prüft die Verbindung.
- Bibliothek: Grundstücke und Räume (.blueprint/.room) werden entschlüsselt – Snappy-komprimiert, darin jedes platzierte Objekt mit seiner Objektdefinition. Fehlende CC-Objekte erscheinen unter dem Grundstück bzw. Raum, platzierte CC zählt als „genutzt“.
- Trefferlisten für LoversLab (nur Sims-4-Dateien, eine Abfrage pro Suche wegen der Suchsperre der Seite) und SexySims (Dateien direkt mit der Anmeldung) – beide brauchen eine Anmeldung unter „Quellen“. Ohne Anmeldung gibt es einen Hinweis statt Treffern.
- Weitere Trefferlisten: Sims Finds, Tumblr (mit den Download-Links aus dem Beitrag, echte Datei-Hoster zuerst), Sims 4 Updates, The Sims Catalog (gemeinsamer WordPress-Leser) und NewSea (keine eigene Suche – der Sims-4-Katalog wird einmal pro Woche eingelesen und lokal durchsucht, Adresse jetzt richtig über http; freie Frisuren ohne Konto, Donate-Frisuren nach Anmeldung unter „Quellen“). Neu als Such-Links: Simsworkshop (Cloudflare-Prüfung) und Around the Sims (keine eigene Suche).
- Echte Trefferlisten für The Sims Resource, CurseForge und ModTheSims (Titel, Bild, Ersteller, Beschreibung). ModTheSims-Dateien lädt SimVault direkt (alle Dateien eines Downloads); bei TSR und CurseForge öffnet sich die Download-Seite im eingebauten Browser, die Datei wird danach automatisch installiert. Blockt eine Seite einfache Abrufe, holt sie der eingebaute Browser.
- Oberfläche auf Deutsch und Englisch (Einstellungen → Sprache, „automatisch“ = Windows-Sprache).

### Bugfixes
- Kommandozeile stürzte unter Windows ab, wenn die Ausgabe umgeleitet wurde (Zeichen „→“).
- Test für Suchorte schlug auf Rechnern mit weiteren Laufwerken fehl.
- Wiederherstellen legt keine doppelte CC mehr an: Funde, deren Teile schon im Mods-Ordner sind oder von einer anderen Fund-Datei mitgebracht werden, werden übersprungen; bei Gleichstand gewinnt das kleinere Einzelpaket statt eines großen Sets.
- „Könnte Sims-Inhalte enthalten“ ist nicht mehr so großzügig – z. B. Mass-Effect-Mods in einem Ordner „Mods“ landen nicht mehr in der Sims-Liste.
- Nach einer Suche (`find`) steht im Bericht wieder bei jeder Mod, ob sie genutzt wird.

## [0.5.0] – 2026-11-14

### Neu
- Eigenes Programmfenster (Qt/PySide6): Übersicht, Mods mit Vorschaubildern, Fehlende CC, Fundgrube, Backup, Quellen, Einstellungen.
- Fehlende CC erkennen: in Spielständen und in der Bibliothek (Tray-Haushalte), mit Körperteil/Slot und Ersteller.
- Fundgrube: durchsucht alle Laufwerke, auch in ZIP-, RAR- und 7z-Archiven (auch verschachtelt), und stellt Funde in den Mods-Ordner wieder her.
- Mods-Ordner wird vor jeder Wiederherstellung automatisch als ZIP gesichert.
- Quellen als Erweiterungen: Webseiten lassen sich als .json- oder .py-Datei im Ordner `plugins` ergänzen.
- Einrichtung: Entpacker (7-Zip, UnRAR, Windows-tar) frei wählbar.
- Berichte als HTML, CSV, JSON, Markdown und SQLite.
- Windows-Build als fertiges Programm (SimVault.exe) über GitHub Actions, Release per Knopfdruck.

### Verbessert
- Temp-Speicher wird sofort wieder freigegeben, wenn ein Archiv keine CC enthält.
- Verständliche Gründe, wenn ein Archiv nicht geöffnet werden kann; falsch benannte Archive werden am Inhalt erkannt.
- Wiederherstellen ohne neue Suche, mit Ausweichen auf andere Fundorte.

### Bugfixes
- Datum von Bibliotheks-Einträgen war um einen Tag verschoben.
- Falscher Dateiname bei Funden in verschachtelten Archiven.
- Temp-Ordner lief bei Treffern in großen Archiven voll.

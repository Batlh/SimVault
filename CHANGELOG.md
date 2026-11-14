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
- Eigenes Branding: Programmname und Logo für Fenster und Berichte.

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

# Changelog

Neue Einträge kommen oben unter `## [Unveröffentlicht]`. Beim Release wird der Abschnitt
der jeweiligen Version (z. B. `## [0.6.0]`) automatisch in die Release-Beschreibung übernommen,
zusammen mit der Liste aller Commits seit dem letzten Release.

## [Unveröffentlicht]

### Bugfixes
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

# Dateiformate – was SimVault liest

Zusammenfassung dessen, was an echten Dateien herausgefunden und im Code umgesetzt ist. Die genauen Stellen
stehen jeweils in den Kommentaren der genannten Module.

## DBPF 2.x – `.package`, `.save`, viele Bibliotheks-Dateien

`simvault/analysis/dbpf.py`

- 96 Byte Kopf: Kennung `DBPF`, Version 2.1, Anzahl, Position und Größe des Index.
- Danach die Ressourcen, roh oder komprimiert (zlib bzw. RefPack/QFS), am Ende der Index.
- Index je Ressource: Typ, Gruppe, Instanz (64 Bit), Position, Größe (oberstes Bit = „erweitert“),
  entpackte Größe, Kompressionsart.
- Für fast alle Auswertungen reicht der Index; Ressourcen werden nur bei Bedarf entpackt.
- Wichtige Typen: `0x034AEECB` CAS-Teil (CASP), `0xC0DB5AE7` Objektdefinition (OBJD),
  `0x319E4F1D` Katalogobjekt (COBJ), `0x0000000D` Spielstand-Daten.
- `rebuild_package()` schreibt ein Paket ohne bestimmte Ressourcen neu (Reparatur, Konflikte auflösen).

## Spielstände – `.save`

`simvault/analysis/missing_cc.py`, `savegame_analyzer.py`

- Ein DBPF-Paket; die Spielstand-Daten (`0x0000000D`) sind Protobuf ohne bekanntes Schema – gelesen wird
  mit einem kleinen eigenen Leser (`iter_fields`) an festen Feldpfaden:
  - Feld 6 = Sims (Vor-/Nachname, Outfits mit CAS-Teilen als gepackte 64-Bit-Liste, Inventar)
  - Feld 5 = Haushalte, Feld 7 = Zonen (Grundstücke), Feld 8 = weitere Objekte
- Zonen (`0x00000006`, Instanz = Zonen-ID) enthalten die platzierten Objekte.
- `.save.ver0` … `.ver4` sind ältere Fassungen – daraus repariert `repair.py` beschädigte Spielstände.

## Bibliothek (Tray)

`simvault/analysis/missing_cc.py`, `thumbnails.py`

- `.trayitem`: Name, Beschreibung, Ersteller (Galerie-ID) des Eintrags.
- `.householdbinary`: 8 Byte Kopf, dann Protobuf mit den Sims wie im Spielstand.
- `.blueprint` (Grundstück) / `.room` (Raum):
  - 8 Byte Kopf (u32 Version, u32 Länge des Rests), danach Snappy-komprimiert (Varint-Länge + Snappy-Strom,
    entpackt mit `dbpf.snappy_decompress`).
  - Entpackt: u32 Kennung `0xFEA1BAAD`, u32 (1/2 …), u32 Länge des Protobuf-Teils, dann Protobuf –
    Feld 2 = platzierte Objekte (1 Objekt-ID, 6 Elternobjekt, 15 Objektdefinition).
  - Dahinter ein Binärteil `LDNB` (Gelände, Wände, Böden) – in den geprüften Dateien ohne CC-Verweise.
- Vorschaubilder: `.hhi`, `.bpi`, `.rmi`, `.sgi`.

## Woran fehlende CC erkannt wird

- EA-Inhalte haben IDs unter 2^32, Creator-CC nutzt 64-Bit-Hashes (≥ 2^32).
- Eine solche ID an einer CAS- oder Objekt-Stelle, die in keinem installierten Paket steckt, fehlt.
- Ist der Spielordner bekannt, werden zusätzlich alle IDs aus dem Spiel ausgeschlossen.

## Konflikte

`simvault/analysis/conflicts.py`

- Gleiche Ressource (Typ, Gruppe, Instanz) in mehreren Paketen: Doppelt (identisch), Überschneidung,
  Konflikt (unterschiedlich) oder Überschreibung.
- Bei CAS-Teilen entscheidet die Formatversion im CASP, welche Fassung neuer ist.

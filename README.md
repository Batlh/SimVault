# SimVault

🛡️ **SimVault** — Sims 4 Savegame and Custom Content Analyzer, Backup and Recovery Tool.

SimVault reads your Mods folder and your savegames directly (DBPF format) and tells you
which Custom Content you actually use, what is broken, and what can go.

---

## 🚀 Features (working)

- 📂 **Mod Folder Scanner** — reads every `.package` via its DBPF index and sorts it into
  CAS, Build/Buy objects, tuning/other and script mods. Detects:
  - `.ts4script` nested deeper than 1 subfolder and `.package` deeper than 5 (the game won't load them)
  - broken, truncated or empty files and invalid script archives
  - unpacked archives (`.zip/.rar/.7z`) left in the Mods folder
  - identical duplicate files
  - the same CAS/object resource in several packages (e.g. installed loose *and* in a merge)

- 🔍 **Savegame & Library Analyzer** — unpacks `.save` files (zlib and RefPack) and Tray files
  and matches the IDs they contain against your installed CC:
  - **used** — appears in a savegame or in the library (households, lots, rooms)
  - **unused** — CAS/object CC that is used nowhere → cleanup candidate
  - **not provable** — tuning/gameplay mods that aren't always stored in the save
  - **not checkable** — script mods

- 📄 **Report Generator** — HTML (sortable, filterable, no internet needed), CSV (Excel-ready),
  JSON and Markdown, plus a local SQLite database with every scan.

- 🌐 **CC Search Links** — search links for TSR, CurseForge, ModTheSims, Tumblr, Patreon,
  LoversLab and Google, generated from the file name (e.g. for broken files).

- 🗜️ **Backup Manager** — Full (ZIP), Delta (only changed files, SHA256) and Selective backups
  of the Mods or saves folder.

- ⚙️ **Config** — `config.json`, created on first start. The Sims 4 folder is found automatically
  (also localized names like "Die Sims 4" and Documents inside OneDrive).

---

## 🛠️ Usage

Requires Python 3.8+. No extra packages needed.

```bash
git clone https://github.com/Batlh/SimVault.git
cd SimVault
python main.py                      # Mods + newest savegame + library, writes reports to ./reports
python main.py analyze --all-saves  # include all savegames
python main.py analyze --save "C:\...\saves\Slot_00000002.save"
python main.py scan                 # Mods folder check only
python main.py backup mods          # backup (mode from config.json)
python main.py backup saves --mode delta
python main.py config               # show detected paths
```

SimVault only **reads** your Sims folders. Nothing is changed or deleted there.

Run the tests: `python -m unittest discover -s tests -v`

---

## 📝 Planned

- **Missing CC detection** (used in a savegame but not installed) — needs the savegame schema
  and an index of the game's own content
- GUI
- Real search results via a browser with manual login
- Restore function for backups

---

## 📜 License

MIT — see [LICENSE](LICENSE).

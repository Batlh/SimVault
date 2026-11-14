# SimVault

🛡️ **SimVault** — The Ultimate Sims 4 Savegame and Custom Content Analyzer, Backup, and Recovery Tool with Modern Web and Database Integration.

SimVault reads your Mods folder and your savegames directly (DBPF format) and tells you
which Custom Content you actually use, what is broken, and what can go.

---

## 💾 Download & Start

**Windows program:** download `SimVault-Windows.zip` from
[Releases](https://github.com/Batlh/SimVault/releases), unzip it anywhere and start **`SimVault.exe`** —
no Python needed. Settings, reports and backups are stored in `%APPDATA%\SimVault`
(or next to the program if a `config.json` is placed there).

**From source:** `pip install -r requirements-gui.txt` and `py -3 simvault_gui.py`
(the command line `main.py` works without any extra packages).

---

## 🚀 Features (working)

- 🖥️ **Program window (Qt/PySide6)** — overview, mods table with filter and **preview images from the
  packages** (with transparency), missing CC with library households, lots and rooms, CC search with restore, backups,
  sources and settings — long tasks run in the background with progress and a cancel button.

- 🧭 **Sources & extensions** — all web sources (TSR, CurseForge, ModTheSims, Tumblr, Patreon, LoversLab,
  SexySims, NewSea, Google) are plugins. New sites are added as a small `.json` file (search link, no
  programming) or a `.py` file (real results, optionally with login) in the `plugins` folder — see
  [plugins/README.md](plugins/README.md). Sources can be switched on/off in the program.

- 📂 **Mod Folder Scanner** — reads every `.package` via its DBPF index and sorts it into
  CAS, Build/Buy objects, tuning/other and script mods. Detects:
  - `.ts4script` nested deeper than 1 subfolder and `.package` deeper than 5 (the game won't load them)
  - broken, truncated or empty files and invalid script archives
  - unpacked archives (`.zip/.rar/.7z`) left in the Mods folder
  - identical duplicate files
  - the same CAS/object resource in several packages (e.g. installed loose *and* in a merge) —
    checked in detail by the conflict check below

- ⚖️ **Conflict check** — an overlap is not automatically a problem, so SimVault compares the actual
  content of the shared resources and cross-checks with your savegames and library:
  - **Doppelt** (duplicate) — content is byte-identical and one file is completely contained in others → it can go
  - **Überschneidung** (overlap) — shared content is identical, but each file has parts of its own → harmless, keep all
  - **Konflikt** — same ID, *different* content → the game uses only one. SimVault looks into the CAS parts:
    same item in a newer CAS format = the updated version wins; different item names under one ID = two CCs
    hiding each other; same name and format = a variant or re-saved copy. You also see whether the parts are
    in use (and in which saves)
  - **Überschreibung** (override) — several mods replace the same original game item (default replacement)

  What can be resolved safely is done with one click ("Aufräumen" / `python main.py conflicts --aufraeumen`):
  completely redundant files are moved to `SimVault_aussortiert` next to the Mods folder (nothing is deleted),
  and where an updated version exists, the outdated copies are removed from the other package — the rest of
  that package stays, its original goes to the backup folder. Everything else is explained, not touched.
  After restoring found CC, the same check shows whether restored files overlap with installed ones.

- 🩺 **Repair** — checks every CC file and savegame and repairs what can be repaired safely:
  - an archive (ZIP/RAR/7z) that was saved with the extension `.package` → unpacked, the real packages are put next to it
  - single damaged resources inside an otherwise readable package → the package is rewritten without them
    (saves the rest of a merge; "thorough" mode unpacks every resource to find damage in the middle of a file)
  - a broken savegame → the newest intact older version the game keeps (`.save.ver0`–`.ver4`) is brought back
  - **not** repairable, and SimVault says so: empty files, truncated downloads, a saved web page instead of
    the file — the data simply is not there; these have to be downloaded again

  The original always goes to the backup folder first (`reparatur_<time>`).

- 🔍 **Savegame & Library Analyzer** — unpacks `.save` files (zlib and RefPack) and Tray files
  and matches the IDs they contain against your installed CC:
  - **used** — appears in a savegame or in the library (households, lots, rooms)
  - **unused** — CAS/object CC that is used nowhere → cleanup candidate
  - **not provable** — tuning/gameplay mods that aren't always stored in the save
  - **not checkable** — script mods

- 🏠 **Library lots & rooms** — `.blueprint`/`.room` files are decoded: an 8-byte header, then a
  **Snappy**-compressed block (`0xFEA1BAAD`, protobuf with every placed object — field 15 is the object
  definition — followed by the `LDNB` build data). Placed CC objects count as "used", missing ones show up
  under the lot or room in *Missing CC*.

- 🧩 **Missing CC Detection** — finds CAS parts and objects that are used in savegames or in
  saved library households, **lots and rooms** but are no longer installed, and shows who uses them
  (Sim names, households, lots, library entries) and what kind of part it is
  (hair, top, shoes, lipstick … from the outfit's body-type slot). EA content is recognized by
  its smaller IDs; if the game folder is found (or set as `game_folder`), all game IDs are excluded as well.
  The game installation is **found automatically** (registry entries of EA App/Origin, Steam libraries, Epic,
  usual folders on all drives, optional deeper drive search) and offered for selection — on first start of the
  program, with "Automatisch suchen" in the settings and in `setup`.
  For library households it also shows the **preview picture** (decoded from the Tray's `.hhi`/`.bpi`/`.rmi`
  files — in the program and embedded in the HTML report), the Gallery creator, description, CC links found in the
  description and a web search link — the best lead to the original CC list.

- 🔦 **CC Finder ("Fundgrube")** — `python main.py find` searches your PC for the missing CC:
  Downloads, old Mods folders (e.g. an English "The Sims 4" folder next to "Die Sims 4"),
  Sims 4 Mod Manager and CurseForge folders, **all other drives** (D:, E:, USB sticks; system folders
  skipped), or any folder you name — including **`.zip`, `.rar` and `.7z` archives** (also nested ones).
  RAR/7z are briefly unpacked to a temp folder (only packages and nested archives), searched and cleaned up,
  using 7-Zip, WinRAR (UnRAR) or the `tar` built into Windows 10/11 — choose which in `setup`.
  Archives with a wrong extension (e.g. a RAR named `.zip`) are recognized by their content.
  Password-protected, broken or very large archives are reported with a clear reason; those that look
  Sims-related are listed first, the rest is collapsed.
  Disk space: every archive is deleted from the temp folder right after it was checked — found or not.
  Only with `--restore` the found packages themselves stay until they are copied. Before unpacking,
  free space is checked; leftovers of aborted runs are removed on the next start; ZIPs are read streamed.
  The temp folder can be moved to another drive with `temp_folder` in `config.json`.
  `--ganzer-pc` also scans the whole C: drive.
  `python main.py restore` copies the finds of the last search to `Mods/SimVault_wiederhergestellt` without
  searching again — also out of nested archives (ZIP in ZIP, RAR in ZIP …); if one location fails, the
  other locations of the same file are tried. Before that, the Mods folder is backed up as a ZIP
  automatically (skip with `--ohne-backup`). Nothing is overwritten; `--ohne TEXT` leaves out finds whose
  name or location contains TEXT. (`find --restore` searches and restores in one go.) The same file found in several places
  is listed once, with all locations. Finds whose parts are already installed, or are covered by another
  find, are not copied — so restoring does not create duplicate CC.

- 📄 **Report Generator** — HTML (sortable, filterable, no internet needed), CSV (Excel-ready),
  JSON and Markdown, plus a local SQLite database with every scan.

- 🌐 **CC Search Links** — search links for TSR, CurseForge, ModTheSims, Tumblr, Patreon,
  LoversLab, SexySims, NewSea and Google, generated from the file name (e.g. for broken files).

- 🗜️ **Backup Manager & Recovery** — Full (ZIP), Delta (only changed files, SHA256) and Selective backups
  of the Mods or saves folder. **Restore** with one click: a delta automatically plays back the last full
  backup plus all deltas up to the chosen one; choose between "replace existing files", "only add what is
  missing" and "bring the folder exactly to the backup state" (files the backup does not know are put aside,
  not deleted). The originals saved by Repair and by the conflict clean-up can be restored the same way.
  **Old backups are cleaned up** by rule (keep the last N full backups per folder, delete older than N days;
  the newest full backup always stays) — on demand or automatically after every backup.

- 🔄 **Auto-Updater** — checks GitHub for a newer release on start (can be switched off), shows the changelog,
  downloads the new version and swaps the program after it closes; settings, reports, backups and your own
  extensions stay. From source it only tells you (update with `git pull`). Nothing is sent anywhere.

- 🎨 **Custom Branding** — your own program name and logo for the window and the reports (`branding` in
  `config.json` or in the settings).

- ⚙️ **Config Manager & Setup** — `python main.py setup` asks for the Sims folder, game folder,
  the unpacker for RAR/7z (found ones, own path or none) and whether to search other drives.
  Everything is stored in `config.json`, created on first start.
  The Sims 4 folder is found automatically (also localized names like "Die Sims 4" and Documents inside OneDrive).

---

## 🗺️ Roadmap (planned)

- 🌐 **More result lists** — The Sims Resource, CurseForge and ModTheSims deliver real result lists (done);
  Tumblr, Patreon, LoversLab and SexySims only show results when logged in and stay search links that open in
  the built-in browser (downloads there are still installed automatically). More sites can be added as full
  sources in `plugins/` (see `plugins/_beispiel_vollquelle.py`).
- 🛡️ **Captcha automation** — captchas are solved by hand in the built-in browser (done); automation optional later
- 📱 **Mobile App** for remote analysis
- 🌍 **More languages** — German and English are in; reports and the command line are still German only

---

## 🌐 Web search, logins & downloads

- **Built-in browser** (page *Web search*, Chromium via Qt WebEngine): every source button and every CC link
  from a library household opens there. Whatever you download in it lands in the download folder and is
  **unpacked and installed right away** (can be switched off): packages go to `Mods/SimVault_heruntergeladen/<name>/`,
  script mods to `Mods/SimVault_heruntergeladen/` (they only load one folder deep), library files (Sims, lots,
  rooms) to `Tray/`. ZIP, RAR and 7z (also nested) are unpacked. Already installed CC (all CAS parts are in the
  Mods folder, or the same file is already there) and broken files are skipped; nothing is ever overwritten.
- **Result lists** from **The Sims Resource, CurseForge and ModTheSims** (and any full source in `plugins/`):
  title, preview image, creator and description. ModTheSims files are downloaded directly (every file of the
  download); TSR and CurseForge start their download on the site (waiting time / countdown), so SimVault opens
  that page in the built-in browser and installs the file as soon as it arrives. *Download and install* fetches the file — if the site answers with a page instead (login, captcha,
  waiting time), it is opened in the built-in browser. Full sources can use `session.render(url)` to get the
  HTML of JavaScript-heavy pages from the built-in browser (headless browser support without Selenium).
- **Secure login manager**: *Sources → Log in …* opens the site's login page in the built-in browser — 2FA codes
  and captchas are entered there by you. *Save login* stores only the cookies afterwards, **AES-256-GCM encrypted**
  (`%APPDATA%\SimVault\logins.bin`); the key is protected by the Windows user account (DPAPI), decrypted only in
  RAM. The browser itself runs "off the record" and writes no cookies to disk. Passwords are never stored.
- Command line: `python main.py install <file, archive or URL>` installs the same way.

## 🗄️ Database

Every analysis is also stored in a database: **SQLite** by default (`simvault_data.db`), or **MySQL/MariaDB** /
**PostgreSQL** for advanced users — set `"type": "mysql"` or `"postgresql"` in the `database` section of
`config.json` and install the driver (`pip install pymysql` or `pip install "psycopg[binary]"`). The password can
come from the environment variable `SIMVAULT_DB_PASSWORD` instead of the file. `python main.py db` checks the
connection and creates the tables (`scans`, `mod_files`, `issues`, `missing_cc`).

## 🌍 Language

The program window speaks **German and English** — *Settings → Language* (automatic = Windows language).
Reports and the command line are German.

## 🛠️ Command line

1. Clone the repository:
    ```bash
    git clone https://github.com/Batlh/SimVault.git
    cd SimVault
    ```

2. Run SimVault (no extra packages needed):
    ```bash
    python main.py                      # Mods + newest savegame + library, writes reports to ./reports
    python main.py analyze --all-saves  # include all savegames
    python main.py analyze --save "C:\...\saves\Slot_00000002.save"
    python main.py scan                 # Mods folder check only
    python main.py find                 # search your PC for missing CC (Downloads, old Mods folders …)
    python main.py find "D:\Old Mods" --restore   # search a folder and copy finds into Mods
    python main.py find --ganzer-pc     # also scan the whole C: drive
    python main.py restore --ohne WickedWhims   # copy the finds of the last search into Mods (no new search)
    python main.py conflicts            # check overlaps: identical or different, in use or not
    python main.py conflicts --aufraeumen   # move redundant files out, remove outdated copies (safe cases only)
    python main.py repair               # check CC files and savegames for damage
    python main.py repair --gruendlich --ausfuehren   # thorough check, repair what can be repaired safely
    python main.py install "Kijiko Set.zip"   # install downloaded CC (file, archive or URL), no duplicates
    python main.py db                   # check the database connection (SQLite, MySQL/MariaDB, PostgreSQL)
    python main.py backup mods          # backup (mode from config.json)
    python main.py backup saves --mode delta
    python main.py backup list          # show all backups
    python main.py backup restore Mods_backup_20261114_203000.zip   # play a backup back (--nur-fehlendes, --genau)
    python main.py backup cleanup       # show old backups that would be removed (--ausfuehren deletes them)
    python main.py update               # look for a newer SimVault version (--laden downloads it)
    python main.py setup                # set up: folders, RAR/7z unpacker, drives
    python main.py config               # show detected paths
    ```

SimVault only **reads** your Sims folders unless you ask for a change — and then nothing is ever deleted:
`find --restore`/`restore` copy found packages into the new subfolder `Mods/SimVault_wiederhergestellt`
(nothing is overwritten), `conflicts --aufraeumen` moves redundant files to `SimVault_aussortiert` and saves
the original of every package it changes, and `repair --ausfuehren` saves every original in the backup folder
before it touches a file.

Run the tests: `python -m unittest discover -s tests -v`

---

## 💻 Requirements

- Python 3.8+ (on Windows use `py -3 main.py …` if `python` starts Python 2)
- No database server required (uses local SQLite by default; MySQL/PostgreSQL optional with their driver)
- Program window from source: `pip install -r requirements-gui.txt` (PySide6 incl. Qt WebEngine, cryptography)
- Internet connection only for the web search, the built-in browser and update checks

---

## 📜 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

## 📬 Contributing

Pull requests are welcome!  
For major changes, please open an issue first to discuss what you would like to change.

Please make sure to update tests as appropriate.

---

## ⚡ SimVault will be:
> "The first real Sims 4 Savegame + CC Analyzer and Recovery Tool with Modern Web + DB Integration."

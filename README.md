# SimVault

🛡️ **SimVault** — The Ultimate Sims 4 Savegame and Custom Content Analyzer, Backup, and Recovery Tool with Modern Web and Database Integration.

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

- 🧩 **Missing CC Detection** — finds CAS parts and objects that are used in savegames or in
  saved library households but are no longer installed, and shows who uses them
  (Sim names, households, lots, library entries) and what kind of part it is
  (hair, top, shoes, lipstick … from the outfit's body-type slot). EA content is recognized by
  its smaller IDs; if the game folder is found (or set as `game_folder`), all game IDs are excluded as well.
  For library households it also shows the Gallery creator, description, CC links found in the
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
  other locations of the same file are tried. Nothing is overwritten; `--ohne TEXT` leaves out finds whose
  name or location contains TEXT. (`find --restore` searches and restores in one go.) The same file found in several places
  is listed once, with all locations.

- 📄 **Report Generator** — HTML (sortable, filterable, no internet needed), CSV (Excel-ready),
  JSON and Markdown, plus a local SQLite database with every scan.

- 🌐 **CC Search Links** — search links for TSR, CurseForge, ModTheSims, Tumblr, Patreon,
  LoversLab, SexySims, NewSea and Google, generated from the file name (e.g. for broken files).

- 🗜️ **Backup Manager** — Full (ZIP), Delta (only changed files, SHA256) and Selective backups
  of the Mods or saves folder.

- ⚙️ **Config Manager & Setup** — `python main.py setup` asks for the Sims folder, game folder,
  the unpacker for RAR/7z (found ones, own path or none) and whether to search other drives.
  Everything is stored in `config.json`, created on first start.
  The Sims 4 folder is found automatically (also localized names like "Die Sims 4" and Documents inside OneDrive).

---

## 🗺️ Roadmap (planned)

- 🔎 **Missing CC Detection for library lots & rooms** (`.blueprint`/`.room` use a different encoding)
- 🖼️ **Library thumbnails** in the report (`.hhi`/`.sgi` use an unknown image encoding)
- 🌐 **CC Search Engine** — real result lists (title, image, download link, description) instead of search links
  - fixed sources as core modules (TSR, CurseForge, ModTheSims, Tumblr, Patreon, LoversLab, SexySims, NewSea)
  - extensible plugin architecture for additional, user-defined sources
  - headless browser support (Selenium/Playwright)
  - automated download management
- 🔐 **Secure Login Manager** — manual login in a visible window with 2FA support;
  cookies stored **AES256-encrypted** and decrypted only in RAM at runtime (no plain-text cookies on disk)
- 🛡️ **Captcha Handling** — manual captcha solving via the visible login window (optional automation later)
- ♻️ **Recovery** — restore function for Full, Delta and Selective backups, automatic cleanup of old backups
- 🖥️ **GUI Interface** (Tkinter / PyQt / Web frontend)
- 📱 **Mobile App** for remote analysis
- 🔄 **Auto-Updater**
- 🌍 **Full Internationalization (i18n)**
- 🗄️ **Optional MySQL/PostgreSQL database plugin** for advanced users
- 🎨 **Custom Branding** (app name, logo)

---

## 🛠️ Installation & Usage

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
    python main.py backup mods          # backup (mode from config.json)
    python main.py backup saves --mode delta
    python main.py setup                # set up: folders, RAR/7z unpacker, drives
    python main.py config               # show detected paths
    ```

SimVault only **reads** your Sims folders. The only exception is `find --restore`, which copies
found packages into the new subfolder `Mods/SimVault_wiederhergestellt` — nothing is overwritten or deleted.

Run the tests: `python -m unittest discover -s tests -v`

---

## 💻 Requirements

- Python 3.8+ (on Windows use `py -3 main.py …` if `python` starts Python 2)
- No database server required (uses local SQLite by default)
- Internet connection only for opening the CC search links (and later the CC Search Engine)

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

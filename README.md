# SimVault

🛡️ **SimVault** — The Ultimate Sims 4 Savegame and Custom Content Analyzer, Backup, and Recovery Tool with Modern Web and Database Integration.

---

## 🚀 Features

- 🔍 **Savegame Analyzer**  
  Extracts used Custom Content (CC) IDs from Sims 4 savegames.

- 📂 **Mod Folder Scanner**  
  Scans installed Mods and Script files (`.package`, `.ts4script`).

- 🌐 **CC Search Engine**  
  Finds missing CC on major platforms like TSR, CurseForge, ModTheSims, Tumblr, Patreon, and more.

- 🔐 **Secure Login Manager**  
  Supports manual login with 2FA and AES256-encrypted cookie storage.

- 🛡️ **Captcha Handling**  
  Manual captcha solving via visible login window (future optional automation).

- 📄 **Report Generator**  
  Generates structured reports in HTML, CSV, JSON, and Markdown formats.  
  Also saves all data into a local SQLite database.

- 🗜️ **Backup Manager**  
  Backup entire savegames and Mods folder with Full, Delta, and Selective backup modes.

- ⚙️ **Config Manager**  
  Centralized configuration through a simple `config.json` file.

---

## 📝 Planned Features

- GUI Interface (Tkinter / PyQt / Web frontend)
- Mobile App for remote analysis
- Auto-Updater
- Full Internationalization (i18n)
- Optional MySQL/PostgreSQL database plugin for advanced users

---

## 🛠️ Installation

1. Clone the repository:
    ```bash
    git clone https://github.com/Batlh/SimVault.git
    cd SimVault
    ```

2. Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```

3. Run SimVault:
    ```bash
    python main.py
    ```

---

## 💻 Requirements

- Python 3.8+
- Internet connection (for CC Search)
- No database server required (uses local SQLite by default)

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


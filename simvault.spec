# PyInstaller-Bauanleitung für SimVault.exe (Windows)
# Bauen:  pip install -r requirements-gui.txt pyinstaller
#         pyinstaller --noconfirm simvault.spec
# Ergebnis: dist/SimVault/SimVault.exe (+ Ordner _internal). Der Ordner "plugins" gehört neben die .exe.

block_cipher = None

a = Analysis(
    ["simvault_gui.py"],
    pathex=["."],
    datas=[("assets/simvault.png", "assets")],
    hiddenimports=["simvault.web.sources.builtin", "simvault.web.sources.loader", "simvault.web.sources.base",
                   "simvault.web.sources.sites",
                   # Übergang für ältere Erweiterungen („from sources.base import Source“)
                   "sources",
                   # eingebauter Browser (Anmelden, Downloads, Seiten rendern) und verschlüsselte Anmeldungen
                   "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebChannel",
                   "cryptography.hazmat.primitives.ciphers.aead"],
    # Qt Quick/QML bleiben drin: der Browser (Qt WebEngine) braucht sie
    excludes=["tkinter", "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtCharts",
              "PySide6.QtDataVisualization"],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="SimVault",
    console=False,
    icon="assets/simvault.ico",
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name="SimVault")

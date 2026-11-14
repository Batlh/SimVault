# PyInstaller-Bauanleitung für SimVault.exe (Windows)
# Bauen:  pip install -r requirements-gui.txt pyinstaller
#         pyinstaller --noconfirm simvault.spec
# Ergebnis: dist/SimVault/SimVault.exe (+ Ordner _internal). Der Ordner "plugins" gehört neben die .exe.

block_cipher = None

a = Analysis(
    ["simvault_gui.py"],
    pathex=["."],
    datas=[("assets/simvault.png", "assets")],
    hiddenimports=["sources.builtin", "sources.loader", "sources.base"],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
              "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtCharts",
              "PySide6.QtDataVisualization", "PySide6.QtPdf"],
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

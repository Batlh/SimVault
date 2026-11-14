# Modul: gui/app.py – startet das Programmfenster

import sys
import logging


def _asset(name):
    """Pfad zu einer Datei in assets/ – auch in der gebauten .exe (PyInstaller)."""
    import os
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(base, "assets", name)
    return path if os.path.exists(path) else None


def main(argv=None):
    from PySide6.QtWidgets import QApplication
    from . import theme
    from .main_window import MainWindow

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    argv = list(sys.argv if argv is None else argv)
    config_path = None
    if "--config" in argv:
        config_path = argv[argv.index("--config") + 1]
    app = QApplication(argv)
    app.setApplicationName("SimVault")
    theme.apply(app)
    icon = _asset("simvault.png")
    if icon:
        from PySide6.QtGui import QIcon
        app.setWindowIcon(QIcon(icon))
    window = MainWindow(config_path, first_run=True)
    window.show()
    return app.exec()

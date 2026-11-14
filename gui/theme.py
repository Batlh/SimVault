# Modul: gui/theme.py – dunkles Erscheinungsbild für SimVault

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

ACCENT = "#2fb67c"        # Sims-Grün
ACCENT_DARK = "#23905f"
BG = "#1e2126"
BG_ALT = "#252930"
PANEL = "#2b3038"
TEXT = "#e6e8eb"
MUTED = "#9aa3ad"
WARN = "#e0a43a"
ERROR = "#e5534b"

STATUS_COLORS = {
    "genutzt": ACCENT,
    "ungenutzt": WARN,
    "defekt": ERROR,
    "nicht nachweisbar": MUTED,
    "nicht prüfbar": MUTED,
}

QSS = f"""
QWidget {{ color: {TEXT}; font-size: 10pt; }}
QMainWindow, QDialog {{ background: {BG}; }}
#Sidebar {{ background: {BG_ALT}; border: none; outline: none; padding-top: 8px; }}
#Sidebar::item {{ padding: 10px 16px; border-radius: 6px; margin: 2px 8px; }}
#Sidebar::item:selected {{ background: {PANEL}; color: {ACCENT}; }}
#Sidebar::item:hover {{ background: {PANEL}; }}
#AppTitle {{ font-size: 15pt; font-weight: 600; padding: 14px 16px 6px 16px; color: {ACCENT}; }}
#PageTitle {{ font-size: 16pt; font-weight: 600; }}
#Muted {{ color: {MUTED}; }}
#Card {{ background: {PANEL}; border-radius: 10px; }}
#CardValue {{ font-size: 20pt; font-weight: 600; }}
#CardLabel {{ color: {MUTED}; }}
QPushButton {{ background: {PANEL}; border: 1px solid #3a404a; border-radius: 6px; padding: 6px 14px; }}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton:disabled {{ color: #666; border-color: #333; }}
QPushButton#Primary {{ background: {ACCENT}; border: none; color: #0d1f16; font-weight: 600; }}
QPushButton#Primary:hover {{ background: {ACCENT_DARK}; }}
QPushButton#Primary:disabled {{ background: #3a4a42; color: #7a8a82; }}
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextBrowser {{
    background: {BG_ALT}; border: 1px solid #3a404a; border-radius: 6px; padding: 5px; selection-background-color: {ACCENT_DARK}; }}
QTableView, QTreeWidget, QListWidget {{
    background: {BG_ALT}; alternate-background-color: #2a2e35; border: 1px solid #343a43; border-radius: 6px;
    gridline-color: #343a43; selection-background-color: {ACCENT_DARK}; selection-color: white; }}
QHeaderView::section {{ background: {PANEL}; border: none; border-right: 1px solid #343a43; padding: 6px; font-weight: 600; }}
QTabWidget::pane {{ border: 1px solid #343a43; border-radius: 6px; top: -1px; }}
QTabBar::tab {{ background: {BG_ALT}; padding: 7px 16px; border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px; }}
QTabBar::tab:selected {{ background: {PANEL}; color: {ACCENT}; }}
QProgressBar {{ background: {BG_ALT}; border: 1px solid #343a43; border-radius: 5px; height: 10px; text-align: center; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 5px; }}
QStatusBar {{ background: {BG_ALT}; color: {MUTED}; }}
QGroupBox {{ border: 1px solid #343a43; border-radius: 8px; margin-top: 14px; padding-top: 10px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {MUTED}; }}
QCheckBox::indicator {{ width: 16px; height: 16px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: #3a404a; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QToolTip {{ background: {PANEL}; color: {TEXT}; border: 1px solid #3a404a; }}
"""


def apply(app: QApplication):
    app.setStyle("Fusion")
    palette = QPalette()
    for role, color in ((QPalette.Window, BG), (QPalette.WindowText, TEXT), (QPalette.Base, BG_ALT),
                        (QPalette.AlternateBase, "#2a2e35"), (QPalette.Text, TEXT), (QPalette.Button, PANEL),
                        (QPalette.ButtonText, TEXT), (QPalette.Highlight, ACCENT_DARK),
                        (QPalette.HighlightedText, "#ffffff"), (QPalette.Link, ACCENT),
                        (QPalette.ToolTipBase, PANEL), (QPalette.ToolTipText, TEXT),
                        (QPalette.PlaceholderText, MUTED)):
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    app.setStyleSheet(QSS)

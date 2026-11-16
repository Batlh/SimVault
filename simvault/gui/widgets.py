# Modul: simvault/gui/widgets.py – wiederverwendbare Bausteine

import os

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QImage, QPixmap
from PySide6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QVBoxLayout, QWidget)

from . import theme


def open_path(path):
    """Datei oder Ordner im Explorer öffnen."""
    if path and os.path.exists(path):
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))


def open_url(url):
    if url:
        QDesktopServices.openUrl(QUrl(url))


def page_header(title, subtitle=""):
    box = QWidget()
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 8)
    t = QLabel(title)
    t.setObjectName("PageTitle")
    lay.addWidget(t)
    if subtitle:
        s = QLabel(subtitle)
        s.setObjectName("Muted")
        s.setWordWrap(True)
        lay.addWidget(s)
    return box


class StatCard(QFrame):
    def __init__(self, label, value="–", color=None):
        super().__init__()
        self.setObjectName("Card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        self.value = QLabel(value)
        self.value.setObjectName("CardValue")
        if color:
            self.value.setStyleSheet(f"color: {color};")
        self.label = QLabel(label)
        self.label.setObjectName("CardLabel")
        lay.addWidget(self.value)
        lay.addWidget(self.label)

    def set(self, value):
        self.value.setText(str(value))


class PathEdit(QWidget):
    """Eingabefeld mit „Durchsuchen …“ für Ordner oder Dateien."""

    def __init__(self, folder=True, placeholder=""):
        super().__init__()
        self.folder = folder
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        button = QPushButton("Durchsuchen …")
        button.clicked.connect(self._browse)
        lay.addWidget(self.edit, 1)
        lay.addWidget(button)

    def _browse(self):
        start = self.edit.text() or os.path.expanduser("~")
        if self.folder:
            path = QFileDialog.getExistingDirectory(self, "Ordner wählen", start)
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Datei wählen", start)
        if path:
            self.edit.setText(os.path.normpath(path))

    def text(self):
        return self.edit.text().strip()

    def setText(self, value):
        self.edit.setText(value or "")


def thumbnail_pixmap(data, size=128):
    """QPixmap aus einem Sims-Vorschaubild (JPEG mit ALFA-Maske oder PNG)."""
    from simvault.analysis import thumbnails
    jpeg, alpha = thumbnails.split_alpha(data)
    image = QImage()
    if not image.loadFromData(jpeg):
        return None
    if alpha:
        mask = QImage()
        if mask.loadFromData(alpha) and mask.size() == image.size():
            image = image.convertToFormat(QImage.Format_ARGB32)
            image.setAlphaChannel(mask.convertToFormat(QImage.Format_Grayscale8))  # Graustufe = Deckkraft
    pix = QPixmap.fromImage(image)
    return pix.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


class DictTableModel(QAbstractTableModel):
    """Tabelle aus einer Liste von Dicts. columns: [(Überschrift, Schlüssel oder Funktion)]."""

    def __init__(self, columns, rows=None, color_key=None):
        super().__init__()
        self.columns = columns
        self.rows = rows or []
        self.color_key = color_key

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = list(rows)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return len(self.columns)

    def value(self, row, col):
        getter = self.columns[col][1]
        item = self.rows[row]
        return getter(item) if callable(getter) else item.get(getter, "")

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        value = self.value(index.row(), index.column())
        if role in (Qt.DisplayRole, Qt.ToolTipRole):
            if isinstance(value, (list, tuple)):
                return ", ".join(str(v) for v in value)
            if isinstance(value, str):
                from simvault.app import i18n
                return i18n.tr(value)            # z. B. Status „genutzt“ -> „used“
            return "" if value is None else str(value)
        if role == Qt.UserRole:          # zum Sortieren: Zahlen als Zahlen
            return value if isinstance(value, (int, float)) else str(value).lower()
        if role == Qt.ForegroundRole and self.color_key:
            status = self.rows[index.row()].get(self.color_key)
            color = theme.STATUS_COLORS.get(status)
            if color and self.columns[index.column()][1] == self.color_key:
                return QColor(color)
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            from simvault.app import i18n
            return i18n.tr(self.columns[section][0])
        return None


class FilterProxy(QSortFilterProxyModel):
    """Filtert über alle Spalten (Text) und optional nach einem Feld (z. B. Status)."""

    def __init__(self):
        super().__init__()
        self.setSortRole(Qt.UserRole)
        self.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.field = None
        self.field_value = None

    def set_field_filter(self, field, value):
        self.field, self.field_value = field, value
        self.invalidateFilter()

    def filterAcceptsRow(self, row, parent):
        model = self.sourceModel()
        if self.field and self.field_value and model.rows[row].get(self.field) != self.field_value:
            return False
        text = self.filterRegularExpression().pattern()
        if not text:
            return True
        text = text.lower()
        return any(text in str(model.data(model.index(row, c), Qt.DisplayRole)).lower()
                   for c in range(model.columnCount()))


def fit_columns(table, stretch, fit=(), widths=None):
    """Spaltenbreiten: stretch füllt den Rest, fit passt sich dem Inhalt an, widths = {Spalte: Pixel}."""
    from PySide6.QtWidgets import QHeaderView
    header = table.horizontalHeader()
    for col in range(table.model().columnCount()):
        if col == stretch:
            header.setSectionResizeMode(col, QHeaderView.Stretch)
        elif col in fit:
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        else:
            header.setSectionResizeMode(col, QHeaderView.Interactive)
            if widths and col in widths:
                header.resizeSection(col, widths[col])

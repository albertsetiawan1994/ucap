"""Ucap visual identity: warm paper, deep ink, coral accent."""
from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

# Calm cool neutrals with the coral brand accent.
INK = "#141B2D"          # sidebar, floating pill
INK_2 = "#232C44"
TEXT = "#1D2433"
PAPER = "#F4F6FA"        # window background
CARD = "#FFFFFF"
SUBTLE = "#F7F8FB"       # table headers, read-only fields
LINE = "#E3E7EF"
MUTED = "#667085"
SIDE_TEXT = "#AEB6C8"
ACCENT = "#FF6B4A"
ACCENT_DARK = "#E5532F"
ACCENT_SOFT = "#FFEDE7"
OK = "#12B76A"
ERR = "#F04438"
FONT = "Segoe UI"


def paint_logo(p: QPainter, r: QRectF, color: str = ACCENT, fg: str = "#FFFFFF") -> None:
    """Speech bubble with four sound bars."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    s = min(r.width(), r.height())
    x, y = r.x(), r.y()
    body = QRectF(x, y, s, s * 0.84)
    path = QPainterPath()
    path.addRoundedRect(body, s * 0.25, s * 0.25)
    tail = QPolygonF([QPointF(x + s * 0.2, y + s * 0.74), QPointF(x + s * 0.44, y + s * 0.74),
                      QPointF(x + s * 0.16, y + s)])
    path.addPolygon(tail)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawPath(path.simplified())
    pen = QPen(QColor(fg), s * 0.095, Qt.SolidLine, Qt.RoundCap)
    p.setPen(pen)
    cy = y + s * 0.42
    for i, h in enumerate((0.30, 0.54, 0.40, 0.20)):
        cx = x + s * 0.275 + i * s * 0.15
        p.drawLine(QPointF(cx, cy - s * h / 2), QPointF(cx, cy + s * h / 2))
    p.restore()


def logo_pixmap(size: int = 64, recording: bool = False) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    m = size * 0.04
    paint_logo(p, QRectF(m, m, size - 2 * m, size - 2 * m), ERR if recording else ACCENT)
    p.end()
    return pm


def logo_icon(recording: bool = False) -> QIcon:
    icon = QIcon()
    for s in (16, 20, 24, 32, 48, 64, 256):
        icon.addPixmap(logo_pixmap(s, recording))
    return icon


def glyph_icon(ch: str, color: str = SIDE_TEXT, size: int = 40) -> QIcon:
    """Icon from the Windows icon font (Segoe Fluent Icons on Windows 11, Segoe MDL2 Assets on Windows 10)."""
    family = next((f for f in ("Segoe Fluent Icons", "Segoe MDL2 Assets") if f in QFontDatabase.families()), FONT)
    icon = QIcon()
    for c, mode in ((color, QIcon.Normal), ("#FFFFFF", QIcon.Selected)):
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        f = QFont(family)
        f.setPixelSize(int(size * 0.62))
        p.setFont(f)
        p.setPen(QColor(c))
        p.drawText(pm.rect(), Qt.AlignCenter, ch)
        p.end()
        icon.addPixmap(pm, mode)
    return icon


def _icon_png(name: str, color: str, points) -> str:
    """QSS can only load images from files, so the tiny check/arrow glyphs are drawn once into %TEMP%."""
    path = Path(tempfile.gettempdir()) / f"ucap_{name}.png"
    if not path.exists():
        pm = QPixmap(32, 32)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(color), 4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPolyline([QPointF(x, y) for x, y in points])
        p.end()
        pm.save(str(path))
    return path.as_posix()


def _check_png() -> str:
    return _icon_png("check", "#FFFFFF", [(8, 17), (14, 23), (25, 10)])


def _arrow_png() -> str:
    return _icon_png("arrow", MUTED, [(9, 13), (16, 20), (23, 13)])


def stylesheet() -> str:
    return f"""
    QWidget {{ font-family: "{FONT}"; font-size: 10pt; color: {TEXT}; }}
    #Root, #Content {{ background: {PAPER}; }}
    #Side {{ background: {INK}; }}
    #Side QLabel {{ background: transparent; }}
    #Title {{ color: white; font-size: 15pt; font-weight: 700; }}
    #Tagline {{ color: {SIDE_TEXT}; font-size: 8.5pt; }}
    #Version {{ color: #6F7890; font-size: 8pt; }}
    QListWidget#Nav {{ background: transparent; border: none; outline: 0; }}
    QListWidget#Nav::item {{ color: {SIDE_TEXT}; padding: 9px 10px; margin: 2px 0; border-radius: 10px; }}
    QListWidget#Nav::item:hover {{ background: {INK_2}; color: white; }}
    QListWidget#Nav::item:selected {{ background: {ACCENT}; color: white; font-weight: 700; }}
    #Seg {{ background: {INK_2}; border-radius: 9px; }}
    #Seg QPushButton {{ background: transparent; color: {SIDE_TEXT}; border: none; border-radius: 7px;
                       padding: 4px 12px; font-weight: 700; font-size: 9pt; }}
    #Seg QPushButton:checked {{ background: {ACCENT}; color: white; }}
    #PageTitle {{ font-size: 17pt; font-weight: 700; color: {TEXT}; }}
    #Status {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 12px; }}
    #HkBadge {{ background: {ACCENT_SOFT}; color: {ACCENT_DARK}; border-radius: 8px; padding: 4px 10px;
               font-weight: 700; font-size: 9pt; }}
    QFrame#Card {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 14px; }}
    QFrame#Card > QLabel, QFrame#Card QCheckBox {{ background: transparent; }}
    QLabel#CardTitle {{ font-size: 11.5pt; font-weight: 700; color: {TEXT}; }}
    #Inner {{ background: {CARD}; }}
    QLabel#Field {{ font-weight: 600; }}
    QLabel#Muted {{ color: {MUTED}; font-size: 9pt; }}
    QPushButton {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 10px; padding: 7px 16px;
                   font-weight: 600; }}
    QPushButton:hover {{ background: {SUBTLE}; border-color: #CBD2DF; }}
    QPushButton:pressed {{ background: {LINE}; }}
    QPushButton:checked {{ background: {ACCENT_SOFT}; border-color: {ACCENT}; color: {ACCENT_DARK}; }}
    QPushButton[accent="true"] {{ background: {ACCENT}; color: white; border-color: {ACCENT}; font-weight: 700; }}
    QPushButton[accent="true"]:hover {{ background: {ACCENT_DARK}; border-color: {ACCENT_DARK}; }}
    QPushButton:disabled {{ color: #A3ABBC; background: {SUBTLE}; }}
    QLineEdit, QComboBox, QPlainTextEdit, QTextEdit {{ background: {CARD}; border: 1px solid {LINE};
        border-radius: 10px; padding: 6px 10px; selection-background-color: {ACCENT_SOFT}; selection-color: {TEXT}; }}
    QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QTextEdit:focus {{ border: 1px solid {ACCENT}; }}
    QLineEdit[readOnly="true"] {{ background: {SUBTLE}; font-weight: 700; }}
    QTextEdit[readOnly="true"]:focus {{ border: 1px solid {LINE}; }}
    QFrame#BubbleMe {{ background: {ACCENT_SOFT}; border-radius: 14px; }}
    QFrame#BubbleAi {{ background: {SUBTLE}; border: 1px solid {LINE}; border-radius: 14px; }}
    QFrame#BubbleMe QLabel, QFrame#BubbleAi QLabel {{ background: transparent; }}
    QFrame#BubbleAi QPushButton {{ padding: 3px 10px; font-size: 9pt; }}
    QPushButton#SegTab {{ border-radius: 9px; padding: 6px 16px; }}
    QComboBox::drop-down {{ border: none; width: 28px; }}
    QComboBox::down-arrow {{ image: url({_arrow_png()}); width: 12px; height: 12px; }}
    QComboBox QAbstractItemView {{ border: 1px solid {LINE}; border-radius: 8px; selection-background-color: {ACCENT_SOFT};
                                  selection-color: {TEXT}; background: {CARD}; padding: 4px; }}
    QCheckBox {{ spacing: 10px; padding: 3px 0; }}
    QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 6px; border: 1px solid #C5CCDA; background: {CARD}; }}
    QCheckBox::indicator:hover {{ border-color: {ACCENT}; }}
    QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; image: url({_check_png()}); }}
    QTableWidget {{ border: 1px solid {LINE}; border-radius: 10px; background: {CARD}; gridline-color: {CARD};
                   alternate-background-color: {SUBTLE}; selection-background-color: {ACCENT_SOFT};
                   selection-color: {TEXT}; outline: 0; }}
    QTableWidget::item {{ padding: 0 6px; }}
    QHeaderView::section {{ background: {SUBTLE}; color: {MUTED}; font-weight: 700; font-size: 9pt; border: none;
                           border-bottom: 1px solid {LINE}; padding: 7px 8px; }}
    QFrame#KeyRow {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 12px; }}
    QFrame#KeyRow QPushButton {{ padding: 5px 12px; }}
    QProgressBar {{ background: {LINE}; border: none; border-radius: 3px; }}
    QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}
    QScrollArea {{ background: transparent; border: none; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}
    QFrame#Sep {{ background: {LINE}; max-height: 1px; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: #CFD5E1; border-radius: 4px; min-height: 28px; }}
    QScrollBar::handle:vertical:hover {{ background: #B5BDCC; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QToolTip {{ background: {INK}; color: white; border: none; padding: 6px 8px; border-radius: 6px; }}
    """

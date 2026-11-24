"""Ucap visual identity: warm paper, deep ink, coral accent."""
from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

INK = "#1B2030"
INK_2 = "#2A3145"
PAPER = "#F5F3EE"
CARD = "#FFFFFF"
LINE = "#E4E0D7"
MUTED = "#6B7080"
ACCENT = "#FF6A3D"
ACCENT_DARK = "#E2522A"
ACCENT_SOFT = "#FFE6DD"
OK = "#1F9E89"
ERR = "#D64545"
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
    QWidget {{ font-family: "{FONT}"; font-size: 10pt; color: {INK}; }}
    #Root {{ background: {PAPER}; }}
    #Header {{ background: {INK}; }}
    #Title {{ color: white; font-size: 18pt; font-weight: 700; }}
    #Tagline {{ color: #AEB3C2; font-size: 9pt; }}
    #Seg {{ background: {INK_2}; border-radius: 8px; }}
    #Seg QPushButton {{ background: transparent; color: #C9CCD6; border: none; border-radius: 6px;
                       padding: 4px 12px; font-weight: 700; font-size: 9pt; }}
    #Seg QPushButton:checked {{ background: {ACCENT}; color: white; }}
    #Status {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 10px; }}
    #HkBadge {{ background: {ACCENT_SOFT}; color: {ACCENT_DARK}; border-radius: 6px; padding: 3px 9px;
               font-weight: 700; font-size: 9pt; }}
    QTabWidget::pane {{ border: 1px solid {LINE}; background: {CARD}; border-radius: 10px; top: -1px; }}
    QTabBar::tab {{ background: transparent; color: {MUTED}; padding: 8px 14px; margin-right: 2px;
                   border: 1px solid transparent; border-top-left-radius: 8px; border-top-right-radius: 8px; }}
    QTabBar::tab:selected {{ background: {CARD}; color: {ACCENT_DARK}; font-weight: 700;
                            border-color: {LINE}; border-bottom-color: {CARD}; }}
    QTabBar::tab:hover:!selected {{ color: {INK}; }}
    #Card {{ background: {CARD}; }}
    QLabel#Field {{ font-weight: 700; }}
    QLabel#Muted {{ color: {MUTED}; font-size: 9pt; }}
    QPushButton {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 8px; padding: 6px 14px; }}
    QPushButton:hover {{ background: {PAPER}; }}
    QPushButton:pressed {{ background: {LINE}; }}
    QPushButton[accent="true"] {{ background: {ACCENT}; color: white; border-color: {ACCENT}; font-weight: 700; }}
    QPushButton[accent="true"]:hover {{ background: {ACCENT_DARK}; border-color: {ACCENT_DARK}; }}
    QPushButton:disabled {{ color: {MUTED}; }}
    QLineEdit, QComboBox, QPlainTextEdit {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 8px;
                                           padding: 5px 8px; selection-background-color: {ACCENT_SOFT};
                                           selection-color: {INK}; }}
    QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{ border-color: {ACCENT}; }}
    QLineEdit[readOnly="true"] {{ background: {PAPER}; font-weight: 700; }}
    QComboBox::drop-down {{ border: none; width: 26px; }}
    QComboBox::down-arrow {{ image: url({_arrow_png()}); width: 12px; height: 12px; }}
    QComboBox QAbstractItemView {{ border: 1px solid {LINE}; selection-background-color: {ACCENT_SOFT};
                                  selection-color: {INK}; background: {CARD}; }}
    QCheckBox {{ spacing: 8px; }}
    QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 5px; border: 1px solid #C8C3B8;
                           background: {CARD}; }}
    QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; image: url({_check_png()}); }}
    QTableWidget {{ border: 1px solid {LINE}; border-radius: 8px; background: {CARD}; gridline-color: {CARD};
                   selection-background-color: {ACCENT_SOFT}; selection-color: {INK}; outline: 0; }}
    QHeaderView::section {{ background: {PAPER}; color: {MUTED}; font-weight: 700; font-size: 9pt; border: none;
                           border-bottom: 1px solid {LINE}; padding: 6px 8px; }}
    QFrame#KeyRow {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 8px; }}
    QFrame#KeyRow QPushButton {{ padding: 4px 10px; }}
    QScrollArea {{ background: transparent; border: none; }}
    QFrame#Sep {{ background: {LINE}; max-height: 1px; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: #D8D3C9; border-radius: 4px; min-height: 24px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    """

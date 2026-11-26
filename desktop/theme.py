"""
Dark Futuristic Theme & Design Tokens for JARVIS AI Desktop.

Uses Segoe UI typography, clean 1px borders, rounded cards, subtle cyan/blue
accents, and exact contrast-checked dark surfaces without clutter.
"""

from __future__ import annotations

# Design palette tokens
COLORS = {
    "bg_main": "#090D14",
    "bg_sidebar": "#0D1420",
    "bg_panel": "#111B29",
    "bg_secondary": "#172333",
    "bg_input": "#0E1724",
    "bg_hover": "#1C2B3F",
    "text_primary": "#E8EFF7",
    "text_secondary": "#91A3B7",
    "text_muted": "#62748A",
    "accent_cyan": "#42CBEF",
    "accent_blue": "#368DFF",
    "success": "#35D69A",
    "warning": "#F2B85B",
    "error": "#F06472",
    "border": "#263548",
    "border_focus": "#42CBEF",
    "user_bubble": "#183354",
    "assistant_bubble": "#111B29",
}


def build_stylesheet() -> str:
    """Return application-wide QSS stylesheet for PySide6."""
    c = COLORS
    return f"""
    QMainWindow, QDialog {{
        background-color: {c["bg_main"]};
        color: {c["text_primary"]};
        font-family: "Segoe UI", "Inter", sans-serif;
        font-size: 13px;
    }}

    QWidget {{
        color: {c["text_primary"]};
        font-family: "Segoe UI", "Inter", sans-serif;
    }}

    /* Scrollbars & Scroll Viewports */
    QStackedWidget, QScrollArea, QScrollArea > QWidget, QScrollArea > QWidget > QWidget {{
        border: none;
        background-color: {c["bg_main"]};
    }}
    QScrollBar:vertical {{
        background: {c["bg_main"]};
        width: 8px;
        margin: 2px 0;
        border-radius: 4px;
    }}
    QScrollBar::handle:vertical {{
        background: {c["border"]};
        min-height: 28px;
        border-radius: 4px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {c["text_muted"]};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar:horizontal {{
        background: {c["bg_main"]};
        height: 8px;
        border-radius: 4px;
    }}
    QScrollBar::handle:horizontal {{
        background: {c["border"]};
        min-width: 28px;
        border-radius: 4px;
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}

    /* Sidebar */
    #Sidebar {{
        background-color: {c["bg_sidebar"]};
        border-right: 1px solid {c["border"]};
    }}
    #SidebarBrandTitle {{
        font-size: 18px;
        font-weight: 700;
        letter-spacing: 2px;
        color: {c["text_primary"]};
    }}
    #SidebarBrandSubtitle {{
        font-size: 10px;
        font-weight: 600;
        letter-spacing: 1.4px;
        color: {c["accent_cyan"]};
    }}
    QPushButton#NavButton {{
        text-align: left;
        padding: 10px 14px;
        border-radius: 8px;
        border: 1px solid transparent;
        background-color: transparent;
        color: {c["text_secondary"]};
        font-size: 13px;
        font-weight: 500;
    }}
    QPushButton#NavButton:hover {{
        background-color: {c["bg_secondary"]};
        color: {c["text_primary"]};
    }}
    QPushButton#NavButton[active="true"] {{
        background-color: {c["bg_secondary"]};
        border: 1px solid {c["border"]};
        border-left: 3px solid {c["accent_cyan"]};
        color: {c["text_primary"]};
        font-weight: 600;
    }}

    /* Topbar */
    #Topbar {{
        background-color: {c["bg_sidebar"]};
        border-bottom: 1px solid {c["border"]};
    }}
    #PageTitle {{
        font-size: 16px;
        font-weight: 600;
        color: {c["text_primary"]};
    }}

    /* Cards & Panels */
    #Card, QFrame#StatusCard {{
        background-color: {c["bg_panel"]};
        border: 1px solid {c["border"]};
        border-radius: 12px;
    }}
    #SecondaryCard {{
        background-color: {c["bg_secondary"]};
        border: 1px solid {c["border"]};
        border-radius: 10px;
    }}

    /* Chat bubbles */
    QFrame#UserBubble {{
        background-color: {c["user_bubble"]};
        border: 1px solid #284D7A;
        border-radius: 12px;
    }}
    QFrame#AssistantBubble {{
        background-color: {c["assistant_bubble"]};
        border: 1px solid {c["border"]};
        border-radius: 12px;
    }}
    QFrame#ToolBubble {{
        background-color: {c["bg_secondary"]};
        border: 1px solid {c["border"]};
        border-left: 3px solid {c["accent_blue"]};
        border-radius: 8px;
    }}
    QFrame#ErrorBubble {{
        background-color: #24131A;
        border: 1px solid #592632;
        border-left: 3px solid {c["error"]};
        border-radius: 8px;
    }}

    /* Inputs */
    QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QDoubleSpinBox, QSpinBox {{
        background-color: {c["bg_input"]};
        border: 1px solid {c["border"]};
        border-radius: 8px;
        padding: 8px 10px;
        color: {c["text_primary"]};
        selection-background-color: {c["accent_blue"]};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus {{
        border: 1px solid {c["border_focus"]};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 24px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {c["bg_panel"]};
        border: 1px solid {c["border"]};
        selection-background-color: {c["bg_hover"]};
        color: {c["text_primary"]};
    }}

    /* Buttons */
    QPushButton {{
        background-color: {c["bg_secondary"]};
        border: 1px solid {c["border"]};
        border-radius: 8px;
        padding: 8px 14px;
        color: {c["text_primary"]};
        font-weight: 500;
    }}
    QPushButton:hover {{
        background-color: {c["bg_hover"]};
        border-color: #364B66;
    }}
    QPushButton:disabled {{
        color: {c["text_muted"]};
        background-color: {c["bg_panel"]};
        border-color: #1A2533;
    }}
    QPushButton#PrimaryButton {{
        background-color: {c["accent_blue"]};
        border: 1px solid #4E9BFF;
        color: #FFFFFF;
        font-weight: 600;
    }}
    QPushButton#PrimaryButton:hover {{
        background-color: #499AFF;
    }}
    QPushButton#AccentButton {{
        background-color: #122E3D;
        border: 1px solid {c["accent_cyan"]};
        color: {c["accent_cyan"]};
        font-weight: 600;
    }}
    QPushButton#AccentButton:hover {{
        background-color: #173B4E;
    }}
    QPushButton#DangerButton {{
        background-color: #331820;
        border: 1px solid {c["error"]};
        color: {c["error"]};
        font-weight: 600;
    }}
    QPushButton#DangerButton:hover {{
        background-color: #45202B;
    }}

    /* Pills & Badges */
    QLabel#Badge {{
        background-color: {c["bg_secondary"]};
        border: 1px solid {c["border"]};
        border-radius: 10px;
        padding: 3px 10px;
        font-size: 11px;
        font-weight: 600;
        color: {c["text_secondary"]};
    }}

    /* Tabs / Tables */
    QTableWidget {{
        background-color: {c["bg_panel"]};
        border: 1px solid {c["border"]};
        border-radius: 8px;
        gridline-color: {c["border"]};
    }}
    QHeaderView::section {{
        background-color: {c["bg_secondary"]};
        color: {c["text_secondary"]};
        padding: 6px 10px;
        border: none;
        border-bottom: 1px solid {c["border"]};
        font-weight: 600;
        font-size: 11px;
    }}
    QTabWidget::pane {{
        border: 1px solid {c["border"]};
        border-radius: 8px;
        background-color: {c["bg_panel"]};
    }}
    QTabBar::tab {{
        background-color: {c["bg_sidebar"]};
        color: {c["text_secondary"]};
        border: 1px solid {c["border"]};
        border-bottom: none;
        padding: 8px 16px;
        margin-right: 4px;
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
    }}
    QTabBar::tab:selected {{
        background-color: {c["bg_panel"]};
        color: {c["accent_cyan"]};
        font-weight: 600;
    }}
    """

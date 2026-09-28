"""Modern dark theme stylesheets for Subterranean Staircase GUI.

Follows clean, high-contrast, anti-slop design principles with a zinc/charcoal dark palette
and neon cyan accents (#00E5FF) matching native pro tools (Linear, Raycast, DaVinci).
"""

MODERN_DARK_THEME = """
/* Global Window Styling */
QDialog, QWidget#SettingsRoot {
    background-color: #121214;
    color: #EDEDED;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    font-size: 13px;
}

/* Headings and Labels */
QLabel {
    color: #D1D5DB;
    font-size: 13px;
}

QLabel#SectionHeader {
    color: #F3F4F6;
    font-size: 14px;
    font-weight: 600;
    padding-bottom: 4px;
}

QLabel#SubtleHint {
    color: #9CA3AF;
    font-size: 11px;
}

/* Card Container Panels */
QFrame#CardPanel {
    background-color: #18181B;
    border: 1px solid #27272A;
    border-radius: 8px;
    padding: 12px;
}

/* Form Controls: Combo Box */
QComboBox {
    background-color: #27272A;
    color: #F3F4F6;
    border: 1px solid #3F3F46;
    border-radius: 6px;
    padding: 6px 12px;
    min-height: 20px;
    font-weight: 500;
}

QComboBox:hover {
    border-color: #52525B;
    background-color: #2E2E33;
}

QComboBox:focus {
    border-color: #00E5FF;
    outline: none;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 24px;
    border-left: none;
}

QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #9CA3AF;
    margin-right: 8px;
}

QComboBox QAbstractItemView {
    background-color: #18181B;
    color: #F3F4F6;
    border: 1px solid #3F3F46;
    border-radius: 6px;
    selection-background-color: #27272A;
    selection-color: #00E5FF;
    padding: 4px;
    outline: none;
}

/* SpinBox */
QSpinBox {
    background-color: #27272A;
    color: #F3F4F6;
    border: 1px solid #3F3F46;
    border-radius: 6px;
    padding: 6px 10px;
    min-height: 20px;
}

QSpinBox:hover {
    border-color: #52525B;
}

QSpinBox:focus {
    border-color: #00E5FF;
}

QSpinBox::up-button, QSpinBox::down-button {
    background: transparent;
    border: none;
    width: 16px;
}

/* CheckBox */
QCheckBox {
    color: #E5E7EB;
    spacing: 8px;
    font-size: 13px;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid #3F3F46;
    background-color: #27272A;
}

QCheckBox::indicator:hover {
    border-color: #52525B;
}

QCheckBox::indicator:checked {
    background-color: #00E5FF;
    border-color: #00E5FF;
}

/* Table Widget */
QTableWidget {
    background-color: #18181B;
    border: 1px solid #27272A;
    border-radius: 8px;
    gridline-color: #27272A;
    color: #E5E7EB;
    selection-background-color: #27272A;
}

QHeaderView::section {
    background-color: #141416;
    color: #9CA3AF;
    padding: 8px 10px;
    border: none;
    border-bottom: 1px solid #27272A;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
}

QTableWidget::item {
    padding: 6px 10px;
    border-bottom: 1px solid #1F1F23;
}

/* Buttons */
QPushButton {
    background-color: #27272A;
    color: #F3F4F6;
    border: 1px solid #3F3F46;
    border-radius: 6px;
    padding: 7px 16px;
    font-weight: 500;
    font-size: 13px;
}

QPushButton:hover {
    background-color: #323238;
    border-color: #52525B;
}

QPushButton:pressed {
    background-color: #1E1E22;
}

QPushButton#PrimaryButton {
    background-color: #00E5FF;
    color: #09090B;
    border: 1px solid #00E5FF;
    font-weight: 600;
}

QPushButton#PrimaryButton:hover {
    background-color: #33EBFF;
    border-color: #33EBFF;
}

QPushButton#PrimaryButton:pressed {
    background-color: #00B8CC;
}

/* Action Buttons in Model Table */
QPushButton#TableDownloadButton {
    background-color: #0F2E35;
    color: #00E5FF;
    border: 1px solid #155E69;
    border-radius: 5px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 600;
}

QPushButton#TableDownloadButton:hover {
    background-color: #164650;
    border-color: #00E5FF;
}

QPushButton#TableDeleteButton {
    background-color: #361717;
    color: #FF6B6B;
    border: 1px solid #632323;
    border-radius: 5px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 600;
}

QPushButton#TableDeleteButton:hover {
    background-color: #4A1D1D;
    border-color: #FF6B6B;
}

/* Control Center Specific Elements */
QPushButton#StartButton {
    background-color: #00E5FF;
    color: #09090B;
    border: 1px solid #00E5FF;
    font-weight: 700;
    font-size: 14px;
    padding: 8px 24px;
    border-radius: 8px;
}

QPushButton#StartButton:hover {
    background-color: #33EBFF;
    border-color: #33EBFF;
}

QPushButton#PauseButton {
    background-color: #27272A;
    color: #F87171;
    border: 1px solid #EF4444;
    font-weight: 700;
    font-size: 14px;
    padding: 8px 24px;
    border-radius: 8px;
}

QPushButton#PauseButton:hover {
    background-color: #3F3F46;
    border-color: #F87171;
}

QPushButton#DangerButton {
    background-color: transparent;
    color: #EF4444;
    border: 1px solid #7F1D1D;
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 12px;
}

QPushButton#DangerButton:hover {
    background-color: #450A0A;
    border-color: #EF4444;
}

QLabel#StatusBadgeActive {
    color: #4ADE80;
    font-weight: 700;
    font-size: 12px;
    letter-spacing: 0.5px;
}

QLabel#StatusBadgeStandby {
    color: #9CA3AF;
    font-weight: 600;
    font-size: 12px;
    letter-spacing: 0.5px;
}

/* Scrollbars */
QScrollBar:vertical {
    border: none;
    background: transparent;
    width: 8px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background: #3F3F46;
    min-height: 20px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background: #52525B;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
"""

"""Settings and Configuration Dialog for Subtitle Translator V1.

Keyboard-accessible (Tab, Enter, Escape) configuration window adhering strictly
to Anti-Slop principles: clean visual hierarchy, zero decorative fluff, functional completeness.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.config import ConfigManager


class SettingsDialog(QDialog):
    """Configuration dialog for language pairs, overlay style, and capture settings."""

    # Predefined popular languages for subtitle translation
    LANGUAGES = [
        ("English", "en"),
        ("Indonesian", "id"),
        ("Japanese", "ja"),
        ("Korean", "ko"),
        ("Chinese", "zh"),
        ("French", "fr"),
        ("German", "de"),
        ("Spanish", "es"),
        ("Arabic", "ar"),
    ]

    def __init__(
        self,
        config_manager: ConfigManager,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.config_manager = config_manager
        self._init_ui()

    def _init_ui(self) -> None:
        self.setWindowTitle("Subtitle Translator — Settings")
        self.setMinimumWidth(380)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        # 1. Source Language
        self.source_combo = QComboBox(self)
        for name, code in self.LANGUAGES:
            self.source_combo.addItem(f"{name} ({code})", code)
        src_code = self.config_manager.config.source_language
        src_idx = self.source_combo.findData(src_code)
        if src_idx < 0:
            self.source_combo.addItem(f"Custom ({src_code})", src_code)
            src_idx = self.source_combo.findData(src_code)
        if src_idx >= 0:
            self.source_combo.setCurrentIndex(src_idx)
        form_layout.addRow(QLabel("Source Language:"), self.source_combo)

        # 2. Target Language
        self.target_combo = QComboBox(self)
        for name, code in self.LANGUAGES:
            self.target_combo.addItem(f"{name} ({code})", code)
        tgt_code = self.config_manager.config.target_language
        tgt_idx = self.target_combo.findData(tgt_code)
        if tgt_idx < 0:
            self.target_combo.addItem(f"Custom ({tgt_code})", tgt_code)
            tgt_idx = self.target_combo.findData(tgt_code)
        if tgt_idx >= 0:
            self.target_combo.setCurrentIndex(tgt_idx)
        form_layout.addRow(QLabel("Target Language:"), self.target_combo)

        # 3. Font Size
        self.font_size_spin = QSpinBox(self)
        self.font_size_spin.setRange(12, 64)
        self.font_size_spin.setValue(self.config_manager.config.overlay.font_size)
        form_layout.addRow(QLabel("Subtitle Font Size:"), self.font_size_spin)

        # 4. Fade-out delay
        self.fade_out_spin = QSpinBox(self)
        self.fade_out_spin.setRange(1, 15)
        self.fade_out_spin.setSuffix(" sec")
        self.fade_out_spin.setValue(int(self.config_manager.config.overlay.fade_out_seconds))
        form_layout.addRow(QLabel("Subtitle Fade-Out:"), self.fade_out_spin)

        layout.addLayout(form_layout)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.save_btn = QPushButton("Save Settings", self)
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self._save_and_close)

        self.cancel_btn = QPushButton("Cancel", self)
        self.cancel_btn.clicked.connect(self.reject)

        button_layout.addWidget(self.cancel_btn)
        button_layout.addWidget(self.save_btn)
        layout.addLayout(button_layout)

    def _save_and_close(self) -> None:
        """Update and persist configuration."""
        selected_src = str(self.source_combo.currentData())
        selected_tgt = str(self.target_combo.currentData())
        font_size = self.font_size_spin.value()
        fade_out = float(self.fade_out_spin.value())

        self.config_manager.update(
            source_language=selected_src,
            target_language=selected_tgt,
            overlay={
                "font_size": font_size,
                "fade_out_seconds": fade_out,
            },
        )
        self.accept()

"""Settings and Configuration Dialog for Subtitle Translator V1.

Keyboard-accessible (Tab, Enter, Escape) configuration window adhering strictly
to Anti-Slop principles: clean visual hierarchy, zero decorative fluff, functional completeness.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.autostart import AutostartManager
from core.config import ConfigManager
from core.translate.models import ModelManager
from core.updater import UpdateInfo, UpdateManager
from ui.model_dialog import ModelDownloadProgressDialog
from ui.updater_dialog import UpdateCheckWorker, UpdateProgressDialog


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
        self.model_manager = ModelManager()
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

        # 5. Offline Models Manager Group
        models_group = QGroupBox("Offline Translation Models", self)
        models_layout = QVBoxLayout(models_group)
        models_layout.setSpacing(8)

        models_hint = QLabel("Download models for offline on-device translation. Delete to free disk space.", self)
        models_hint.setStyleSheet("color: #888888; font-size: 11px;")
        models_layout.addWidget(models_hint)

        self.models_table = QTableWidget(self)
        self.models_table.setColumnCount(4)
        self.models_table.setHorizontalHeaderLabels(["Language Pair", "Description", "Status / Size", "Action"])
        self.models_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.models_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.models_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.models_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.models_table.verticalHeader().setVisible(False)
        self.models_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.models_table.setFixedHeight(180)
        models_layout.addWidget(self.models_table)

        self._refresh_models_table()
        layout.addWidget(models_group)

        # 6. System Integration & Autostart
        system_group = QGroupBox("System & Autostart", self)
        system_layout = QVBoxLayout(system_group)
        self.autostart_manager = AutostartManager()
        self.autostart_cb = QCheckBox("Start Subterranean Staircase on system login", self)
        # Reflect actual system status or saved configuration
        self.autostart_cb.setChecked(
            self.config_manager.config.autostart_on_boot or self.autostart_manager.is_enabled()
        )
        system_layout.addWidget(self.autostart_cb)
        layout.addWidget(system_group)

        # 6. Updates Group
        update_group = QGroupBox("Application Updates", self)
        update_layout = QVBoxLayout(update_group)
        update_layout.setSpacing(8)

        self.check_updates_cb = QCheckBox("Check for updates on launch", self)
        self.check_updates_cb.setChecked(self.config_manager.config.check_updates)
        update_layout.addWidget(self.check_updates_cb)

        check_row = QHBoxLayout()
        self.check_now_btn = QPushButton("Check for Updates Now", self)
        self.check_now_btn.clicked.connect(self._check_for_updates_now)
        check_row.addWidget(self.check_now_btn)
        check_row.addStretch()
        update_layout.addLayout(check_row)

        layout.addWidget(update_group)

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

    def _refresh_models_table(self) -> None:
        """Populate the models table with current installation status and action buttons."""
        models = self.model_manager.list_models_status()
        self.models_table.setRowCount(len(models))

        for row, item in enumerate(models):
            pair_id = item["pair_id"]
            name_item = QTableWidgetItem(item["name"])
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.models_table.setItem(row, 0, name_item)

            desc_item = QTableWidgetItem(item["description"])
            desc_item.setFlags(desc_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.models_table.setItem(row, 1, desc_item)

            if item["installed"]:
                status_text = f"✔ Installed ({item['installed_size_mb']} MB)"
                status_item = QTableWidgetItem(status_text)
                btn = QPushButton("Delete")
                btn.setStyleSheet("color: #ff5555;")
                btn.clicked.connect(lambda checked, pid=pair_id: self._delete_model_clicked(pid))
            else:
                status_text = f"Not Installed (~{item['approx_size_mb']} MB)"
                status_item = QTableWidgetItem(status_text)
                btn = QPushButton("Download")
                btn.setStyleSheet("color: #00e5ff;")
                btn.clicked.connect(lambda checked, pid=pair_id: self._download_model_clicked(pid))

            status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.models_table.setItem(row, 2, status_item)
            self.models_table.setCellWidget(row, 3, btn)

    def _download_model_clicked(self, pair_id: str) -> None:
        """Trigger interactive download dialog for a model."""
        dialog = ModelDownloadProgressDialog(self.model_manager, pair_id, self)
        dialog.start_download()
        self._refresh_models_table()

    def _delete_model_clicked(self, pair_id: str) -> None:
        """Prompt confirmation and delete an installed model."""
        confirm = QMessageBox.question(
            self,
            "Delete Model",
            f"Are you sure you want to delete the offline model for '{pair_id}'?\n"
            "This will free up disk space.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            success, msg = self.model_manager.delete_model(pair_id)
            if success:
                self._refresh_models_table()
            else:
                QMessageBox.warning(self, "Delete Failed", msg)

    def _check_for_updates_now(self) -> None:
        """Trigger immediate manual update check."""
        self.check_now_btn.setEnabled(False)
        self.check_now_btn.setText("Checking...")
        self._update_manager = UpdateManager()
        self._check_worker = UpdateCheckWorker(self._update_manager, self)
        self._check_worker.check_finished.connect(self._on_manual_check_finished)
        self._check_worker.start()

    def _on_manual_check_finished(self, info: UpdateInfo) -> None:
        """Handle results of manual update check."""
        self.check_now_btn.setEnabled(True)
        self.check_now_btn.setText("Check for Updates Now")

        if info.has_update:
            confirm = QMessageBox.question(
                self,
                "Update Available",
                f"{info.message}\n\nWould you like to install the update and restart now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if confirm == QMessageBox.StandardButton.Yes:
                dialog = UpdateProgressDialog(self._update_manager, self)
                dialog.start_update()
        else:
            QMessageBox.information(
                self,
                "Subtitle Translator Updates",
                info.message,
            )

    def _save_and_close(self) -> None:
        """Update and persist configuration."""
        selected_src = str(self.source_combo.currentData())
        selected_tgt = str(self.target_combo.currentData())
        font_size = self.font_size_spin.value()
        fade_out = float(self.fade_out_spin.value())
        check_updates = self.check_updates_cb.isChecked()
        autostart = self.autostart_cb.isChecked()

        # Apply system autostart hook
        self.autostart_manager.set_enabled(autostart)

        self.config_manager.update(
            source_language=selected_src,
            target_language=selected_tgt,
            check_updates=check_updates,
            autostart_on_boot=autostart,
            overlay={
                "font_size": font_size,
                "fade_out_seconds": fade_out,
            },
        )
        self.accept()

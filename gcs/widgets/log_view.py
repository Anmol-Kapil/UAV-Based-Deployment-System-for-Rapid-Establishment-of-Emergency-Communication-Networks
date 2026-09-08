"""Event Log View for GCS Context Panel.

Maintains persistent operational history:
- Timestamp
- Severity (INFO, WARNING, CRITICAL)
- Category (SYSTEM, MAVLINK, MISSION, SAFETY)
- Message
"""

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QPushButton,
    QComboBox,
    QLabel,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from gcs.state.app_state import app_state


class LogView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        self._connect_signals()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Log toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        lbl_filter = QLabel("FILTER:")
        lbl_filter.setStyleSheet("font-weight: 700; font-size: 10px; color: #8b949e;")
        toolbar.addWidget(lbl_filter)

        self.combo_filter = QComboBox()
        self.combo_filter.addItems(["ALL", "INFO", "WARNING", "CRITICAL"])
        self.combo_filter.currentIndexChanged.connect(self._apply_filter)
        toolbar.addWidget(self.combo_filter)

        toolbar.addStretch()

        btn_clear = QPushButton("Clear Log")
        btn_clear.clicked.connect(self.clear_log)
        toolbar.addWidget(btn_clear)

        layout.addLayout(toolbar)

        # Table
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["TIME", "SEVERITY", "CATEGORY", "MESSAGE"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        layout.addWidget(self.table)

    def _connect_signals(self):
        app_state.log_event.connect(self.add_log_entry)

    def add_log_entry(self, timestamp: str, severity: str, category: str, message: str):
        row = self.table.rowCount()
        self.table.insertRow(row)

        item_time = QTableWidgetItem(timestamp)
        item_time.setForeground(QColor("#8b949e"))

        item_sev = QTableWidgetItem(severity)
        if severity == "CRITICAL":
            item_sev.setForeground(QColor("#f85149"))
        elif severity == "WARNING":
            item_sev.setForeground(QColor("#d29922"))
        else:
            item_sev.setForeground(QColor("#58a6ff"))

        item_cat = QTableWidgetItem(category)
        item_cat.setForeground(QColor("#79c0ff"))

        item_msg = QTableWidgetItem(message)
        item_msg.setForeground(QColor("#c9d1d9"))

        self.table.setItem(row, 0, item_time)
        self.table.setItem(row, 1, item_sev)
        self.table.setItem(row, 2, item_cat)
        self.table.setItem(row, 3, item_msg)

        # Auto-scroll to bottom
        self.table.scrollToBottom()

    def _apply_filter(self):
        filter_text = self.combo_filter.currentText()
        for row in range(self.table.rowCount()):
            sev_item = self.table.item(row, 1)
            if not sev_item:
                continue
            if filter_text == "ALL" or sev_item.text() == filter_text:
                self.table.setRowHidden(row, False)
            else:
                self.table.setRowHidden(row, True)

    def clear_log(self):
        self.table.setRowCount(0)

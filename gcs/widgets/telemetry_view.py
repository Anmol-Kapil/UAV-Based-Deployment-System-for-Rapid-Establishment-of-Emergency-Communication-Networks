"""Telemetry View for GCS Context Panel.

Displays:
- Latitude & Longitude
- Relative Altitude
- Ground Speed
- Heading
- Attitude (Roll, Pitch, Yaw)
- Battery (% and V)
- GPS Fix & Satellites
- Flight Mode
- Armed State
"""

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QGridLayout,
    QScrollArea,
)
from PySide6.QtCore import Qt
from gcs.state.app_state import app_state


class TelemetryItem(QFrame):
    """Reusable card for a single telemetry metric."""

    def __init__(self, label: str, unit: str = "", parent=None):
        super().__init__(parent)
        self.setProperty("class", "telemetry-card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        self.lbl_title = QLabel(label)
        self.lbl_title.setProperty("class", "telemetry-label")
        layout.addWidget(self.lbl_title)

        val_layout = QHBoxLayout()
        val_layout.setContentsMargins(0, 0, 0, 0)
        val_layout.setSpacing(2)

        self.lbl_value = QLabel("--")
        self.lbl_value.setProperty("class", "telemetry-value")
        val_layout.addWidget(self.lbl_value)

        if unit:
            self.lbl_unit = QLabel(unit)
            self.lbl_unit.setProperty("class", "telemetry-unit")
            val_layout.addWidget(self.lbl_unit)

        val_layout.addStretch()
        layout.addLayout(val_layout)

    def set_value(self, value):
        if isinstance(value, float):
            self.lbl_value.setText(f"{value:.1f}")
        else:
            self.lbl_value.setText(str(value))


class TelemetryView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        self._connect_signals()

    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(6, 6, 6, 6)
        root_layout.setSpacing(6)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # GPS Coordinates Card
        gps_card = QFrame()
        gps_card.setProperty("class", "telemetry-card")
        gps_layout = QVBoxLayout(gps_card)
        gps_layout.setContentsMargins(8, 6, 8, 6)
        gps_layout.setSpacing(3)

        lbl_gps_title = QLabel("GLOBAL POSITION (WGS-84)")
        lbl_gps_title.setProperty("class", "telemetry-label")
        gps_layout.addWidget(lbl_gps_title)

        coord_row = QHBoxLayout()
        self.val_lat = QLabel("LAT: --")
        self.val_lat.setProperty("class", "telemetry-value")
        self.val_lon = QLabel("LON: --")
        self.val_lon.setProperty("class", "telemetry-value")
        coord_row.addWidget(self.val_lat)
        coord_row.addWidget(self.val_lon)
        gps_layout.addLayout(coord_row)
        layout.addWidget(gps_card)

        # Key Flight Metrics Grid
        grid = QGridLayout()
        grid.setSpacing(6)

        self.item_alt = TelemetryItem("ALTITUDE (REL)", "m")
        self.item_speed = TelemetryItem("GROUND SPEED", "m/s")
        self.item_heading = TelemetryItem("HEADING", "°")
        self.item_battery = TelemetryItem("BATTERY", "%")

        grid.addWidget(self.item_alt, 0, 0)
        grid.addWidget(self.item_speed, 0, 1)
        grid.addWidget(self.item_heading, 1, 0)
        grid.addWidget(self.item_battery, 1, 1)
        layout.addLayout(grid)

        # Attitude (Roll, Pitch, Yaw)
        att_card = QFrame()
        att_card.setProperty("class", "telemetry-card")
        att_layout = QVBoxLayout(att_card)
        att_layout.setContentsMargins(8, 6, 8, 6)
        att_layout.setSpacing(3)

        lbl_att_title = QLabel("ATTITUDE / ORIENTATION")
        lbl_att_title.setProperty("class", "telemetry-label")
        att_layout.addWidget(lbl_att_title)

        att_row = QHBoxLayout()
        self.val_roll = QLabel("R: --°")
        self.val_roll.setProperty("class", "telemetry-value")
        self.val_pitch = QLabel("P: --°")
        self.val_pitch.setProperty("class", "telemetry-value")
        self.val_yaw = QLabel("Y: --°")
        self.val_yaw.setProperty("class", "telemetry-value")
        att_row.addWidget(self.val_roll)
        att_row.addWidget(self.val_pitch)
        att_row.addWidget(self.val_yaw)
        att_layout.addLayout(att_row)
        layout.addWidget(att_card)

        # Status & Navigation State
        status_grid = QGridLayout()
        status_grid.setSpacing(6)

        self.item_gps_fix = TelemetryItem("GPS FIX", "")
        self.item_sats = TelemetryItem("SATELLITES", "")
        self.item_mode = TelemetryItem("FLIGHT MODE", "")
        self.item_armed = TelemetryItem("ARM STATE", "")

        status_grid.addWidget(self.item_gps_fix, 0, 0)
        status_grid.addWidget(self.item_sats, 0, 1)
        status_grid.addWidget(self.item_mode, 1, 0)
        status_grid.addWidget(self.item_armed, 1, 1)
        layout.addLayout(status_grid)

        layout.addStretch()
        scroll.setWidget(container)
        root_layout.addWidget(scroll)

    def _connect_signals(self):
        app_state.telemetry_updated.connect(self.update_telemetry)

    def update_telemetry(self, data: dict):
        lat = data.get("lat", "--")
        lon = data.get("lon", "--")

        if isinstance(lat, float):
            self.val_lat.setText(f"LAT: {lat:.6f}°")
        else:
            self.val_lat.setText(f"LAT: {lat}")

        if isinstance(lon, float):
            self.val_lon.setText(f"LON: {lon:.6f}°")
        else:
            self.val_lon.setText(f"LON: {lon}")

        alt = data.get("alt_rel", "--")
        self.item_alt.set_value(alt)

        speed = data.get("groundspeed", data.get("ground_speed", "--"))
        self.item_speed.set_value(speed)

        heading = data.get("heading", "--")
        self.item_heading.set_value(heading)

        bat_pct = data.get("battery_pct", "--")
        self.item_battery.set_value(bat_pct)

        roll = data.get("roll", "--")
        pitch = data.get("pitch", "--")
        yaw = data.get("yaw", "--")

        self.val_roll.setText(f"R: {roll:.1f}°" if isinstance(roll, float) else f"R: {roll}")
        self.val_pitch.setText(f"P: {pitch:.1f}°" if isinstance(pitch, float) else f"P: {pitch}")
        self.val_yaw.setText(f"Y: {yaw:.1f}°" if isinstance(yaw, float) else f"Y: {yaw}")

        self.item_gps_fix.set_value(data.get("gps_fix", "--"))
        self.item_sats.set_value(data.get("satellites", "--"))
        self.item_mode.set_value(data.get("mode", "--"))

        armed = data.get("armed", "--")
        if armed is True:
            self.item_armed.set_value("ARMED")
        elif armed is False:
            self.item_armed.set_value("DISARMED")
        else:
            self.item_armed.set_value(str(armed))

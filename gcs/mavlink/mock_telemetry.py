"""Mock MAVLink Telemetry Generator.

Generates realistic telemetry streams for visual GCS testing and headless automated testing
without requiring an active ArduPilot SITL instance.
"""

import math
import time


class MockTelemetryGenerator:
    """Generates synthetic MAVLink telemetry streams for Phase 1 verification."""

    def __init__(self):
        self._base_lat = 37.7749
        self._base_lon = -122.4194
        self._base_alt = 15.5
        self._battery = 99.0

    def generate_packet(self, tick_count: int) -> dict:
        """Generate a single realistic telemetry packet dictionary."""
        t = tick_count * 0.1

        # Simulate small circular orbit
        radius = 0.00015  # ~15 meters
        lat = self._base_lat + radius * math.sin(t * 0.2)
        lon = self._base_lon + radius * math.cos(t * 0.2)
        alt_rel = self._base_alt + 1.2 * math.sin(t * 0.5)
        alt_abs = alt_rel + 45.0  # ~60.5m MSL

        heading = (t * 15.0) % 360.0
        roll = 2.5 * math.sin(t * 1.5)
        pitch = 1.8 * math.cos(t * 1.2)
        yaw = heading

        groundspeed = 3.5 + 0.8 * math.sin(t * 0.8)
        vx = groundspeed * math.cos(math.radians(heading))
        vy = groundspeed * math.sin(math.radians(heading))
        vz = 0.2 * math.cos(t * 0.5)

        # Slow battery drain
        self._battery = max(10.0, 99.0 - (t * 0.01))
        battery_v = 14.8 * (self._battery / 100.0) + 7.4  # ~4S LiPo

        return {
            "lat": lat,
            "lon": lon,
            "alt_rel": alt_rel,
            "alt_abs": alt_abs,
            "vx": vx,
            "vy": vy,
            "vz": vz,
            "groundspeed": groundspeed,
            "heading": heading,
            "roll": roll,
            "pitch": pitch,
            "yaw": yaw,
            "battery_pct": int(self._battery),
            "battery_v": round(battery_v, 2),
            "gps_fix": "3D Fix",
            "satellites": 14,
            "hdop": 0.78,
            "armed": False,
            "mode": "GUIDED",
            "system_id": 1,
            "component_id": 1,
            "autopilot": "ArduCopter",
            "connection_str": "mock://127.0.0.1:14550",
            "timestamp": time.time(),
        }

"""Virtual Communication Node Data Models and Manager for Phase 10.

Provides:
- VirtualNode dataclass storing:
  - Node ID (NODE_001, NODE_002, ...)
  - Latitude, Longitude, Altitude (e.g. 4.5m)
  - Deployment Timestamp, Mission ID
  - Operational Status (READY -> DEPLOYED -> ACTIVE -> OFFLINE)
  - RF parameters: Frequency Band (2.4GHz, 5.8GHz, 433MHz, 915MHz), Tx Power (dBm)
  - Operational Telemetry: Battery %, Packets TX/RX, Connected Clients, Coverage Radius
- VirtualNodeManager for node registration, inspection, lifecycle state transitions,
  telemetry simulation, and GeoJSON/JSON persistence.
"""

import time
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any
from PySide6.QtCore import QObject, Signal


class NodeStatus(str, Enum):
    READY = "READY"
    DEPLOYED = "DEPLOYED"
    ACTIVE = "ACTIVE"
    OFFLINE = "OFFLINE"


class FrequencyBand(str, Enum):
    BAND_2_4_GHZ = "2.4 GHz"
    BAND_5_8_GHZ = "5.8 GHz"
    BAND_915_MHZ = "915 MHz"
    BAND_433_MHZ = "433 MHz"


@dataclass
class VirtualNode:
    """Represents a deployed or ready-to-deploy virtual emergency communication node."""
    node_id: str = "NODE_001"
    lat: float = 37.7749
    lon: float = -122.4194
    altitude_m: float = 4.5
    deploy_time: str = field(default_factory=lambda: time.strftime("%H:%M:%S"))
    mission_id: str = "MIS-EMERGENCY-01"
    status: str = "READY"
    frequency_band: str = "2.4 GHz"
    frequency_mhz: float = 2400.0
    tx_power_dbm: float = 20.0
    battery_pct: float = 100.0
    packets_tx: int = 0
    packets_rx: int = 0
    connected_clients: int = 0
    coverage_radius_m: float = 250.0

    @property
    def latitude(self) -> float:
        return self.lat

    @property
    def longitude(self) -> float:
        return self.lon

    @property
    def altitude(self) -> float:
        return self.altitude_m

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "lat": round(self.lat, 7),
            "lon": round(self.lon, 7),
            "altitude_m": round(self.altitude_m, 1),
            "deploy_time": self.deploy_time,
            "mission_id": self.mission_id,
            "status": self.status,
            "frequency_band": self.frequency_band,
            "frequency_mhz": round(self.frequency_mhz, 1),
            "tx_power_dbm": round(self.tx_power_dbm, 1),
            "battery_pct": round(self.battery_pct, 1),
            "packets_tx": self.packets_tx,
            "packets_rx": self.packets_rx,
            "connected_clients": self.connected_clients,
            "coverage_radius_m": round(self.coverage_radius_m, 1),
        }

    def to_geojson_feature(self) -> Dict[str, Any]:
        return {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [round(self.lon, 7), round(self.lat, 7)]
            },
            "properties": self.to_dict()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VirtualNode":
        return cls(
            node_id=str(data.get("node_id", "NODE_001")),
            lat=float(data.get("lat", 37.7749)),
            lon=float(data.get("lon", -122.4194)),
            altitude_m=float(data.get("altitude_m", 4.5)),
            deploy_time=str(data.get("deploy_time", "")),
            mission_id=str(data.get("mission_id", "MIS-01")),
            status=str(data.get("status", "READY")),
            frequency_band=str(data.get("frequency_band", "2.4 GHz")),
            frequency_mhz=float(data.get("frequency_mhz", 2400.0)),
            tx_power_dbm=float(data.get("tx_power_dbm", 20.0)),
            battery_pct=float(data.get("battery_pct", 100.0)),
            packets_tx=int(data.get("packets_tx", 0)),
            packets_rx=int(data.get("packets_rx", 0)),
            connected_clients=int(data.get("connected_clients", 0)),
            coverage_radius_m=float(data.get("coverage_radius_m", 250.0)),
        )


class VirtualNodeManager(QObject):
    """Manages virtual communication node lifecycle, registry, and telemetry."""

    node_added = Signal(object)
    node_updated = Signal(object)
    node_selected = Signal(object)
    nodes_cleared = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._nodes: Dict[str, VirtualNode] = {}
        self._selected_node_id: Optional[str] = None
        self._next_node_num: int = 1

    @property
    def nodes(self) -> List[VirtualNode]:
        return list(self._nodes.values())

    def get_all_nodes(self) -> List[VirtualNode]:
        return list(self._nodes.values())

    @property
    def selected_node(self) -> Optional[VirtualNode]:
        if self._selected_node_id and self._selected_node_id in self._nodes:
            return self._nodes[self._selected_node_id]
        return None

    def create_next_ready_node(self, lat: float = 37.7749, lon: float = -122.4194, altitude_m: float = 4.5) -> VirtualNode:
        """Create the next un-deployed node with READY status."""
        node_id = f"NODE_{self._next_node_num:03d}"
        node = VirtualNode(
            node_id=node_id,
            lat=lat,
            lon=lon,
            altitude_m=altitude_m,
            status=NodeStatus.READY.value
        )
        return node

    def deploy_node(
        self,
        node_id: Optional[Any] = None,
        lat: float = 37.7749,
        lon: float = -122.4194,
        altitude_m: float = 4.5,
        mission_id: str = "MIS-EMERGENCY-01",
        frequency_band: str = "2.4 GHz",
        tx_power_dbm: float = 20.0,
        coverage_radius_m: float = 250.0
    ) -> VirtualNode:
        """Deploy an operational virtual communication node."""
        if isinstance(node_id, VirtualNode):
            node = node_id
            nid = node.node_id
            self._nodes[nid] = node
            self._selected_node_id = nid
            self.node_added.emit(node)
            self.node_selected.emit(node)
            from gcs.state.app_state import app_state
            app_state.add_virtual_node(node)
            return node

        if not node_id:
            node_id = f"NODE_{self._next_node_num:03d}"
            self._next_node_num += 1

        freq_map = {
            "2.4 GHz": 2400.0,
            "5.8 GHz": 5800.0,
            "915 MHz": 915.0,
            "433 MHz": 433.0,
        }
        freq_mhz = freq_map.get(frequency_band, 2400.0)

        node = VirtualNode(
            node_id=node_id,
            lat=lat,
            lon=lon,
            altitude_m=altitude_m,
            deploy_time=time.strftime("%H:%M:%S"),
            mission_id=mission_id,
            status=NodeStatus.ACTIVE.value,
            frequency_band=frequency_band,
            frequency_mhz=freq_mhz,
            tx_power_dbm=tx_power_dbm,
            battery_pct=100.0,
            packets_tx=12,
            packets_rx=8,
            connected_clients=2,
            coverage_radius_m=coverage_radius_m
        )
        self._nodes[node_id] = node
        self._selected_node_id = node_id

        self.node_added.emit(node)
        self.node_selected.emit(node)

        from gcs.state.app_state import app_state
        app_state.add_virtual_node(node)
        return node

    def get_node(self, node_id: str) -> Optional[VirtualNode]:
        """Retrieve node by ID."""
        return self._nodes.get(node_id)

    def select_node(self, node_id: str) -> Optional[VirtualNode]:
        """Focus a specific node for telemetry inspection."""
        if node_id in self._nodes:
            self._selected_node_id = node_id
            node = self._nodes[node_id]
            self.node_selected.emit(node)
            from gcs.state.app_state import app_state
            app_state.select_virtual_node(node_id)
            return node
        return None

    def update_telemetry(
        self,
        node_id: str,
        battery_pct: Optional[float] = None,
        packets_tx: Optional[int] = None,
        packets_rx: Optional[int] = None,
        connected_clients: Optional[int] = None,
        add_packets: int = 0,
        add_clients: int = 0
    ) -> bool:
        """Simulate or update real-time node operational telemetry."""
        if node_id in self._nodes:
            node = self._nodes[node_id]
            if battery_pct is not None:
                node.battery_pct = max(0.0, min(100.0, battery_pct))
            if packets_tx is not None:
                node.packets_tx = packets_tx
            elif add_packets > 0:
                node.packets_tx += add_packets
            if packets_rx is not None:
                node.packets_rx = packets_rx
            elif add_packets > 0:
                node.packets_rx += max(0, add_packets - 1)
            if connected_clients is not None:
                node.connected_clients = max(0, connected_clients)
            elif add_clients != 0:
                node.connected_clients = max(0, node.connected_clients + add_clients)
            self.node_updated.emit(node)
            return True
        return False

    def clear(self):
        """Clear all registered virtual nodes."""
        self._nodes.clear()
        self._selected_node_id = None
        self._next_node_num = 1
        self.nodes_cleared.emit()
        from gcs.state.app_state import app_state
        app_state.clear_virtual_nodes()

    clear_nodes = clear

    def to_geojson(self, as_dict: bool = False) -> Any:
        """Export virtual nodes as GeoJSON FeatureCollection."""
        features = []
        for n in self.nodes:
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [n.lon, n.lat, n.altitude_m]
                },
                "properties": n.to_dict()
            }
            features.append(feature)
        data = {
            "type": "FeatureCollection",
            "metadata": {
                "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
                "total_nodes": len(self.nodes),
            },
            "features": features
        }
        return data if as_dict else json.dumps(data, indent=2)

    def to_geojson_dict(self) -> Dict[str, Any]:
        return self.to_geojson(as_dict=True)


# Global singleton instance
virtual_node_manager = VirtualNodeManager()

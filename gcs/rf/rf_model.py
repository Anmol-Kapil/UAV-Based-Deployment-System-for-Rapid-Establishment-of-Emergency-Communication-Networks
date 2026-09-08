"""Simulated RF Propagation Engine for Phase 11.

Implements standard empirical radio propagation physics:
1. Free Space Path Loss (FSPL) calibration at reference distance d0:
   PL(d0) = 20*log10(f_MHz) + 20*log10(d0_m) - 27.55
2. Log-Distance Path Loss Model:
   PL(d) = PL(d0) + 10 * n * log10(d / d0) + X_sigma
3. Received Signal Strength Indication (RSSI):
   RSSI(d) = P_tx + G_tx + G_rx - PL(d)
4. Theoretical Coverage Radius Inversion (solved at receiver sensitivity threshold P_rx_sens):
   R_cov = d0 * 10^((P_tx + G_tx + G_rx - PL(d0) - P_rx_sens) / (10 * n))

Supports multi-band frequency presets:
- 2.4 GHz (WiFi / 802.11 b/g/n, f = 2400 MHz)
- 5.8 GHz (High-throughput ISM, f = 5800 MHz)
- 915 MHz (LoRa / 900MHz ISM US, f = 915 MHz)
- 433 MHz (Telemetry / UHF, f = 433 MHz)

Clearly labeled as SIMULATED RF per engineering GCS specification.
"""

import math
import random
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from PySide6.QtCore import QObject, Signal

from gcs.deployment.deployment_manager import calculate_ground_distance


@dataclass
class RfConfig:
    """RF simulation configuration parameters."""
    frequency_band: str = "2.4 GHz"
    frequency_mhz: float = 2400.0
    tx_power_dbm: float = 20.0
    tx_gain_dbi: float = 2.15
    rx_gain_dbi: float = 2.15
    ref_distance_m: float = 1.0
    path_loss_exponent: float = 2.5
    environment_name: str = "Suburban Disaster (2.5)"
    rx_sensitivity_dbm: float = -75.0
    shadowing_std_db: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "frequency_band": self.frequency_band,
            "frequency_mhz": round(self.frequency_mhz, 1),
            "tx_power_dbm": round(self.tx_power_dbm, 1),
            "tx_gain_dbi": round(self.tx_gain_dbi, 2),
            "rx_gain_dbi": round(self.rx_gain_dbi, 2),
            "ref_distance_m": round(self.ref_distance_m, 2),
            "path_loss_exponent": round(self.path_loss_exponent, 2),
            "environment_name": self.environment_name,
            "rx_sensitivity_dbm": round(self.rx_sensitivity_dbm, 1),
            "shadowing_std_db": round(self.shadowing_std_db, 1),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RfConfig":
        return cls(
            frequency_band=str(d.get("frequency_band", "2.4 GHz")),
            frequency_mhz=float(d.get("frequency_mhz", 2400.0)),
            tx_power_dbm=float(d.get("tx_power_dbm", 20.0)),
            tx_gain_dbi=float(d.get("tx_gain_dbi", 2.15)),
            rx_gain_dbi=float(d.get("rx_gain_dbi", 2.15)),
            ref_distance_m=float(d.get("ref_distance_m", 1.0)),
            path_loss_exponent=float(d.get("path_loss_exponent", 2.5)),
            environment_name=str(d.get("environment_name", "Suburban Disaster (2.5)")),
            rx_sensitivity_dbm=float(d.get("rx_sensitivity_dbm", -75.0)),
            shadowing_std_db=float(d.get("shadowing_std_db", 0.0)),
        )


@dataclass
class RfCalculationResult:
    """Theoretical RF coverage and link calculation metrics."""
    fspl_at_d0_db: float = 40.05
    max_allowable_path_loss_db: float = 99.3
    coverage_radius_m: float = 248.6
    coverage_area_m2: float = 194156.0
    coverage_area_km2: float = 0.194
    eirp_dbm: float = 22.15

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fspl_at_d0_db": round(self.fspl_at_d0_db, 2),
            "max_allowable_path_loss_db": round(self.max_allowable_path_loss_db, 2),
            "coverage_radius_m": round(self.coverage_radius_m, 1),
            "coverage_area_m2": round(self.coverage_area_m2, 1),
            "coverage_area_km2": round(self.coverage_area_km2, 3),
            "eirp_dbm": round(self.eirp_dbm, 2),
        }


class RfPropagationEngine(QObject):
    """Calculates theoretical and simulated RF propagation metrics."""

    calculation_updated = Signal(object)
    uav_link_updated = Signal(object)

    ENV_PRESETS = {
        "Free Space (2.0)": 2.0,
        "Rural / Open Field (2.2)": 2.2,
        "Suburban Disaster (2.5)": 2.5,
        "Urban / Light Debris (3.0)": 3.0,
        "Dense Urban / Forest (3.8)": 3.8,
    }

    BAND_PRESETS = {
        "2.4 GHz": 2400.0,
        "5.8 GHz": 5800.0,
        "915 MHz": 915.0,
        "433 MHz": 433.0,
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = RfConfig()
        self.last_result = self.calculate_coverage(self.config)

    def calculate_fspl_d0(self, freq_mhz: float, d0_m: float = 1.0) -> float:
        """Calculate Free Space Path Loss at reference distance d0 in dB.

        FSPL(d0) = 20*log10(f_MHz) + 20*log10(d0_m) - 27.55
        """
        f = max(1.0, freq_mhz)
        d0 = max(0.01, d0_m)
        return 20.0 * math.log10(f) + 20.0 * math.log10(d0) - 27.55

    def calculate_path_loss(self, distance_m: float, config: Optional[Any] = None) -> float:
        """Calculate path loss in dB at distance_m using Log-Distance model.

        PL(d) = PL(d0) + 10 * n * log10(d / d0)
        """
        cfg = config or self.config
        if isinstance(cfg, dict):
            cfg = RfConfig.from_dict(cfg)
        d0 = max(0.01, cfg.ref_distance_m)
        d = max(d0, distance_m)
        pl_d0 = self.calculate_fspl_d0(cfg.frequency_mhz, d0)
        pl = pl_d0 + 10.0 * cfg.path_loss_exponent * math.log10(d / d0)
        if cfg.shadowing_std_db > 0.0:
            # Deterministic/Gaussian shadow fading
            pl += random.gauss(0.0, cfg.shadowing_std_db)
        return pl

    def calculate_rssi(
        self,
        distance_m: float,
        config: Optional[Any] = None,
        apply_shadowing: bool = False,
        with_shadowing: bool = False,
        custom_tx_pwr_dbm: Optional[float] = None,
        tx_power_dbm: Optional[float] = None,
        **kwargs
    ) -> float:
        """Calculate received signal strength indication (RSSI) in dBm.

        RSSI = P_tx + G_tx + G_rx - PL(d)
        """
        cfg = config or self.config
        if isinstance(cfg, dict):
            cfg = RfConfig.from_dict(cfg)
        use_shadow = apply_shadowing or with_shadowing
        pl = self.calculate_path_loss(distance_m, cfg)
        if not use_shadow and cfg.shadowing_std_db > 0.0:
            # Recompute without random shadow for deterministic display
            d0 = max(0.01, cfg.ref_distance_m)
            d = max(d0, distance_m)
            pl = self.calculate_fspl_d0(cfg.frequency_mhz, d0) + 10.0 * cfg.path_loss_exponent * math.log10(d / d0)
        pwr_override = tx_power_dbm if tx_power_dbm is not None else custom_tx_pwr_dbm
        tx_pwr = pwr_override if pwr_override is not None else cfg.tx_power_dbm
        rssi = tx_pwr + cfg.tx_gain_dbi + cfg.rx_gain_dbi - pl
        return rssi

    def calculate_coverage_radius(self, config: Optional[Any] = None) -> float:
        """Calculate theoretical coverage radius R_cov in meters where RSSI = rx_sensitivity.

        R_cov = d0 * 10^((P_tx + G_tx + G_rx - PL(d0) - P_rx_sens) / (10 * n))
        """
        cfg = config or self.config
        if isinstance(cfg, dict):
            cfg = RfConfig.from_dict(cfg)
        d0 = max(0.01, cfg.ref_distance_m)
        pl_d0 = self.calculate_fspl_d0(cfg.frequency_mhz, d0)
        total_eirp = cfg.tx_power_dbm + cfg.tx_gain_dbi + cfg.rx_gain_dbi
        max_allowable_pl = total_eirp - cfg.rx_sensitivity_dbm

        # Exponent numerator
        delta_pl = max_allowable_pl - pl_d0
        if delta_pl <= 0:
            return d0

        exponent = delta_pl / (10.0 * max(0.1, cfg.path_loss_exponent))
        radius = d0 * math.pow(10.0, exponent)
        # Cap radius within realistic terrestrial bounds (e.g. 5 km max)
        return max(d0, min(5000.0, radius))

    def calculate_coverage(self, config: Optional[RfConfig] = None) -> RfCalculationResult:
        """Calculate full RF model coverage metrics."""
        cfg = config or self.config
        self.config = cfg
        d0 = max(0.01, cfg.ref_distance_m)
        fspl_d0 = self.calculate_fspl_d0(cfg.frequency_mhz, d0)
        eirp = cfg.tx_power_dbm + cfg.tx_gain_dbi
        total_gain_link = cfg.tx_power_dbm + cfg.tx_gain_dbi + cfg.rx_gain_dbi
        max_pl = total_gain_link - cfg.rx_sensitivity_dbm

        radius = self.calculate_coverage_radius(cfg)
        area_m2 = math.pi * (radius ** 2)
        area_km2 = area_m2 / 1e6

        result = RfCalculationResult(
            fspl_at_d0_db=fspl_d0,
            max_allowable_path_loss_db=max_pl,
            coverage_radius_m=radius,
            coverage_area_m2=area_m2,
            coverage_area_km2=area_km2,
            eirp_dbm=eirp
        )
        self.last_result = result
        self.calculation_updated.emit(result)
        return result

    def estimate_uav_link(
        self,
        uav_lat: float,
        uav_lon: float,
        uav_alt_m: float,
        nodes: List[Any],
        config: Optional[RfConfig] = None
    ) -> Dict[str, Any]:
        """Estimate real-time RF link between UAV and nearest deployed communication node."""
        cfg = config or self.config
        if not nodes:
            return {
                "connected": False,
                "node_id": "NONE",
                "ground_dist_m": 0.0,
                "dist_3d_m": 0.0,
                "rssi_dbm": -120.0,
                "quality": "NO COVERAGE",
                "color": "#8b949e"
            }

        best_node_id = "NONE"
        best_rssi = -999.0
        min_dist_3d = float("inf")
        min_ground_dist = 0.0

        for n in nodes:
            n_dict = n.to_dict() if hasattr(n, "to_dict") else n
            n_lat = float(n_dict.get("lat", 0.0))
            n_lon = float(n_dict.get("lon", 0.0))
            n_alt = float(n_dict.get("altitude_m", n_dict.get("alt", 4.5)))
            nid = str(n_dict.get("node_id", "NODE"))

            # Calculate 3D slant distance
            g_dist = calculate_ground_distance(uav_lat, uav_lon, n_lat, n_lon)
            d_alt = abs(uav_alt_m - n_alt)
            dist_3d = math.hypot(g_dist, d_alt)

            # Calculate RSSI from this node
            node_freq_band = n_dict.get("frequency_band", cfg.frequency_band)
            node_freq_mhz = self.BAND_PRESETS.get(node_freq_band, cfg.frequency_mhz)
            node_tx_pwr = float(n_dict.get("tx_power_dbm", cfg.tx_power_dbm))

            node_cfg = RfConfig(
                frequency_band=node_freq_band,
                frequency_mhz=node_freq_mhz,
                tx_power_dbm=node_tx_pwr,
                tx_gain_dbi=cfg.tx_gain_dbi,
                rx_gain_dbi=cfg.rx_gain_dbi,
                ref_distance_m=cfg.ref_distance_m,
                path_loss_exponent=cfg.path_loss_exponent,
                rx_sensitivity_dbm=cfg.rx_sensitivity_dbm,
                shadowing_std_db=cfg.shadowing_std_db
            )

            rssi = self.calculate_rssi(dist_3d, node_cfg, apply_shadowing=False)
            if rssi > best_rssi:
                best_rssi = rssi
                best_node_id = nid
                min_dist_3d = dist_3d
                min_ground_dist = g_dist

        # Quality classification
        if best_rssi >= -65.0:
            quality = "EXCELLENT"
            color = "#3fb950"  # Green
        elif best_rssi >= -75.0:
            quality = "GOOD"
            color = "#58a6ff"  # Blue
        elif best_rssi >= -85.0:
            quality = "WEAK / MARGINAL"
            color = "#d29922"  # Amber
        else:
            quality = "NO COVERAGE"
            color = "#f85149"  # Red

        link_info = {
            "connected": best_rssi >= cfg.rx_sensitivity_dbm,
            "node_id": best_node_id,
            "ground_dist_m": round(min_ground_dist, 1),
            "dist_3d_m": round(min_dist_3d, 1),
            "rssi_dbm": round(best_rssi, 1),
            "quality": quality,
            "color": color
        }
        self.uav_link_updated.emit(link_info)
        return link_info


# Global singleton
rf_engine = RfPropagationEngine()

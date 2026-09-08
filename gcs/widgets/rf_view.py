"""Simulated RF Propagation Model Console for Right Context Panel (Phase 11).

Provides:
- RF Configuration Panel matching user specification (Section 22):
  - Frequency Band & Center Frequency (2.4GHz, 5.8GHz, 915MHz, 433MHz)
  - Transmit Power (dBm), Reference Distance d0 (m)
  - Path Loss Exponent n (with environment presets: Free Space, Rural, Suburban, Urban, Dense)
  - Receiver Sensitivity Threshold (dBm) & Shadow Fading
- [CALCULATE COVERAGE] theoretical physics engine calculation
- [APPLY TO VIRTUAL NODES] network-wide coverage footprint updater
- Real-time UAV RF Link Telemetry (instantaneous RSSI & link quality badge)
- High-contrast tactical styling with explicit [SIMULATED RF] safety badge
"""

import math
from typing import Optional, Dict, Any
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QFrame,
    QDoubleSpinBox,
    QComboBox,
    QScrollArea,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from gcs.state.app_state import app_state
from gcs.rf.rf_model import RfConfig, RfCalculationResult, rf_engine
from gcs.deployment.virtual_node_manager import virtual_node_manager
from gcs.rf.rf_survey_controller import (
    rf_survey_controller,
    SurveyStatus,
    SurveyMetrics,
    SurveySample,
)
from gcs.rf.survey_generator import SurveyPlan
from gcs.rf.rf_heatmap import (
    RfHeatmapEngine,
    RfAnalysisResult,
    RfCategory,
    CATEGORY_COLORS,
)
from gcs.rf.coverage_gap_analyzer import (
    CoverageGapAnalyzer,
    coverage_gap_analyzer,
    GapZone,
    CoverageAnalysisReport,
    CoverageRegionType,
)


class RFView(QWidget):
    """Simulated RF Model Configuration and Propagation Console."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("rfView")
        self._init_ui()
        self._connect_signals()
        # Perform initial calculation
        self._on_calculate_coverage()

    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # 1. Header Card with Prominent [SIMULATED RF] Label
        header_card = QFrame()
        header_card.setProperty("class", "telemetry-card")
        h_layout = QVBoxLayout(header_card)
        h_layout.setContentsMargins(8, 6, 8, 6)
        h_layout.setSpacing(4)

        h_top = QHBoxLayout()
        title = QLabel("RF PROPAGATION MODEL")
        title.setStyleSheet("font-weight: 700; color: #58a6ff; font-size: 11px;")
        h_top.addWidget(title)
        h_top.addStretch()

        self.lbl_sim_badge = QLabel("SIMULATED RF")
        self.lbl_sim_badge.setStyleSheet(
            "background-color: #1f6feb; color: #ffffff; font-size: 9px; font-weight: 800; "
            "padding: 2px 6px; border-radius: 3px; letter-spacing: 0.5px;"
        )
        self.lbl_sim_badge.setToolTip("Mathematical empirical propagation model — not physical hardware readings")
        h_top.addWidget(self.lbl_sim_badge)
        h_layout.addLayout(h_top)

        sub_desc = QLabel("Log-Distance Path Loss model predicting RF coverage footprint & link RSSI.")
        sub_desc.setStyleSheet("font-size: 9px; color: #8b949e;")
        sub_desc.setWordWrap(True)
        h_layout.addWidget(sub_desc)
        layout.addWidget(header_card)

        # 2. RF Configuration Parameters Card (Exact match to Phase 11 Spec)
        cfg_card = QFrame()
        cfg_card.setProperty("class", "telemetry-card")
        c_layout = QVBoxLayout(cfg_card)
        c_layout.setContentsMargins(8, 6, 8, 6)
        c_layout.setSpacing(6)

        lbl_cfg_title = QLabel("RF CONFIGURATION PARAMETERS")
        lbl_cfg_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #79c0ff;")
        c_layout.addWidget(lbl_cfg_title)

        grid = QGridLayout()
        grid.setSpacing(6)

        # Row 0: Frequency Band & Center Freq
        lbl_band = QLabel("Frequency Band:")
        lbl_band.setStyleSheet("font-size: 9px; color: #c9d1d9;")
        grid.addWidget(lbl_band, 0, 0)
        self.combo_band = QComboBox()
        self.combo_band.addItems(["2.4 GHz", "5.8 GHz", "915 MHz", "433 MHz"])
        self.combo_band.setStyleSheet("font-size: 9px;")
        self.combo_band.currentTextChanged.connect(self._on_band_changed)
        grid.addWidget(self.combo_band, 0, 1)

        lbl_freq = QLabel("Center Freq:")
        lbl_freq.setStyleSheet("font-size: 9px; color: #c9d1d9;")
        grid.addWidget(lbl_freq, 0, 2)
        self.spin_freq = QDoubleSpinBox()
        self.spin_freq.setRange(100.0, 10000.0)
        self.spin_freq.setValue(2400.0)
        self.spin_freq.setSuffix(" MHz")
        self.spin_freq.setStyleSheet("font-size: 9px; font-family: Consolas, monospace;")
        grid.addWidget(self.spin_freq, 0, 3)

        # Row 1: Tx Power & Reference Distance d0
        lbl_tx = QLabel("Tx Power:")
        lbl_tx.setStyleSheet("font-size: 9px; color: #c9d1d9;")
        grid.addWidget(lbl_tx, 1, 0)
        self.spin_tx_pwr = QDoubleSpinBox()
        self.spin_tx_pwr.setRange(0.0, 40.0)
        self.spin_tx_pwr.setValue(20.0)
        self.spin_tx_pwr.setSuffix(" dBm")
        self.spin_tx_pwr.setStyleSheet("font-size: 9px; font-family: Consolas, monospace;")
        grid.addWidget(self.spin_tx_pwr, 1, 1)

        lbl_d0 = QLabel("Reference d₀:")
        lbl_d0.setStyleSheet("font-size: 9px; color: #c9d1d9;")
        grid.addWidget(lbl_d0, 1, 2)
        self.spin_d0 = QDoubleSpinBox()
        self.spin_d0.setRange(0.1, 10.0)
        self.spin_d0.setValue(1.0)
        self.spin_d0.setSuffix(" m")
        self.spin_d0.setStyleSheet("font-size: 9px; font-family: Consolas, monospace;")
        grid.addWidget(self.spin_d0, 1, 3)

        # Row 2: Environment Preset & Path Loss Exponent n
        lbl_env = QLabel("Environment:")
        lbl_env.setStyleSheet("font-size: 9px; color: #c9d1d9;")
        grid.addWidget(lbl_env, 2, 0)
        self.combo_env = QComboBox()
        self.combo_env.addItems(list(rf_engine.ENV_PRESETS.keys()))
        self.combo_env.setCurrentText("Suburban Disaster (2.5)")
        self.combo_env.setStyleSheet("font-size: 9px;")
        self.combo_env.currentTextChanged.connect(self._on_env_changed)
        grid.addWidget(self.combo_env, 2, 1)

        lbl_n = QLabel("Path Loss n:")
        lbl_n.setStyleSheet("font-size: 9px; color: #c9d1d9;")
        grid.addWidget(lbl_n, 2, 2)
        self.spin_n = QDoubleSpinBox()
        self.spin_n.setRange(1.2, 5.5)
        self.spin_n.setDecimals(2)
        self.spin_n.setValue(2.5)
        self.spin_n.setStyleSheet("font-size: 9px; font-family: Consolas, monospace;")
        grid.addWidget(self.spin_n, 2, 3)

        # Row 3: Receiver Sensitivity / RSSI Threshold & Shadowing
        lbl_sens = QLabel("RSSI Threshold:")
        lbl_sens.setStyleSheet("font-size: 9px; color: #c9d1d9;")
        grid.addWidget(lbl_sens, 3, 0)
        self.spin_rx_sens = QDoubleSpinBox()
        self.spin_rx_sens.setRange(-120.0, -30.0)
        self.spin_rx_sens.setValue(-75.0)
        self.spin_rx_sens.setSuffix(" dBm")
        self.spin_rx_sens.setStyleSheet("font-size: 9px; font-family: Consolas, monospace;")
        grid.addWidget(self.spin_rx_sens, 3, 1)

        lbl_sh = QLabel("Shadowing σ:")
        lbl_sh.setStyleSheet("font-size: 9px; color: #c9d1d9;")
        grid.addWidget(lbl_sh, 2, 2)
        self.spin_shadow = QDoubleSpinBox()
        self.spin_shadow.setRange(0.0, 10.0)
        self.spin_shadow.setValue(0.0)
        self.spin_shadow.setSuffix(" dB")
        self.spin_shadow.setStyleSheet("font-size: 9px; font-family: Consolas, monospace;")
        grid.addWidget(self.spin_shadow, 3, 3)

        c_layout.addLayout(grid)

        # Action Buttons Row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self.btn_calc = QPushButton("CALCULATE COVERAGE")
        self.btn_calc.setFixedHeight(28)
        self.btn_calc.setStyleSheet("""
            QPushButton {
                background-color: #238636;
                color: #ffffff;
                font-size: 10px;
                font-weight: 800;
                letter-spacing: 0.5px;
                border-radius: 3px;
                border: 1px solid #2ea043;
            }
            QPushButton:hover {
                background-color: #2ea043;
            }
        """)
        self.btn_calc.clicked.connect(self._on_calculate_coverage)
        btn_row.addWidget(self.btn_calc)

        self.btn_apply_nodes = QPushButton("Apply to Virtual Nodes")
        self.btn_apply_nodes.setFixedHeight(28)
        self.btn_apply_nodes.setStyleSheet("""
            QPushButton {
                background-color: #21262d;
                color: #58a6ff;
                font-size: 9px;
                font-weight: 700;
                border-radius: 3px;
                border: 1px solid #30363d;
            }
            QPushButton:hover {
                background-color: #30363d;
            }
        """)
        self.btn_apply_nodes.clicked.connect(self._on_apply_to_virtual_nodes)
        btn_row.addWidget(self.btn_apply_nodes)
        c_layout.addLayout(btn_row)

        layout.addWidget(cfg_card)

        # 3. Calculated Coverage & Link Budget Metrics Card
        res_card = QFrame()
        res_card.setProperty("class", "telemetry-card")
        r_layout = QVBoxLayout(res_card)
        r_layout.setContentsMargins(8, 6, 8, 6)
        r_layout.setSpacing(6)

        r_title = QLabel("CALCULATED RF COVERAGE (SIMULATED)")
        r_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #3fb950;")
        r_layout.addWidget(r_title)

        # Big Hero Radius Readout
        radius_row = QHBoxLayout()
        lbl_rad_head = QLabel("Theoretical Coverage Radius:")
        lbl_rad_head.setStyleSheet("font-size: 10px; color: #8b949e;")
        radius_row.addWidget(lbl_rad_head)
        radius_row.addStretch()

        self.lbl_radius_val = QLabel("248.6 m")
        self.lbl_radius_val.setStyleSheet("font-size: 14px; font-weight: 800; color: #3fb950; font-family: Consolas, monospace;")
        radius_row.addWidget(self.lbl_radius_val)
        r_layout.addLayout(radius_row)

        # Secondary metrics grid
        m_grid = QGridLayout()
        m_grid.setSpacing(4)

        lbl_a = QLabel("Coverage Area:")
        lbl_a.setStyleSheet("font-size: 9px; color: #8b949e;")
        m_grid.addWidget(lbl_a, 0, 0)
        self.lbl_area_val = QLabel("0.19 km² (19.4 ha)")
        self.lbl_area_val.setStyleSheet("font-size: 9px; font-weight: 600; color: #c9d1d9; font-family: Consolas, monospace;")
        m_grid.addWidget(self.lbl_area_val, 0, 1)

        lbl_pl0 = QLabel("FSPL @ 1m (d₀):")
        lbl_pl0.setStyleSheet("font-size: 9px; color: #8b949e;")
        m_grid.addWidget(lbl_pl0, 0, 2)
        self.lbl_fspl_val = QLabel("40.0 dB")
        self.lbl_fspl_val.setStyleSheet("font-size: 9px; font-weight: 600; color: #c9d1d9; font-family: Consolas, monospace;")
        m_grid.addWidget(self.lbl_fspl_val, 0, 3)

        lbl_mpl = QLabel("Max Path Loss:")
        lbl_mpl.setStyleSheet("font-size: 9px; color: #8b949e;")
        m_grid.addWidget(lbl_mpl, 1, 0)
        self.lbl_max_pl = QLabel("99.3 dB")
        self.lbl_max_pl.setStyleSheet("font-size: 9px; font-weight: 600; color: #c9d1d9; font-family: Consolas, monospace;")
        m_grid.addWidget(self.lbl_max_pl, 1, 1)

        lbl_eirp = QLabel("EIRP (Tx + Ant):")
        lbl_eirp.setStyleSheet("font-size: 9px; color: #8b949e;")
        m_grid.addWidget(lbl_eirp, 1, 2)
        self.lbl_eirp_val = QLabel("22.2 dBm")
        self.lbl_eirp_val.setStyleSheet("font-size: 9px; font-weight: 600; color: #c9d1d9; font-family: Consolas, monospace;")
        m_grid.addWidget(self.lbl_eirp_val, 1, 3)

        r_layout.addLayout(m_grid)
        layout.addWidget(res_card)

        # 4. Real-Time UAV RF Link Telemetry Card
        link_card = QFrame()
        link_card.setProperty("class", "telemetry-card")
        l_layout = QVBoxLayout(link_card)
        l_layout.setContentsMargins(8, 6, 8, 6)
        l_layout.setSpacing(6)

        l_top = QHBoxLayout()
        l_title = QLabel("REAL-TIME UAV RF LINK")
        l_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #58a6ff;")
        l_top.addWidget(l_title)
        l_top.addStretch()

        self.lbl_link_status_badge = QLabel("NO NODES")
        self.lbl_link_status_badge.setStyleSheet(
            "background-color: #21262d; color: #8b949e; font-size: 9px; font-weight: 700; "
            "padding: 2px 6px; border-radius: 3px; border: 1px solid #30363d;"
        )
        l_top.addWidget(self.lbl_link_status_badge)
        l_layout.addLayout(l_top)

        l_grid = QGridLayout()
        l_grid.setSpacing(4)

        lbl_near = QLabel("Nearest Relay:")
        lbl_near.setStyleSheet("font-size: 9px; color: #8b949e;")
        l_grid.addWidget(lbl_near, 0, 0)
        self.lbl_near_node = QLabel("--")
        self.lbl_near_node.setStyleSheet("font-size: 9px; font-weight: 700; color: #58a6ff; font-family: Consolas, monospace;")
        l_grid.addWidget(self.lbl_near_node, 0, 1)

        lbl_dist = QLabel("3D Distance:")
        lbl_dist.setStyleSheet("font-size: 9px; color: #8b949e;")
        l_grid.addWidget(lbl_dist, 0, 2)
        self.lbl_link_dist = QLabel("-- m")
        self.lbl_link_dist.setStyleSheet("font-size: 9px; font-weight: 600; color: #c9d1d9; font-family: Consolas, monospace;")
        l_grid.addWidget(self.lbl_link_dist, 0, 3)

        lbl_rssi = QLabel("Simulated RSSI:")
        lbl_rssi.setStyleSheet("font-size: 9px; color: #8b949e;")
        l_grid.addWidget(lbl_rssi, 1, 0)
        self.lbl_link_rssi = QLabel("-- dBm")
        self.lbl_link_rssi.setStyleSheet("font-size: 11px; font-weight: 800; color: #79c0ff; font-family: Consolas, monospace;")
        l_grid.addWidget(self.lbl_link_rssi, 1, 1)

        lbl_margin = QLabel("Link Margin:")
        lbl_margin.setStyleSheet("font-size: 9px; color: #8b949e;")
        l_grid.addWidget(lbl_margin, 1, 2)
        self.lbl_link_margin = QLabel("-- dB")
        self.lbl_link_margin.setStyleSheet("font-size: 9px; font-weight: 600; color: #c9d1d9; font-family: Consolas, monospace;")
        l_grid.addWidget(self.lbl_link_margin, 1, 3)

        l_layout.addLayout(l_grid)
        layout.addWidget(link_card)

        # 5. Phase 12: RF Survey Planning Card (Section 23 Specification)
        survey_card = QFrame()
        survey_card.setProperty("class", "telemetry-card")
        s_layout = QVBoxLayout(survey_card)
        s_layout.setContentsMargins(8, 6, 8, 6)
        s_layout.setSpacing(6)

        s_top = QHBoxLayout()
        s_title = QLabel("RF SURVEY")
        s_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #58a6ff;")
        s_top.addWidget(s_title)
        s_top.addStretch()

        self.lbl_survey_status_badge = QLabel("IDLE")
        self.lbl_survey_status_badge.setStyleSheet(
            "background-color: #21262d; color: #8b949e; font-size: 9px; font-weight: 800; "
            "padding: 2px 6px; border-radius: 3px; border: 1px solid #30363d;"
        )
        s_top.addWidget(self.lbl_survey_status_badge)
        s_layout.addLayout(s_top)

        # Survey Grid parameters matching Section 23
        s_grid = QGridLayout()
        s_grid.setHorizontalSpacing(8)
        s_grid.setVerticalSpacing(4)

        # Survey Altitude
        lbl_s_alt = QLabel("Survey altitude:")
        lbl_s_alt.setStyleSheet("font-size: 9px; color: #8b949e;")
        self.spin_survey_alt = QDoubleSpinBox()
        self.spin_survey_alt.setRange(5.0, 200.0)
        self.spin_survey_alt.setValue(20.0)
        self.spin_survey_alt.setSingleStep(5.0)
        self.spin_survey_alt.setSuffix(" m")
        self.spin_survey_alt.setStyleSheet("font-size: 9px;")
        s_grid.addWidget(lbl_s_alt, 0, 0)
        s_grid.addWidget(self.spin_survey_alt, 0, 1)

        # Line Spacing
        lbl_s_spc = QLabel("Line spacing:")
        lbl_s_spc.setStyleSheet("font-size: 9px; color: #8b949e;")
        self.spin_survey_spacing = QDoubleSpinBox()
        self.spin_survey_spacing.setRange(5.0, 100.0)
        self.spin_survey_spacing.setValue(20.0)
        self.spin_survey_spacing.setSingleStep(5.0)
        self.spin_survey_spacing.setSuffix(" m")
        self.spin_survey_spacing.setStyleSheet("font-size: 9px;")
        s_grid.addWidget(lbl_s_spc, 1, 0)
        s_grid.addWidget(self.spin_survey_spacing, 1, 1)

        # Area
        lbl_s_area = QLabel("Area:")
        lbl_s_area.setStyleSheet("font-size: 9px; color: #8b949e;")
        self.lbl_survey_area = QLabel("1.200 km²")
        self.lbl_survey_area.setStyleSheet("font-size: 9px; font-weight: 700; color: #c9d1d9; font-family: Consolas, monospace;")
        s_grid.addWidget(lbl_s_area, 2, 0)
        s_grid.addWidget(self.lbl_survey_area, 2, 1)

        # Pattern
        lbl_s_pat = QLabel("Pattern:")
        lbl_s_pat.setStyleSheet("font-size: 9px; color: #8b949e;")
        self.lbl_survey_pattern = QLabel("LAWNMOWER")
        self.lbl_survey_pattern.setStyleSheet("font-size: 9px; font-weight: 700; color: #79c0ff;")
        s_grid.addWidget(lbl_s_pat, 3, 0)
        s_grid.addWidget(self.lbl_survey_pattern, 3, 1)

        # Points
        lbl_s_pts = QLabel("Points:")
        lbl_s_pts.setStyleSheet("font-size: 9px; color: #8b949e;")
        self.lbl_survey_points = QLabel("64")
        self.lbl_survey_points.setStyleSheet("font-size: 9px; font-weight: 700; color: #c9d1d9; font-family: Consolas, monospace;")
        s_grid.addWidget(lbl_s_pts, 4, 0)
        s_grid.addWidget(self.lbl_survey_points, 4, 1)

        s_layout.addLayout(s_grid)

        # Primary Action Buttons
        btn_layout = QHBoxLayout()
        self.btn_gen_survey = QPushButton("GENERATE SURVEY")
        self.btn_gen_survey.setStyleSheet(
            "background-color: #1f6feb; color: #ffffff; font-weight: 700; font-size: 9px; padding: 4px;"
        )
        btn_layout.addWidget(self.btn_gen_survey)

        self.btn_start_survey = QPushButton("START SURVEY")
        self.btn_start_survey.setEnabled(False)
        self.btn_start_survey.setStyleSheet(
            "background-color: #238636; color: #ffffff; font-weight: 700; font-size: 9px; padding: 4px;"
        )
        btn_layout.addWidget(self.btn_start_survey)

        self.btn_stop_survey = QPushButton("STOP SURVEY")
        self.btn_stop_survey.setEnabled(False)
        self.btn_stop_survey.setStyleSheet(
            "background-color: #da3633; color: #ffffff; font-weight: 700; font-size: 9px; padding: 4px;"
        )
        btn_layout.addWidget(self.btn_stop_survey)

        s_layout.addLayout(btn_layout)

        # Clear button
        self.btn_clear_survey = QPushButton("CLEAR SURVEY")
        self.btn_clear_survey.setStyleSheet("font-size: 8px; color: #8b949e; padding: 2px;")
        s_layout.addWidget(self.btn_clear_survey)

        layout.addWidget(survey_card)

        # 6. Real-Time Survey Progress Card (Matching Section 23 Specification)
        self.progress_card = QFrame()
        self.progress_card.setProperty("class", "telemetry-card")
        p_layout = QVBoxLayout(self.progress_card)
        p_layout.setContentsMargins(8, 6, 8, 6)
        p_layout.setSpacing(4)

        p_title = QLabel("SURVEY TELEMETRY (REAL-TIME)")
        p_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #7ee787;")
        p_layout.addWidget(p_title)

        p_grid = QGridLayout()
        p_grid.setHorizontalSpacing(8)
        p_grid.setVerticalSpacing(4)

        # Progress: 32 / 64
        lbl_p_prog = QLabel("Progress:")
        lbl_p_prog.setStyleSheet("font-size: 9px; color: #8b949e;")
        self.lbl_survey_progress = QLabel("0 / 64 (0.0%)")
        self.lbl_survey_progress.setStyleSheet("font-size: 10px; font-weight: 700; color: #ffffff; font-family: Consolas, monospace;")
        p_grid.addWidget(lbl_p_prog, 0, 0)
        p_grid.addWidget(self.lbl_survey_progress, 0, 1)

        # Current RSSI: -62 dBm
        lbl_p_rssi = QLabel("Current RSSI:")
        lbl_p_rssi.setStyleSheet("font-size: 9px; color: #8b949e;")
        self.lbl_survey_current_rssi = QLabel("-- dBm")
        self.lbl_survey_current_rssi.setStyleSheet("font-size: 11px; font-weight: 800; color: #58a6ff; font-family: Consolas, monospace;")
        p_grid.addWidget(lbl_p_rssi, 1, 0)
        p_grid.addWidget(self.lbl_survey_current_rssi, 1, 1)

        # Coverage: 73%
        lbl_p_cov = QLabel("Coverage:")
        lbl_p_cov.setStyleSheet("font-size: 9px; color: #8b949e;")
        self.lbl_survey_coverage = QLabel("0.0%")
        self.lbl_survey_coverage.setStyleSheet("font-size: 11px; font-weight: 800; color: #3fb950; font-family: Consolas, monospace;")
        p_grid.addWidget(lbl_p_cov, 2, 0)
        p_grid.addWidget(self.lbl_survey_coverage, 2, 1)

        # Mean RSSI
        lbl_p_mean = QLabel("Mean RSSI:")
        lbl_p_mean.setStyleSheet("font-size: 9px; color: #8b949e;")
        self.lbl_survey_mean_rssi = QLabel("-- dBm")
        self.lbl_survey_mean_rssi.setStyleSheet("font-size: 9px; font-weight: 600; color: #c9d1d9; font-family: Consolas, monospace;")
        p_grid.addWidget(lbl_p_mean, 3, 0)
        p_grid.addWidget(self.lbl_survey_mean_rssi, 3, 1)

        p_layout.addLayout(p_grid)
        layout.addWidget(self.progress_card)

        # 7. Phase 13: RF ANALYSIS Card (Section 24 Specification)
        self.analysis_card = QFrame()
        self.analysis_card.setProperty("class", "telemetry-card")
        a_layout = QVBoxLayout(self.analysis_card)
        a_layout.setContentsMargins(8, 6, 8, 6)
        a_layout.setSpacing(5)

        a_top = QHBoxLayout()
        lbl_a_title = QLabel("RF ANALYSIS")
        lbl_a_title.setStyleSheet("font-weight: 700; color: #58a6ff; font-size: 11px;")
        a_top.addWidget(lbl_a_title)
        a_top.addStretch()

        self.lbl_heatmap_badge = QLabel("READY")
        self.lbl_heatmap_badge.setStyleSheet(
            "background-color: #21262d; color: #8b949e; font-size: 9px; font-weight: 800; "
            "padding: 2px 6px; border-radius: 3px; border: 1px solid #30363d;"
        )
        a_top.addWidget(self.lbl_heatmap_badge)
        a_layout.addLayout(a_top)

        # Statistical Metrics Grid
        a_grid = QGridLayout()
        a_grid.setHorizontalSpacing(8)
        a_grid.setVerticalSpacing(3)

        # Survey points: 64
        lbl_ap_pts = QLabel("Survey points:")
        lbl_ap_pts.setStyleSheet("font-size: 9px; color: #8b949e;")
        self.lbl_analysis_points = QLabel("--")
        self.lbl_analysis_points.setStyleSheet("font-size: 10px; font-weight: 700; color: #c9d1d9; font-family: Consolas, monospace;")
        a_grid.addWidget(lbl_ap_pts, 0, 0)
        a_grid.addWidget(self.lbl_analysis_points, 0, 1)

        # Mean RSSI: -61 dBm
        lbl_ap_mean = QLabel("Mean RSSI:")
        lbl_ap_mean.setStyleSheet("font-size: 9px; color: #8b949e;")
        self.lbl_analysis_mean = QLabel("-- dBm")
        self.lbl_analysis_mean.setStyleSheet("font-size: 10px; font-weight: 700; color: #c9d1d9; font-family: Consolas, monospace;")
        a_grid.addWidget(lbl_ap_mean, 1, 0)
        a_grid.addWidget(self.lbl_analysis_mean, 1, 1)

        # Min RSSI: -87 dBm
        lbl_ap_min = QLabel("Min RSSI:")
        lbl_ap_min.setStyleSheet("font-size: 9px; color: #8b949e;")
        self.lbl_analysis_min = QLabel("-- dBm")
        self.lbl_analysis_min.setStyleSheet("font-size: 10px; font-weight: 700; color: #c9d1d9; font-family: Consolas, monospace;")
        a_grid.addWidget(lbl_ap_min, 2, 0)
        a_grid.addWidget(self.lbl_analysis_min, 2, 1)

        # Max RSSI: -42 dBm
        lbl_ap_max = QLabel("Max RSSI:")
        lbl_ap_max.setStyleSheet("font-size: 9px; color: #8b949e;")
        self.lbl_analysis_max = QLabel("-- dBm")
        self.lbl_analysis_max.setStyleSheet("font-size: 10px; font-weight: 700; color: #c9d1d9; font-family: Consolas, monospace;")
        a_grid.addWidget(lbl_ap_max, 3, 0)
        a_grid.addWidget(self.lbl_analysis_max, 3, 1)

        a_layout.addLayout(a_grid)

        # Horizontal separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setStyleSheet("border-top: 1px solid #30363d; margin-top: 2px; margin-bottom: 2px;")
        a_layout.addWidget(sep)

        # Coverage breakdown metrics
        c_grid = QGridLayout()
        c_grid.setHorizontalSpacing(8)
        c_grid.setVerticalSpacing(3)

        # Coverage: 76%
        lbl_cp_cov = QLabel("Coverage:")
        lbl_cp_cov.setStyleSheet("font-size: 9px; color: #8b949e; font-weight: 600;")
        self.lbl_analysis_coverage = QLabel("--%")
        self.lbl_analysis_coverage.setStyleSheet("font-size: 11px; font-weight: 800; color: #3fb950; font-family: Consolas, monospace;")
        c_grid.addWidget(lbl_cp_cov, 0, 0)
        c_grid.addWidget(self.lbl_analysis_coverage, 0, 1)

        # Weak: 14%
        lbl_cp_weak = QLabel("Weak:")
        lbl_cp_weak.setStyleSheet("font-size: 9px; color: #8b949e;")
        self.lbl_analysis_weak = QLabel("--%")
        self.lbl_analysis_weak.setStyleSheet("font-size: 10px; font-weight: 700; color: #d29922; font-family: Consolas, monospace;")
        c_grid.addWidget(lbl_cp_weak, 1, 0)
        c_grid.addWidget(self.lbl_analysis_weak, 1, 1)

        # No coverage: 10%
        lbl_cp_no_cov = QLabel("No coverage:")
        lbl_cp_no_cov.setStyleSheet("font-size: 9px; color: #8b949e;")
        self.lbl_analysis_no_cov = QLabel("--%")
        self.lbl_analysis_no_cov.setStyleSheet("font-size: 10px; font-weight: 700; color: #f85149; font-family: Consolas, monospace;")
        c_grid.addWidget(lbl_cp_no_cov, 2, 0)
        c_grid.addWidget(self.lbl_analysis_no_cov, 2, 1)

        a_layout.addLayout(c_grid)

        # Proportional Breakdown Bar
        bar_frame = QFrame()
        bar_frame.setFixedHeight(8)
        bar_frame.setStyleSheet("background-color: #21262d; border-radius: 4px; border: 1px solid #30363d;")
        self.bar_layout = QHBoxLayout(bar_frame)
        self.bar_layout.setContentsMargins(0, 0, 0, 0)
        self.bar_layout.setSpacing(0)

        self.bar_strong = QFrame()
        self.bar_strong.setStyleSheet("background-color: #2ecc71; border-top-left-radius: 3px; border-bottom-left-radius: 3px;")
        self.bar_good = QFrame()
        self.bar_good.setStyleSheet("background-color: #a3e635;")
        self.bar_weak = QFrame()
        self.bar_weak.setStyleSheet("background-color: #f39c12;")
        self.bar_no_cov = QFrame()
        self.bar_no_cov.setStyleSheet("background-color: #e74c3c; border-top-right-radius: 3px; border-bottom-right-radius: 3px;")

        self.bar_layout.addWidget(self.bar_strong, 25)
        self.bar_layout.addWidget(self.bar_good, 25)
        self.bar_layout.addWidget(self.bar_weak, 25)
        self.bar_layout.addWidget(self.bar_no_cov, 25)
        a_layout.addWidget(bar_frame)

        # Heatmap Action Buttons
        a_btns = QHBoxLayout()
        self.btn_gen_heatmap = QPushButton("GENERATE HEATMAP")
        self.btn_gen_heatmap.setStyleSheet(
            "QPushButton { background-color: #1f6feb; color: #ffffff; font-weight: 700; font-size: 9px; padding: 4px 8px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #388bfd; }"
        )
        self.btn_clear_heatmap = QPushButton("CLEAR HEATMAP")
        self.btn_clear_heatmap.setStyleSheet(
            "QPushButton { background-color: #21262d; color: #c9d1d9; font-size: 9px; padding: 4px 8px; border-radius: 4px; border: 1px solid #30363d; }"
            "QPushButton:hover { background-color: #30363d; }"
        )
        a_btns.addWidget(self.btn_gen_heatmap)
        a_btns.addWidget(self.btn_clear_heatmap)
        a_layout.addLayout(a_btns)

        layout.addWidget(self.analysis_card)

        # 8. Phase 14: COVERAGE ANALYSIS Card (Section 25 Specification)
        self.coverage_gap_card = QFrame()
        self.coverage_gap_card.setProperty("class", "telemetry-card")
        cg_layout = QVBoxLayout(self.coverage_gap_card)
        cg_layout.setContentsMargins(8, 6, 8, 6)
        cg_layout.setSpacing(5)

        cg_top = QHBoxLayout()
        lbl_cg_title = QLabel("COVERAGE ANALYSIS")
        lbl_cg_title.setStyleSheet("font-weight: 700; color: #58a6ff; font-size: 11px;")
        cg_top.addWidget(lbl_cg_title)
        cg_top.addStretch()

        self.lbl_gap_badge = QLabel("READY")
        self.lbl_gap_badge.setStyleSheet(
            "background-color: #21262d; color: #8b949e; font-size: 9px; font-weight: 800; "
            "padding: 2px 6px; border-radius: 3px; border: 1px solid #30363d;"
        )
        cg_top.addWidget(self.lbl_gap_badge)
        cg_layout.addLayout(cg_top)

        # Section 25 Metrics Grid:
        # Total area: 1.2 km²
        # Covered: 78%
        # Weak: 12%
        # Uncovered: 10%
        cg_grid = QGridLayout()
        cg_grid.setHorizontalSpacing(8)
        cg_grid.setVerticalSpacing(3)

        lbl_cgt_area = QLabel("Total area:")
        lbl_cgt_area.setStyleSheet("font-size: 9px; color: #8b949e;")
        self.lbl_cov_total_area = QLabel("1.2 km²")
        self.lbl_cov_total_area.setStyleSheet("font-size: 10px; font-weight: 700; color: #c9d1d9; font-family: Consolas, monospace;")
        cg_grid.addWidget(lbl_cgt_area, 0, 0)
        cg_grid.addWidget(self.lbl_cov_total_area, 0, 1)

        lbl_cgt_cov = QLabel("Covered:")
        lbl_cgt_cov.setStyleSheet("font-size: 9px; color: #8b949e;")
        self.lbl_cov_covered = QLabel("78%")
        self.lbl_cov_covered.setStyleSheet("font-size: 10px; font-weight: 700; color: #3fb950; font-family: Consolas, monospace;")
        cg_grid.addWidget(lbl_cgt_cov, 1, 0)
        cg_grid.addWidget(self.lbl_cov_covered, 1, 1)

        lbl_cgt_weak = QLabel("Weak:")
        lbl_cgt_weak.setStyleSheet("font-size: 9px; color: #8b949e;")
        self.lbl_cov_weak = QLabel("12%")
        self.lbl_cov_weak.setStyleSheet("font-size: 10px; font-weight: 700; color: #d29922; font-family: Consolas, monospace;")
        cg_grid.addWidget(lbl_cgt_weak, 2, 0)
        cg_grid.addWidget(self.lbl_cov_weak, 2, 1)

        lbl_cgt_uncov = QLabel("Uncovered:")
        lbl_cgt_uncov.setStyleSheet("font-size: 9px; color: #8b949e;")
        self.lbl_cov_uncovered = QLabel("10%")
        self.lbl_cov_uncovered.setStyleSheet("font-size: 10px; font-weight: 700; color: #f85149; font-family: Consolas, monospace;")
        cg_grid.addWidget(lbl_cgt_uncov, 3, 0)
        cg_grid.addWidget(self.lbl_cov_uncovered, 3, 1)

        cg_layout.addLayout(cg_grid)

        # Gap Info summary label
        self.lbl_gap_summary = QLabel("Gaps Detected: 0 zones")
        self.lbl_gap_summary.setStyleSheet("font-size: 9px; color: #8b949e; font-style: italic;")
        cg_layout.addWidget(self.lbl_gap_summary)

        # Buttons (Exact Section 25 match)
        # [FIND GAPS]
        # [RECALCULATE LOCATIONS]
        cg_btns = QHBoxLayout()
        self.btn_find_gaps = QPushButton("FIND GAPS")
        self.btn_find_gaps.setStyleSheet(
            "QPushButton { background-color: #1f6feb; color: #ffffff; font-weight: 700; font-size: 9px; padding: 4px 8px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #388bfd; }"
        )
        self.btn_recalc_locations = QPushButton("RECALCULATE LOCATIONS")
        self.btn_recalc_locations.setStyleSheet(
            "QPushButton { background-color: #238636; color: #ffffff; font-weight: 700; font-size: 9px; padding: 4px 8px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #2ea043; }"
        )
        cg_btns.addWidget(self.btn_find_gaps)
        cg_btns.addWidget(self.btn_recalc_locations)
        cg_layout.addLayout(cg_btns)

        layout.addWidget(self.coverage_gap_card)

        # 9. Adaptive Deployment (Phase 15)
        self.adaptive_card = QFrame()
        self.adaptive_card.setProperty("class", "telemetry-card")
        adp_layout = QVBoxLayout(self.adaptive_card)
        adp_layout.setContentsMargins(8, 6, 8, 6)
        adp_layout.setSpacing(4)

        adp_header = QHBoxLayout()
        adp_title = QLabel("ADAPTIVE DEPLOYMENT")
        adp_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #58a6ff; letter-spacing: 0.5px;")
        adp_header.addWidget(adp_title)
        adp_header.addStretch()
        self.lbl_adp_badge = QLabel("READY")
        self.lbl_adp_badge.setStyleSheet(
            "background-color: #21262d; color: #8b949e; font-size: 9px; font-weight: 800; "
            "padding: 2px 6px; border-radius: 3px; border: 1px solid #30363d;"
        )
        adp_header.addWidget(self.lbl_adp_badge)
        adp_layout.addLayout(adp_header)

        sep4 = QFrame()
        sep4.setFrameShape(QFrame.Shape.HLine)
        sep4.setStyleSheet("background-color: #21262d; margin: 2px 0;")
        adp_layout.addWidget(sep4)

        # Coverage estimate row
        cov_row = QHBoxLayout()
        cov_row.setSpacing(8)
        for lbl_text, attr, color in [
            ("Before:", "lbl_adp_cov_before", "#8b949e"),
            ("Est. After:", "lbl_adp_cov_after", "#3fb950"),
        ]:
            r = QHBoxLayout()
            r.setSpacing(3)
            r.addWidget(QLabel(lbl_text))
            lbl = QLabel("78%" if "Before" in lbl_text else "--")
            lbl.setStyleSheet(f"font-size: 10px; font-weight: 700; color: {color};")
            setattr(self, attr, lbl)
            r.addWidget(lbl)
            cov_row.addLayout(r)
        cov_row.addStretch()
        adp_layout.addLayout(cov_row)

        # Stage count
        stages_row = QHBoxLayout()
        stages_row.setSpacing(3)
        stages_row.addWidget(QLabel("Stages:"))
        self.lbl_adp_stages = QLabel("--")
        self.lbl_adp_stages.setStyleSheet("font-size: 10px; font-weight: 700; color: #58a6ff;")
        stages_row.addWidget(self.lbl_adp_stages)
        stages_row.addStretch()
        adp_layout.addLayout(stages_row)

        sep5 = QFrame()
        sep5.setFrameShape(QFrame.Shape.HLine)
        sep5.setStyleSheet("background-color: #21262d; margin: 2px 0;")
        adp_layout.addWidget(sep5)

        # Current stage readouts
        for label_text, attr, default, color in [
            ("Stage:",    "lbl_adp_current_stage", "--",       "#e6edf3"),
            ("Priority:", "lbl_adp_priority",      "--",       "#8b949e"),
            ("Gap Area:", "lbl_adp_area",           "--",       "#8b949e"),
            ("Target:",   "lbl_adp_target",         "--",       "#8b949e"),
            ("Est. Flight:","lbl_adp_flight_time",  "--",       "#8b949e"),
        ]:
            row = QHBoxLayout()
            row.setSpacing(3)
            lbl_k = QLabel(label_text)
            lbl_k.setFixedWidth(70)
            lbl_k.setStyleSheet("font-size: 9px; color: #8b949e;")
            row.addWidget(lbl_k)
            lbl_v = QLabel(default)
            lbl_v.setStyleSheet(f"font-size: 9px; font-weight: 600; color: {color};")
            lbl_v.setWordWrap(True)
            setattr(self, attr, lbl_v)
            row.addWidget(lbl_v)
            row.addStretch()
            adp_layout.addLayout(row)

        # Action buttons row 1
        adp_btn_row1 = QHBoxLayout()
        adp_btn_row1.setSpacing(6)
        self.btn_build_plan = QPushButton("BUILD PLAN")
        self.btn_build_plan.setStyleSheet(
            "QPushButton { background-color: #1f6feb; color: #ffffff; "
            "border-radius: 3px; font-size: 9px; font-weight: 700; padding: 4px 8px; } "
            "QPushButton:hover { background-color: #388bfd; }"
        )
        adp_btn_row1.addWidget(self.btn_build_plan)
        self.btn_execute_stage = QPushButton("EXECUTE STAGE")
        self.btn_execute_stage.setStyleSheet(
            "QPushButton { background-color: #238636; color: #ffffff; "
            "border-radius: 3px; font-size: 9px; font-weight: 700; padding: 4px 8px; } "
            "QPushButton:hover { background-color: #2ea043; }"
        )
        adp_btn_row1.addWidget(self.btn_execute_stage)
        adp_layout.addLayout(adp_btn_row1)

        # Action buttons row 2
        adp_btn_row2 = QHBoxLayout()
        adp_btn_row2.setSpacing(6)
        self.btn_skip_stage = QPushButton("SKIP")
        self.btn_skip_stage.setStyleSheet(
            "QPushButton { background-color: #21262d; color: #f0883e; "
            "border: 1px solid #f0883e; border-radius: 3px; font-size: 9px; "
            "font-weight: 700; padding: 4px 8px; } "
            "QPushButton:hover { background-color: #2d2f34; }"
        )
        adp_btn_row2.addWidget(self.btn_skip_stage)
        self.btn_reset_plan = QPushButton("RESET PLAN")
        self.btn_reset_plan.setStyleSheet(
            "QPushButton { background-color: #21262d; color: #f85149; "
            "border: 1px solid #f85149; border-radius: 3px; font-size: 9px; "
            "font-weight: 700; padding: 4px 8px; } "
            "QPushButton:hover { background-color: #2d1e1e; }"
        )
        adp_btn_row2.addWidget(self.btn_reset_plan)
        adp_layout.addLayout(adp_btn_row2)

        layout.addWidget(self.adaptive_card)

        self.scroll_area.setWidget(container)
        root_layout.addWidget(self.scroll_area)

    def _connect_signals(self):
        app_state.rf_uav_link_updated.connect(self._on_uav_rf_link_updated)
        app_state.virtual_nodes_updated.connect(self._on_nodes_updated)
        app_state.deployed_nodes_cleared.connect(self._on_nodes_cleared)

        # Survey connections (Phase 12)
        self.btn_gen_survey.clicked.connect(self._on_generate_survey)
        self.btn_start_survey.clicked.connect(self._on_start_survey)
        self.btn_stop_survey.clicked.connect(self._on_stop_survey)
        self.btn_clear_survey.clicked.connect(self._on_clear_survey)

        rf_survey_controller.plan_generated.connect(self._on_survey_plan_generated)
        rf_survey_controller.state_changed.connect(self._on_survey_state_changed)
        rf_survey_controller.progress_updated.connect(self._on_survey_progress_updated)
        rf_survey_controller.survey_completed.connect(self._on_survey_completed)
        rf_survey_controller.survey_cleared.connect(self._on_survey_cleared)

        # Heatmap connections (Phase 13)
        self.btn_gen_heatmap.clicked.connect(self._on_generate_heatmap)
        self.btn_clear_heatmap.clicked.connect(self._on_clear_heatmap)
        app_state.rssi_heatmap_cleared.connect(self._on_heatmap_cleared_external)

        # Coverage Gap connections (Phase 14)
        self.btn_find_gaps.clicked.connect(self._on_find_gaps)
        self.btn_recalc_locations.clicked.connect(self._on_recalculate_locations)
        app_state.gaps_cleared.connect(self._on_gaps_cleared_external)

        # Adaptive Deployment connections (Phase 15)
        self.btn_build_plan.clicked.connect(self._on_build_adaptive_plan)
        self.btn_execute_stage.clicked.connect(self._on_execute_stage)
        self.btn_skip_stage.clicked.connect(self._on_skip_stage)
        self.btn_reset_plan.clicked.connect(self._on_reset_adaptive_plan)
        app_state.adaptive_plan_generated.connect(self._update_adaptive_ui)
        app_state.adaptive_plan_updated.connect(self._update_adaptive_ui)
        app_state.adaptive_plan_cleared.connect(self._on_adaptive_plan_cleared)

    def _on_band_changed(self, band_text: str):
        preset_freq = rf_engine.BAND_PRESETS.get(band_text, 2400.0)
        self.spin_freq.setValue(preset_freq)
        self._on_calculate_coverage()

    def _on_env_changed(self, env_text: str):
        preset_n = rf_engine.ENV_PRESETS.get(env_text, 2.5)
        self.spin_n.setValue(preset_n)
        self._on_calculate_coverage()

    def _on_calculate_coverage(self):
        """Execute propagation engine calculation and sync with app_state."""
        cfg = RfConfig(
            frequency_band=self.combo_band.currentText(),
            frequency_mhz=self.spin_freq.value(),
            tx_power_dbm=self.spin_tx_pwr.value(),
            ref_distance_m=self.spin_d0.value(),
            path_loss_exponent=self.spin_n.value(),
            environment_name=self.combo_env.currentText(),
            rx_sensitivity_dbm=self.spin_rx_sens.value(),
            shadowing_std_db=self.spin_shadow.value()
        )

        res = rf_engine.calculate_coverage(cfg)
        app_state.set_rf_config(cfg)
        app_state.set_rf_calculation_result(res)

        # Update UI labels
        self.lbl_radius_val.setText(f"{res.coverage_radius_m:.1f} m")
        self.lbl_area_val.setText(f"{res.coverage_area_km2:.3f} km² ({res.coverage_area_m2 / 10000:.1f} ha)")
        self.lbl_fspl_val.setText(f"{res.fspl_at_d0_db:.1f} dB")
        self.lbl_max_pl.setText(f"{res.max_allowable_path_loss_db:.1f} dB")
        self.lbl_eirp_val.setText(f"{res.eirp_dbm:.1f} dBm")

        app_state.set_command_feedback(f"RF MODEL CALCULATED: Radius = {res.coverage_radius_m:.1f}m (Band: {cfg.frequency_band})")

    def _on_apply_to_virtual_nodes(self):
        """Apply newly calculated coverage radius and band across all deployed virtual nodes."""
        res = rf_engine.last_result
        if not res:
            return
        radius = res.coverage_radius_m
        band = self.combo_band.currentText()
        tx_pwr = self.spin_tx_pwr.value()

        # Update virtual nodes in manager
        count = 0
        for node in virtual_node_manager.nodes:
            node.coverage_radius_m = radius
            node.frequency_band = band
            node.tx_power_dbm = tx_pwr
            virtual_node_manager.node_updated.emit(node)
            count += 1

        # Also update app_state.deployed_nodes
        for d in app_state.deployed_nodes:
            d.coverage_radius_m = radius

        app_state.virtual_nodes_updated.emit(app_state.virtual_nodes)
        feedback = f"APPLIED RF COVERAGE: {radius:.1f}m TO {count} VIRTUAL NODE(S)"
        app_state.set_command_feedback(feedback)
        app_state.log("INFO", "RF_MODEL", feedback)

    def _on_uav_rf_link_updated(self, link: dict):
        """Update live UAV-to-node simulated link readout."""
        if not link or not link.get("connected", False) and link.get("node_id") == "NONE":
            self.lbl_link_status_badge.setText("NO NODES")
            self.lbl_link_status_badge.setStyleSheet("background-color: #21262d; color: #8b949e; font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: 3px; border: 1px solid #30363d;")
            self.lbl_near_node.setText("--")
            self.lbl_link_dist.setText("-- m")
            self.lbl_link_rssi.setText("-- dBm")
            self.lbl_link_margin.setText("-- dB")
            return

        nid = link.get("node_id", "--")
        dist = link.get("dist_3d_m", 0.0)
        rssi = link.get("rssi_dbm", -120.0)
        quality = link.get("quality", "UNKNOWN")
        color = link.get("color", "#8b949e")

        sens = self.spin_rx_sens.value()
        margin = rssi - sens

        self.lbl_near_node.setText(nid)
        self.lbl_link_dist.setText(f"{dist:.1f} m")
        self.lbl_link_rssi.setText(f"{rssi:.1f} dBm")
        self.lbl_link_rssi.setStyleSheet(f"font-size: 11px; font-weight: 800; color: {color}; font-family: Consolas, monospace;")

        margin_sign = "+" if margin >= 0 else ""
        self.lbl_link_margin.setText(f"{margin_sign}{margin:.1f} dB")
        if margin >= 10:
            self.lbl_link_margin.setStyleSheet("font-size: 9px; font-weight: 600; color: #3fb950; font-family: Consolas, monospace;")
        elif margin >= 0:
            self.lbl_link_margin.setStyleSheet("font-size: 9px; font-weight: 600; color: #e3b341; font-family: Consolas, monospace;")
        else:
            self.lbl_link_margin.setStyleSheet("font-size: 9px; font-weight: 600; color: #f85149; font-family: Consolas, monospace;")

        self.lbl_link_status_badge.setText(quality)
        self.lbl_link_status_badge.setStyleSheet(f"background-color: {color}; color: #ffffff; font-size: 9px; font-weight: 800; padding: 2px 6px; border-radius: 3px;")

    def _on_nodes_updated(self, nodes: list):
        if not nodes:
            self._on_nodes_cleared()

    def _on_nodes_cleared(self):
        self.lbl_link_status_badge.setText("NO NODES")
        self.lbl_link_status_badge.setStyleSheet("background-color: #21262d; color: #8b949e; font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: 3px; border: 1px solid #30363d;")
        self.lbl_near_node.setText("--")
        self.lbl_link_dist.setText("-- m")
        self.lbl_link_rssi.setText("-- dBm")
        self.lbl_link_margin.setText("-- dB")

    # ──────────────────────────────────────────────────────────────────────────
    # Phase 12: Survey Planning & Progress Handlers
    # ──────────────────────────────────────────────────────────────────────────
    def _on_survey_params_changed(self):
        """Update estimated points or area if survey is idle."""
        if rf_survey_controller.status == SurveyStatus.IDLE:
            # Dynamically preview plan
            pass

    def _on_generate_survey(self):
        """Generate lawnmower survey flight pattern."""
        alt = self.spin_survey_alt.value()
        spacing = self.spin_survey_spacing.value()
        plan = rf_survey_controller.generate_survey(
            altitude_m=alt,
            line_spacing_m=spacing,
            target_points=64,
            target_area_km2=1.2,
        )
        self._on_survey_plan_generated(plan)

    def _on_start_survey(self):
        """Initiate autonomous or simulated survey flight."""
        rf_survey_controller.start_survey()

    def _on_stop_survey(self):
        """Halt active survey."""
        rf_survey_controller.stop_survey()

    def _on_clear_survey(self):
        """Clear survey waypoints and samples."""
        rf_survey_controller.clear_survey()

    def _on_survey_plan_generated(self, plan: SurveyPlan):
        """Update UI labels upon survey plan generation."""
        if not plan:
            return
        self.lbl_survey_area.setText(f"{plan.area_km2:.3f} km²")
        self.lbl_survey_pattern.setText(plan.pattern_type)
        self.lbl_survey_points.setText(str(len(plan.waypoints)))
        self.lbl_survey_progress.setText(f"0 / {len(plan.waypoints)} (0.0%)")
        self.lbl_survey_current_rssi.setText("-- dBm")
        self.lbl_survey_coverage.setText("0.0%")
        self.lbl_survey_mean_rssi.setText("-- dBm")

    def _on_survey_state_changed(self, status: str):
        """Update badge styling and control button enabled states."""
        self.lbl_survey_status_badge.setText(status)

        if status == SurveyStatus.READY.value:
            self.lbl_survey_status_badge.setStyleSheet(
                "background-color: #1f6feb; color: #ffffff; font-size: 9px; font-weight: 800; padding: 2px 6px; border-radius: 3px;"
            )
            self.btn_gen_survey.setEnabled(True)
            self.btn_start_survey.setEnabled(True)
            self.btn_stop_survey.setEnabled(False)
        elif status == SurveyStatus.RUNNING.value:
            self.lbl_survey_status_badge.setStyleSheet(
                "background-color: #238636; color: #ffffff; font-size: 9px; font-weight: 800; padding: 2px 6px; border-radius: 3px;"
            )
            self.btn_gen_survey.setEnabled(False)
            self.btn_start_survey.setEnabled(False)
            self.btn_stop_survey.setEnabled(True)
        elif status == SurveyStatus.COMPLETED.value:
            self.lbl_survey_status_badge.setStyleSheet(
                "background-color: #388bfd; color: #ffffff; font-size: 9px; font-weight: 800; padding: 2px 6px; border-radius: 3px;"
            )
            self.btn_gen_survey.setEnabled(True)
            self.btn_start_survey.setEnabled(False)
            self.btn_stop_survey.setEnabled(False)
        elif status == SurveyStatus.STOPPED.value:
            self.lbl_survey_status_badge.setStyleSheet(
                "background-color: #da3633; color: #ffffff; font-size: 9px; font-weight: 800; padding: 2px 6px; border-radius: 3px;"
            )
            self.btn_gen_survey.setEnabled(True)
            self.btn_start_survey.setEnabled(True)
            self.btn_stop_survey.setEnabled(False)
        else:  # IDLE
            self.lbl_survey_status_badge.setStyleSheet(
                "background-color: #21262d; color: #8b949e; font-size: 9px; font-weight: 800; padding: 2px 6px; border-radius: 3px; border: 1px solid #30363d;"
            )
            self.btn_gen_survey.setEnabled(True)
            self.btn_start_survey.setEnabled(False)
            self.btn_stop_survey.setEnabled(False)

    def _on_survey_progress_updated(self, metrics: SurveyMetrics):
        """Update live running survey telemetry matching Section 23 specification."""
        if not metrics:
            return

        self.lbl_survey_progress.setText(f"{metrics.visited_points} / {metrics.total_points} ({metrics.progress_pct:.1f}%)")

        if metrics.current_rssi_dbm is not None:
            rssi = metrics.current_rssi_dbm
            self.lbl_survey_current_rssi.setText(f"{rssi:.1f} dBm")
            threshold = self.spin_rx_sens.value()
            if rssi >= -65.0:
                self.lbl_survey_current_rssi.setStyleSheet("font-size: 11px; font-weight: 800; color: #3fb950; font-family: Consolas, monospace;")
            elif rssi >= threshold:
                self.lbl_survey_current_rssi.setStyleSheet("font-size: 11px; font-weight: 800; color: #58a6ff; font-family: Consolas, monospace;")
            elif rssi >= threshold - 10.0:
                self.lbl_survey_current_rssi.setStyleSheet("font-size: 11px; font-weight: 800; color: #d29922; font-family: Consolas, monospace;")
            else:
                self.lbl_survey_current_rssi.setStyleSheet("font-size: 11px; font-weight: 800; color: #f85149; font-family: Consolas, monospace;")
        else:
            self.lbl_survey_current_rssi.setText("-- dBm")

        self.lbl_survey_coverage.setText(f"{metrics.coverage_pct:.1f}%")
        if metrics.coverage_pct >= 70.0:
            self.lbl_survey_coverage.setStyleSheet("font-size: 11px; font-weight: 800; color: #3fb950; font-family: Consolas, monospace;")
        elif metrics.coverage_pct >= 50.0:
            self.lbl_survey_coverage.setStyleSheet("font-size: 11px; font-weight: 800; color: #d29922; font-family: Consolas, monospace;")
        else:
            self.lbl_survey_coverage.setStyleSheet("font-size: 11px; font-weight: 800; color: #f85149; font-family: Consolas, monospace;")

        if metrics.mean_rssi_dbm is not None:
            self.lbl_survey_mean_rssi.setText(f"{metrics.mean_rssi_dbm:.1f} dBm")
        else:
            self.lbl_survey_mean_rssi.setText("-- dBm")

    def _on_survey_completed(self, metrics: SurveyMetrics):
        """Handler when all waypoints in the survey have been completed."""
        self._on_survey_state_changed(SurveyStatus.COMPLETED.value)
        self._on_survey_progress_updated(metrics)
        # Automatically generate RSSI heatmap upon survey completion
        self._on_generate_heatmap()

    def _on_survey_cleared(self):
        """Handler when survey is cleared."""
        self.lbl_survey_status_badge.setText("IDLE")
        self.lbl_survey_status_badge.setStyleSheet(
            "background-color: #21262d; color: #8b949e; font-size: 9px; font-weight: 800; padding: 2px 6px; border-radius: 3px; border: 1px solid #30363d;"
        )
        self.lbl_survey_progress.setText("0 / 0 (0.0%)")
        self.lbl_survey_current_rssi.setText("-- dBm")
        self.lbl_survey_coverage.setText("0.0%")
        self.lbl_survey_mean_rssi.setText("-- dBm")
        self.btn_gen_survey.setEnabled(True)
        self.btn_start_survey.setEnabled(False)
        self.btn_stop_survey.setEnabled(False)

    # ──────────────────────────────────────────────────────────────────────────
    # Phase 13: RF Analysis & RSSI Heatmap Handlers
    # ──────────────────────────────────────────────────────────────────────────
    def _on_generate_heatmap(self):
        """Generate spatial RSSI heatmap from survey samples or active virtual nodes."""
        samples = app_state.survey_samples
        if samples and len(samples) > 0:
            analysis = RfHeatmapEngine.generate_heatmap_from_samples(samples)
        else:
            # Fallback to active virtual nodes or default center
            nodes = virtual_node_manager.get_all_nodes()
            c_lat = -35.363261
            c_lon = 149.165230
            if nodes:
                c_lat = sum(getattr(n, "lat", getattr(n, "latitude", 0.0)) for n in nodes) / len(nodes)
                c_lon = sum(getattr(n, "lon", getattr(n, "longitude", 0.0)) for n in nodes) / len(nodes)
            elif app_state.telemetry.get("lat") not in ("--", None):
                try:
                    c_lat = float(app_state.telemetry["lat"])
                    c_lon = float(app_state.telemetry["lon"])
                except Exception:
                    pass

            analysis = RfHeatmapEngine.generate_heatmap_from_nodes(
                nodes=nodes,
                center_lat=c_lat,
                center_lon=c_lon,
                radius_m=650.0,
                rf_engine=rf_engine,
            )

        app_state.set_rssi_heatmap(analysis)
        self._update_analysis_ui(analysis)
        app_state.set_command_feedback(
            f"HEATMAP GENERATED: {analysis.coverage_pct:.1f}% Coverage, Mean {analysis.mean_rssi_dbm:.1f} dBm"
        )

    def _on_clear_heatmap(self):
        """Clear the RSSI heatmap and reset the RF Analysis card."""
        app_state.clear_rssi_heatmap()
        self._on_heatmap_cleared_external()
        app_state.set_command_feedback("RF HEATMAP CLEARED")

    def _on_heatmap_cleared_external(self):
        """Reset the RF Analysis display metrics."""
        self.lbl_analysis_points.setText("--")
        self.lbl_analysis_mean.setText("-- dBm")
        self.lbl_analysis_min.setText("-- dBm")
        self.lbl_analysis_max.setText("-- dBm")
        self.lbl_analysis_coverage.setText("--%")
        self.lbl_analysis_weak.setText("--%")
        self.lbl_analysis_no_cov.setText("--%")
        self.lbl_heatmap_badge.setText("READY")
        self.lbl_heatmap_badge.setStyleSheet(
            "background-color: #21262d; color: #8b949e; font-size: 9px; font-weight: 800; padding: 2px 6px; border-radius: 3px; border: 1px solid #30363d;"
        )
        self.bar_layout.setStretch(0, 25)
        self.bar_layout.setStretch(1, 25)
        self.bar_layout.setStretch(2, 25)
        self.bar_layout.setStretch(3, 25)

    def _update_analysis_ui(self, res: RfAnalysisResult):
        """Update RF Analysis card metrics matching Section 24 specification."""
        if not res:
            return

        self.lbl_analysis_points.setText(str(res.total_points))
        self.lbl_analysis_mean.setText(f"{res.mean_rssi_dbm:.0f} dBm")
        self.lbl_analysis_min.setText(f"{res.min_rssi_dbm:.0f} dBm")
        self.lbl_analysis_max.setText(f"{res.max_rssi_dbm:.0f} dBm")

        self.lbl_analysis_coverage.setText(f"{res.coverage_pct:.0f}%")
        self.lbl_analysis_weak.setText(f"{res.weak_pct:.0f}%")
        self.lbl_analysis_no_cov.setText(f"{res.no_coverage_pct:.0f}%")

        # Visual breakdown bar stretch proportions
        s = max(1, int(round(res.strong_pct)))
        g = max(1, int(round(res.good_pct)))
        w = max(1, int(round(res.weak_pct)))
        n = max(1, int(round(res.no_coverage_pct)))

        self.bar_layout.setStretch(0, s)
        self.bar_layout.setStretch(1, g)
        self.bar_layout.setStretch(2, w)
        self.bar_layout.setStretch(3, n)

        self.lbl_heatmap_badge.setText("ACTIVE")
        self.lbl_heatmap_badge.setStyleSheet(
            "background-color: #238636; color: #ffffff; font-size: 9px; font-weight: 800; padding: 2px 6px; border-radius: 3px;"
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Phase 14: Coverage Gap Analysis Handlers (Section 25 Specification)
    # ──────────────────────────────────────────────────────────────────────────
    def _on_find_gaps(self):
        """Execute coverage gap and shadow analysis matching Section 25 specification."""
        report = CoverageGapAnalyzer.analyze_gaps(
            heatmap_result=app_state.rf_analysis_result,
            survey_samples=app_state.survey_samples,
            virtual_nodes=virtual_node_manager.get_all_nodes(),
            total_area_km2=1.2,
        )
        app_state.set_coverage_analysis_report(report)
        self._update_coverage_gap_ui(report)

    def _update_coverage_gap_ui(self, report: CoverageAnalysisReport):
        """Update Section 25 COVERAGE ANALYSIS card."""
        if not report:
            return

        self.lbl_cov_total_area.setText(f"{report.total_area_km2:.1f} km²")
        self.lbl_cov_covered.setText(f"{report.covered_pct:.0f}%")
        self.lbl_cov_weak.setText(f"{report.weak_pct:.0f}%")
        self.lbl_cov_uncovered.setText(f"{report.uncovered_pct:.0f}%")

        if report.gaps_detected > 0:
            self.lbl_gap_badge.setText(f"{report.gaps_detected} GAP{'S' if report.gaps_detected > 1 else ''}")
            self.lbl_gap_badge.setStyleSheet(
                "background-color: #da3633; color: #ffffff; font-size: 9px; font-weight: 800; padding: 2px 6px; border-radius: 3px;"
            )
            gap_summary_str = f"Gaps Detected: {report.gaps_detected} zones ("
            gap_summary_str += ", ".join(f"{g.gap_id}: {g.area_sq_km:.2f} km²" for g in report.gaps[:2])
            if len(report.gaps) > 2:
                gap_summary_str += f", +{len(report.gaps) - 2} more"
            gap_summary_str += ")"
            self.lbl_gap_summary.setText(gap_summary_str)
            self.lbl_gap_summary.setStyleSheet("font-size: 9px; color: #f85149; font-weight: 600;")
        else:
            self.lbl_gap_badge.setText("ALL CLEAR")
            self.lbl_gap_badge.setStyleSheet(
                "background-color: #238636; color: #ffffff; font-size: 9px; font-weight: 800; padding: 2px 6px; border-radius: 3px;"
            )
            self.lbl_gap_summary.setText("Gaps Detected: 0 zones (Full coverage)")
            self.lbl_gap_summary.setStyleSheet("font-size: 9px; color: #3fb950; font-style: italic;")

        app_state.set_command_feedback(
            f"COVERAGE ANALYSIS: {report.covered_pct:.0f}% Covered, {report.uncovered_pct:.0f}% Uncovered, {report.gaps_detected} Gaps"
        )

    def _on_recalculate_locations(self):
        """Recalculate optimal secondary relay deployment coordinates to patch detected gaps."""
        report = app_state.coverage_analysis_report
        if not report or not report.gaps:
            self._on_find_gaps()
            report = app_state.coverage_analysis_report

        if report and report.gaps:
            target_gap = report.gaps[0]
            lat = target_gap.recommended_relay_lat
            lon = target_gap.recommended_relay_lon
            alt = 15.0

            app_state.set_deployment_target(lat, lon, altitude_m=alt)
            app_state.set_command_feedback(
                f"RECALCULATED LOCATION: Secondary target set to {target_gap.gap_id} centroid ({lat:.6f}, {lon:.6f})"
            )
            app_state.log("INFO", "DEPLOYMENT", f"Secondary deployment target recalculated for {target_gap.gap_id}: Lat={lat:.6f}, Lon={lon:.6f}")

            # Route to DEPLOYMENT tab so operator sees new target ready to upload
            win = self.window()
            if hasattr(win, "right_panel") and hasattr(win.right_panel, "tabs"):
                win.right_panel.tabs.setCurrentIndex(3)
        else:
            app_state.set_command_feedback("RECALCULATE LOCATIONS: No coverage gaps detected.")

    def _on_gaps_cleared_external(self):
        """Reset the coverage gap card."""
        self.lbl_cov_total_area.setText("1.2 km²")
        self.lbl_cov_covered.setText("--%")
        self.lbl_cov_weak.setText("--%")
        self.lbl_cov_uncovered.setText("--%")
        self.lbl_gap_badge.setText("READY")
        self.lbl_gap_badge.setStyleSheet(
            "background-color: #21262d; color: #8b949e; font-size: 9px; font-weight: 800; padding: 2px 6px; border-radius: 3px; border: 1px solid #30363d;"
        )
        self.lbl_gap_summary.setText("Gaps Detected: 0 zones")
        self.lbl_gap_summary.setStyleSheet("font-size: 9px; color: #8b949e; font-style: italic;")

    # ─── Phase 15: Adaptive Deployment Handlers ──────────────────────────────

    def _on_build_adaptive_plan(self):
        """Build a prioritised multi-stage deployment plan from detected gap zones."""
        from gcs.deployment.adaptive_deployment_engine import adaptive_deployment_engine

        # Ensure gaps are available; auto-run find_gaps if not
        if not app_state.detected_gaps:
            self._on_find_gaps()

        report = app_state.coverage_analysis_report
        cov_before = getattr(report, "covered_pct", 78.0) if report else 78.0
        total_area = getattr(report, "total_area_km2", 1.2) if report else 1.2

        plan = adaptive_deployment_engine.build_plan(
            gaps=app_state.detected_gaps,
            home_lat=app_state.home_lat,
            home_lon=app_state.home_lon,
            coverage_before_pct=cov_before,
            total_area_km2=total_area,
        )
        app_state.set_adaptive_plan(plan)

    def _on_execute_stage(self):
        """Send current ACTIVE stage target to the deployment pipeline."""
        plan = app_state.adaptive_plan
        if not plan or plan.is_complete:
            app_state.set_command_feedback("ADAPTIVE PLAN: No active stage to execute.")
            return

        stage = plan.active_stage
        if not stage:
            app_state.set_command_feedback("ADAPTIVE PLAN: No active stage.")
            return

        app_state.set_deployment_target(
            stage.target_lat, stage.target_lon, altitude_m=stage.target_alt_m
        )
        app_state.set_command_feedback(
            f"ADAPTIVE PLAN: Executing {stage.stage_id} ({stage.gap_id}) — "
            f"Target ({stage.target_lat:.6f}, {stage.target_lon:.6f})"
        )
        # Switch to DEPLOYMENT tab
        win = self.window()
        if hasattr(win, "right_panel") and hasattr(win.right_panel, "tabs"):
            win.right_panel.tabs.setCurrentIndex(3)

    def _on_skip_stage(self):
        """Skip the current ACTIVE stage and advance to the next."""
        app_state.skip_adaptive_stage()

    def _on_reset_adaptive_plan(self):
        """Reset the adaptive deployment plan and clear all overlays."""
        if app_state.adaptive_plan:
            from gcs.deployment.adaptive_deployment_engine import adaptive_deployment_engine
            adaptive_deployment_engine.reset_plan(app_state.adaptive_plan)
            app_state.adaptive_plan_updated.emit(app_state.adaptive_plan)
        app_state.clear_adaptive_plan()

    def _update_adaptive_ui(self, plan):
        """Refresh ADAPTIVE DEPLOYMENT card from the current plan."""
        if not plan or plan.total_stages == 0:
            self._on_adaptive_plan_cleared()
            return

        active = plan.active_stage
        idx    = plan.active_stage_index

        # Badge
        if plan.is_complete:
            self.lbl_adp_badge.setText("COMPLETE")
            self.lbl_adp_badge.setStyleSheet(
                "background-color: #238636; color: #ffffff; font-size: 9px; font-weight: 800; padding: 2px 6px; border-radius: 3px;"
            )
        else:
            self.lbl_adp_badge.setText(f"STAGE {idx}/{plan.total_stages}")
            self.lbl_adp_badge.setStyleSheet(
                "background-color: #1f6feb; color: #ffffff; font-size: 9px; font-weight: 800; padding: 2px 6px; border-radius: 3px;"
            )

        # Coverage estimates
        self.lbl_adp_cov_before.setText(f"{plan.coverage_before_pct:.0f}%")
        self.lbl_adp_cov_after.setText(f"{plan.estimated_coverage_after_pct:.0f}%")
        self.lbl_adp_stages.setText(str(plan.total_stages))

        # Active stage readouts
        if active:
            self.lbl_adp_current_stage.setText(f"{active.stage_id} — {active.gap_id}")

            priority_colors = {
                "CRITICAL": "#f85149",
                "HIGH":     "#f0883e",
                "MODERATE": "#8b949e",
            }
            self.lbl_adp_priority.setText(active.priority)
            self.lbl_adp_priority.setStyleSheet(
                f"font-size: 9px; font-weight: 700; color: {priority_colors.get(active.priority, '#8b949e')};"
            )
            self.lbl_adp_area.setText(f"{active.gap_area_km2:.3f} km²")
            self.lbl_adp_target.setText(
                f"{active.target_lat:.6f}, {active.target_lon:.6f} @ {active.target_alt_m:.0f}m"
            )
            self.lbl_adp_flight_time.setText(f"~{active.estimated_flight_time_s:.0f} s")
        else:
            for attr in ("lbl_adp_current_stage", "lbl_adp_priority",
                         "lbl_adp_area", "lbl_adp_target", "lbl_adp_flight_time"):
                getattr(self, attr).setText("--")

    def _on_adaptive_plan_cleared(self):
        """Reset adaptive deployment card to READY state."""
        self.lbl_adp_badge.setText("READY")
        self.lbl_adp_badge.setStyleSheet(
            "background-color: #21262d; color: #8b949e; font-size: 9px; font-weight: 800; "
            "padding: 2px 6px; border-radius: 3px; border: 1px solid #30363d;"
        )
        self.lbl_adp_cov_before.setText("78%")
        self.lbl_adp_cov_after.setText("--")
        self.lbl_adp_stages.setText("--")
        for attr in ("lbl_adp_current_stage", "lbl_adp_priority",
                     "lbl_adp_area", "lbl_adp_target", "lbl_adp_flight_time"):
            getattr(self, attr).setText("--")

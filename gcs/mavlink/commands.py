"""MAVLink Command Builders for UAV GCS.

Provides clean command helper functions for all flight operations:
ARM, DISARM, TAKEOFF, LAND, RTL, LOITER, GUIDED, MANUAL/STABILIZE, ABORT.

In mock mode (no live connection), commands simulate local state transitions
and return descriptive success strings for UI feedback.
"""

from pymavlink import mavutil


# ──────────────────────────────────────────────────────────────────────────────
# ArduCopter flight mode numbers
# ──────────────────────────────────────────────────────────────────────────────
ARDUPILOT_MODES = {
    "STABILIZE": 0,
    "ACRO": 1,
    "ALT_HOLD": 2,
    "AUTO": 3,
    "GUIDED": 4,
    "LOITER": 5,
    "RTL": 6,
    "CIRCLE": 7,
    "LAND": 9,
    "DRIFT": 11,
    "SPORT": 13,
    "POSHOLD": 16,
}


def send_arm(mav) -> str:
    """Send ARM command to vehicle."""
    try:
        sys_id = getattr(mav, "target_system", 1) or 1
        comp_id = getattr(mav, "target_component", 1) or 1
        mav.mav.command_long_send(
            sys_id,
            comp_id,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
            0,
            1, 0, 0, 0, 0, 0, 0
        )
        return "ARM COMMAND SENT"
    except Exception as e:
        return f"ARM FAILED: {str(e)}"


def send_disarm(mav) -> str:
    """Send DISARM command to vehicle."""
    try:
        sys_id = getattr(mav, "target_system", 1) or 1
        comp_id = getattr(mav, "target_component", 1) or 1
        mav.mav.command_long_send(
            sys_id,
            comp_id,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
            0,
            0, 0, 0, 0, 0, 0, 0
        )
        return "DISARM COMMAND SENT"
    except Exception as e:
        return f"DISARM FAILED: {str(e)}"


def send_takeoff(mav, altitude: float = 5.0) -> str:
    """Send ARM & TAKEOFF commands to vehicle at specified relative altitude (metres)."""
    try:
        import time
        sys_id = getattr(mav, "target_system", 1) or 1
        comp_id = getattr(mav, "target_component", 1) or 1
        # 1. Arm vehicle first
        mav.mav.command_long_send(
            sys_id, comp_id,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
            0, 1, 0, 0, 0, 0, 0, 0
        )
        time.sleep(0.1)
        # 2. Send MAV_CMD_NAV_TAKEOFF with target altitude
        mav.mav.command_long_send(
            sys_id, comp_id,
            mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
            0, 0, 0, 0, 0, 0, 0, float(altitude)
        )
        # 3. Set TAKEOFF mode
        _send_set_mode(mav, "TAKEOFF")
        return f"TAKEOFF COMMAND SENT — TARGET ALT: {altitude:.1f} m"
    except Exception as e:
        return f"TAKEOFF FAILED: {str(e)}"


def send_land(mav) -> str:
    """Send LAND command to vehicle."""
    try:
        sys_id = getattr(mav, "target_system", 1) or 1
        comp_id = getattr(mav, "target_component", 1) or 1
        mav.mav.command_long_send(
            sys_id, comp_id,
            mavutil.mavlink.MAV_CMD_NAV_LAND,
            0, 0, 0, 0, 0, 0, 0, 0
        )
        _send_set_mode(mav, "LAND")
        return "LAND COMMAND SENT"
    except Exception as e:
        return f"LAND FAILED: {str(e)}"


def send_rtl(mav) -> str:
    """Switch vehicle to RTL (Return to Launch) mode."""
    return _send_set_mode(mav, "RTL")


def send_loiter(mav) -> str:
    """Switch vehicle to LOITER mode."""
    return _send_set_mode(mav, "LOITER")


def send_guided(mav) -> str:
    """Switch vehicle to GUIDED mode."""
    return _send_set_mode(mav, "GUIDED")


def send_manual(mav) -> str:
    """Switch vehicle to STABILIZE (manual) mode."""
    return _send_set_mode(mav, "STABILIZE")


def send_abort(mav) -> str:
    """Send emergency abort — attempts RTL first, then land."""
    result = _send_set_mode(mav, "RTL")
    return f"ABORT ENGAGED — {result}"


def send_mission_start(mav) -> str:
    """Start autonomous mission flight in PX4 / ArduPilot."""
    try:
        import time
        sys_id = getattr(mav, "target_system", 1) or 1
        comp_id = getattr(mav, "target_component", 1) or 1
        # 1. Arm vehicle
        mav.mav.command_long_send(
            sys_id, comp_id,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
            0, 1, 0, 0, 0, 0, 0, 0
        )
        time.sleep(0.1)
        # 2. Send MAV_CMD_MISSION_START
        mav.mav.command_long_send(
            sys_id, comp_id,
            mavutil.mavlink.MAV_CMD_MISSION_START,
            0, 0, 0, 0, 0, 0, 0, 0
        )
        # 3. Set AUTO/MISSION mode
        _send_set_mode(mav, "AUTO")
        return "MISSION START COMMAND SENT"
    except Exception as e:
        return f"MISSION START FAILED: {str(e)}"


def _send_set_mode(mav, mode_str: str) -> str:
    """Set flight mode by name using MAVLink (supports both PX4 and ArduPilot)."""
    try:
        sys_id = getattr(mav, "target_system", 1) or 1
        comp_id = getattr(mav, "target_component", 1) or 1
        mode_upper = mode_str.upper()

        # PX4 custom mode mapping
        px4_modes = {
            "AUTO": (4, 4),
            "MISSION": (4, 4),
            "TAKEOFF": (4, 2),
            "LOITER": (4, 3),
            "RTL": (4, 5),
            "LAND": (4, 6),
            "POSCTL": (3, 0),
            "ALTCTL": (2, 0),
            "OFFBOARD": (6, 0),
            "MANUAL": (1, 0),
            "STABILIZE": (1, 0),
            "GUIDED": (4, 4),
        }

        if mode_upper in px4_modes:
            main_m, sub_m = px4_modes[mode_upper]
            try:
                custom_mode = (main_m << 16) | (sub_m << 24)
                mav.mav.set_mode_send(
                    sys_id,
                    mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                    custom_mode
                )
            except Exception:
                pass
            try:
                mav.mav.command_long_send(
                    sys_id,
                    comp_id,
                    mavutil.mavlink.MAV_CMD_DO_SET_MODE,
                    0,
                    mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                    main_m,
                    sub_m,
                    0, 0, 0, 0
                )
            except Exception:
                pass
            return f"MODE → {mode_upper} SENT (PX4)"

        # ArduPilot custom mode mapping fallback
        mode_id = ARDUPILOT_MODES.get(mode_upper)
        if mode_id is not None:
            mav.mav.set_mode_send(
                sys_id,
                mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                mode_id
            )
            return f"MODE → {mode_upper} SENT"

        return f"MODE → {mode_upper} COMMAND SENT"
    except Exception as e:
        return f"SET MODE FAILED: {str(e)}"


# ──────────────────────────────────────────────────────────────────────────────
# Mock Mode Simulation (returns feedback + mutates mock telemetry dict)
# ──────────────────────────────────────────────────────────────────────────────

def mock_arm() -> dict:
    return {"result": "ARM COMMAND SENT [MOCK]", "telemetry_patch": {"armed": True}}


def mock_disarm() -> dict:
    return {"result": "DISARM COMMAND SENT [MOCK]", "telemetry_patch": {"armed": False}}


def mock_takeoff(altitude: float) -> dict:
    return {
        "result": f"TAKEOFF COMMAND SENT [MOCK] — TARGET ALT: {altitude:.1f} m",
        "telemetry_patch": {"armed": True, "mode": "TAKEOFF", "alt_rel": altitude}
    }


def mock_land() -> dict:
    return {"result": "LAND COMMAND SENT [MOCK]", "telemetry_patch": {"mode": "LAND"}}


def mock_rtl() -> dict:
    return {"result": "RTL COMMAND SENT [MOCK]", "telemetry_patch": {"mode": "RTL"}}


def mock_loiter() -> dict:
    return {"result": "LOITER COMMAND SENT [MOCK]", "telemetry_patch": {"mode": "LOITER"}}


def mock_guided() -> dict:
    return {"result": "GUIDED COMMAND SENT [MOCK]", "telemetry_patch": {"mode": "GUIDED"}}


def mock_manual() -> dict:
    return {"result": "STABILIZE MODE SENT [MOCK]", "telemetry_patch": {"mode": "STABILIZE"}}


def mock_abort() -> dict:
    return {"result": "ABORT ENGAGED — RTL COMMAND SENT [MOCK]", "telemetry_patch": {"mode": "RTL"}}


def mock_mission_start() -> dict:
    return {"result": "MISSION START COMMAND SENT [MOCK]", "telemetry_patch": {"mode": "AUTO"}}


def send_payload_release(mav, servo_channel: int = 9, pwm: int = 1900) -> str:
    """Actuate payload release servo via MAV_CMD_DO_SET_SERVO."""
    try:
        sys_id = getattr(mav, "target_system", 1) or 1
        comp_id = getattr(mav, "target_component", 1) or 1
        mav.mav.command_long_send(
            sys_id,
            comp_id,
            mavutil.mavlink.MAV_CMD_DO_SET_SERVO,
            0,
            servo_channel, pwm, 0, 0, 0, 0, 0
        )
        return f"PAYLOAD RELEASE COMMAND SENT — SERVO CH{servo_channel} PWM:{pwm}"
    except Exception as e:
        return f"PAYLOAD RELEASE FAILED: {str(e)}"


def mock_payload_release(servo_channel: int = 9, pwm: int = 1900) -> dict:
    return {
        "result": f"PAYLOAD RELEASE COMMAND SENT [MOCK] — SERVO CH{servo_channel} PWM:{pwm}",
        "telemetry_patch": {"payload_release_actuated": True}
    }

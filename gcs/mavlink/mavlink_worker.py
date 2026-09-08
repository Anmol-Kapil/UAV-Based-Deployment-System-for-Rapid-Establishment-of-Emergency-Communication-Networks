"""MAVLink & MAVSDK Background Worker Thread.

Powered by MAVSDK (Headless API). Provides high-level asynchronous PX4 autopilot control
including native MissionPlan/MissionItem object modeling, Action plugin flight operations,
continuous 10Hz manual remote control, and mock SITL simulation fallback.
"""

from gcs.mavlink.mavsdk_worker import QMavsdkWorker


class QMavlinkWorker(QMavsdkWorker):
    """Background worker thread consuming MAVSDK / MAVLink packet streams."""
    pass

"""
gcs/network/backend_client.py

Phase 16: Async REST API Client (BackendClient)
Interfaces the PySide6 Ground Control Station (GCS) with the FastAPI REST server
running in backend/main.py. Supports dual-mode operation (Remote REST API vs
Local Embedded PySide6 Engine) and background thread request execution via Qt signals.
"""

import json
import logging
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional, Callable

from PySide6.QtCore import QObject, QThread, Signal

logger = logging.getLogger(__name__)


class BackendApiError(Exception):
    """Custom exception raised when backend HTTP requests fail."""

    def __init__(self, status_code: int, message: str):
        super().__init__(f"Backend API Error [{status_code}]: {message}")
        self.status_code = status_code
        self.message = message


class BackendWorkerThread(QThread):
    """Worker thread for executing HTTP requests without blocking PySide6 main loop."""

    success = Signal(object)  # Emits payload (dict or list)
    error = Signal(str)      # Emits error message string

    def __init__(self, func: Callable, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            res = self.func(*self.args, **self.kwargs)
            self.success.emit(res)
        except Exception as e:
            self.error.emit(str(e))


class BackendClient(QObject):
    """
    REST API Client for communicating with the FastAPI backend server (http://localhost:8000).

    Signals emitted:
      - connection_changed(bool)
      - status_received(dict) / status_error(str)
      - area_posted(dict) / area_error(str)
      - analysis_received(dict) / analysis_error(str)
      - candidates_received(dict) / candidates_error(str)
      - target_selected(dict) / target_error(str)
      - mission_generated(dict) / mission_error(str)
      - nodes_received(list) / nodes_error(str)
      - missions_received(list) / missions_error(str)
      - deployments_received(list) / deployments_error(str)
    """

    connection_changed = Signal(bool)

    status_received = Signal(dict)
    status_error = Signal(str)

    area_posted = Signal(dict)
    area_error = Signal(str)

    analysis_received = Signal(dict)
    analysis_error = Signal(str)

    candidates_received = Signal(dict)
    candidates_error = Signal(str)

    target_selected = Signal(dict)
    target_error = Signal(str)

    mission_generated = Signal(dict)
    mission_error = Signal(str)

    nodes_received = Signal(list)
    nodes_error = Signal(str)

    missions_received = Signal(list)
    missions_error = Signal(str)

    deployments_received = Signal(list)
    deployments_error = Signal(str)

    def __init__(self, base_url: str = "http://localhost:8000"):
        super().__init__()
        self.base_url = base_url.rstrip("/")
        self.is_connected = False
        self._active_workers: List[BackendWorkerThread] = []

    def set_base_url(self, url: str):
        """Update backend server URL."""
        self.base_url = url.rstrip("/")

    # ---------------------------------------------------------------------------
    # Core HTTP helper methods (synchronous execution)
    # ---------------------------------------------------------------------------

    def _http_request(
        self, endpoint: str, method: str = "GET", payload: Optional[Dict] = None, timeout: float = 5.0
    ) -> Any:
        """Executes an HTTP request synchronously using urllib."""
        url = f"{self.base_url}{endpoint}"
        headers = {"Accept": "application/json"}
        data = None

        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                body = response.read().decode("utf-8")
                if response.status >= 400:
                    raise BackendApiError(response.status, body)
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8") if e.fp else str(e)
            try:
                err_json = json.loads(err_body)
                detail = err_json.get("detail", err_body)
            except Exception:
                detail = err_body
            raise BackendApiError(e.code, str(detail))
        except urllib.error.URLError as e:
            raise BackendApiError(0, f"Connection failed: {e.reason}")
        except Exception as e:
            raise BackendApiError(0, f"Unexpected request failure: {str(e)}")

    def _spawn_worker(self, func: Callable, args: tuple, success_sig: Signal, error_sig: Signal):
        """Spawns an async worker thread and connects signals."""
        worker = BackendWorkerThread(func, *args)

        def _on_success(res):
            self._update_connection_state(True)
            success_sig.emit(res)
            self._cleanup_worker(worker)

        def _on_error(err_str):
            self._update_connection_state(False)
            error_sig.emit(err_str)
            self._cleanup_worker(worker)

        worker.success.connect(_on_success)
        worker.error.connect(_on_error)
        self._active_workers.append(worker)
        worker.start()

    def _cleanup_worker(self, worker: BackendWorkerThread):
        """Remove completed worker reference."""
        if worker in self._active_workers:
            self._active_workers.remove(worker)

    def _update_connection_state(self, connected: bool):
        self.is_connected = connected
        self.connection_changed.emit(connected)


    # ---------------------------------------------------------------------------
    # Synchronous API Methods (for direct testing or synchronous calls)
    # ---------------------------------------------------------------------------

    def check_status_sync(self) -> Dict[str, Any]:
        res = self._http_request("/api/status", method="GET")
        self._update_connection_state(True)
        return res

    def post_area_sync(self, polygon: List[Dict[str, float]]) -> Dict[str, Any]:
        payload = {"polygon": polygon}
        return self._http_request("/api/area", method="POST", payload=payload)

    def analyze_coverage_sync(self) -> Dict[str, Any]:
        return self._http_request("/api/analyze", method="POST")

    def get_candidates_sync(self) -> Dict[str, Any]:
        return self._http_request("/api/candidates", method="GET")

    def select_target_sync(self, lat: float, lon: float) -> Dict[str, Any]:
        payload = {"lat": lat, "lon": lon}
        return self._http_request("/api/select-target", method="POST", payload=payload)

    def generate_mission_sync(self, lat: float, lon: float, altitude_m: float = 30.0) -> Dict[str, Any]:
        payload = {"lat": lat, "lon": lon, "altitude_m": altitude_m}
        return self._http_request("/api/mission/generate", method="POST", payload=payload)

    def get_nodes_sync(self) -> List[Dict[str, Any]]:
        return self._http_request("/api/nodes", method="GET")

    def get_missions_sync(self) -> List[Dict[str, Any]]:
        return self._http_request("/api/missions", method="GET")

    def get_deployments_sync(self) -> List[Dict[str, Any]]:
        return self._http_request("/api/deployments", method="GET")

    # ---------------------------------------------------------------------------
    # Asynchronous API Methods (using QThread signals)
    # ---------------------------------------------------------------------------

    def check_status(self):
        """Asynchronously request /api/status."""
        self._spawn_worker(self.check_status_sync, (), self.status_received, self.status_error)

    def post_area(self, polygon: List[Dict[str, float]]):
        """Asynchronously post polygon to /api/area."""
        self._spawn_worker(self.post_area_sync, (polygon,), self.area_posted, self.area_error)

    def analyze_coverage(self):
        """Asynchronously trigger /api/analyze."""
        self._spawn_worker(self.analyze_coverage_sync, (), self.analysis_received, self.analysis_error)

    def get_candidates(self):
        """Asynchronously get candidate sites from /api/candidates."""
        self._spawn_worker(self.get_candidates_sync, (), self.candidates_received, self.candidates_error)

    def select_target(self, lat: float, lon: float):
        """Asynchronously post target selection to /api/select-target."""
        self._spawn_worker(self.select_target_sync, (lat, lon), self.target_selected, self.target_error)

    def generate_mission(self, lat: float, lon: float, altitude_m: float = 30.0):
        """Asynchronously trigger /api/mission/generate."""
        self._spawn_worker(
            self.generate_mission_sync, (lat, lon, altitude_m), self.mission_generated, self.mission_error
        )

    def get_nodes(self):
        """Asynchronously fetch nodes list from /api/nodes."""
        self._spawn_worker(self.get_nodes_sync, (), self.nodes_received, self.nodes_error)

    def get_missions(self):
        """Asynchronously fetch mission history from /api/missions."""
        self._spawn_worker(self.get_missions_sync, (), self.missions_received, self.missions_error)

    def get_deployments(self):
        """Asynchronously fetch deployment history from /api/deployments."""
        self._spawn_worker(self.get_deployments_sync, (), self.deployments_received, self.deployments_error)


# Global singleton instance
backend_client = BackendClient()

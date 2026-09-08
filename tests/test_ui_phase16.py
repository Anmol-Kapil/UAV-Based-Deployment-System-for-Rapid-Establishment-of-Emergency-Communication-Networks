"""
tests/test_ui_phase16.py

Phase 16: Backend FastAPI Integration & Async REST Client
Unit and integration tests for:
  - BackendApiError custom exception
  - BackendClient synchronous and asynchronous REST requests
  - Integration with FastAPI test server (backend/main.py)
  - AppState Phase 16 signals and state attributes
  - LeftPanel REST API status badge and ping interaction
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QCoreApplication

# Ensure Qt application exists
app = QApplication.instance() or QApplication(sys.argv)

from gcs.state.app_state import app_state
from gcs.network.backend_client import BackendClient, BackendApiError, BackendWorkerThread, backend_client
from gcs.widgets.left_panel import LeftPanel

# FastAPI TestClient
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from fastapi.testclient import TestClient
from backend.main import app as fastapi_app, session_state


class TestPhase16BackendClientSync(unittest.TestCase):
    """Test BackendClient synchronous methods using FastAPI TestClient mock adapter."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(fastapi_app)

    def setUp(self):
        # Reset session state in FastAPI backend
        session_state["polygon"] = None
        session_state["last_coverage"] = None
        session_state["last_candidates"] = None
        session_state["last_scored"] = None
        session_state["selected_target"] = None
        session_state["mission_state"] = "PLANNING"

    def test_01_backend_api_error(self):
        """Test BackendApiError exception attributes and string formatting."""
        err = BackendApiError(404, "Not Found")
        self.assertEqual(err.status_code, 404)
        self.assertEqual(err.message, "Not Found")
        self.assertIn("Backend API Error [404]: Not Found", str(err))

    def test_02_status_endpoint(self):
        """Test /api/status endpoint response parsing."""
        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["phase"], 5)
        self.assertFalse(data["uav_connected"])
        self.assertFalse(data["area_defined"])

    def test_03_nodes_endpoint(self):
        """Test /api/nodes endpoint returns node list."""
        response = self.client.get("/api/nodes")
        self.assertEqual(response.status_code, 200)
        nodes = response.json()
        self.assertIsInstance(nodes, list)
        if len(nodes) > 0:
            self.assertIn("id", nodes[0])
            self.assertIn("lat", nodes[0])
            self.assertIn("lon", nodes[0])

    def test_04_area_and_analyze_flow(self):
        """Test POST /api/area followed by POST /api/analyze."""
        polygon = [
            {"lat": 37.774, "lon": -122.420},
            {"lat": 37.780, "lon": -122.420},
            {"lat": 37.780, "lon": -122.410},
            {"lat": 37.774, "lon": -122.410},
        ]
        # 1. Post Area
        area_res = self.client.post("/api/area", json={"polygon": polygon})
        self.assertEqual(area_res.status_code, 200)
        self.assertTrue(area_res.json()["accepted"])
        self.assertEqual(area_res.json()["point_count"], 4)

        # 2. Status now reflects area defined
        status_res = self.client.get("/api/status")
        self.assertTrue(status_res.json()["area_defined"])

        # 3. Analyze Coverage
        analyze_res = self.client.post("/api/analyze")
        self.assertEqual(analyze_res.status_code, 200)
        cov_data = analyze_res.json()
        self.assertGreater(cov_data["total_points"], 0)
        self.assertIn("coverage_percentage", cov_data)
        self.assertIn("gap_percentage", cov_data)

    def test_05_candidates_and_target_selection(self):
        """Test GET /api/candidates, POST /api/select-target, and POST /api/mission/generate."""
        polygon = [
            {"lat": 37.774, "lon": -122.420},
            {"lat": 37.780, "lon": -122.420},
            {"lat": 37.780, "lon": -122.410},
            {"lat": 37.774, "lon": -122.410},
        ]
        self.client.post("/api/area", json={"polygon": polygon})
        self.client.post("/api/analyze")

        # GET candidates
        cand_res = self.client.get("/api/candidates")
        self.assertEqual(cand_res.status_code, 200)
        cand_data = cand_res.json()
        self.assertIn("candidates", cand_data)
        self.assertIn("top", cand_data)
        self.assertGreater(len(cand_data["candidates"]), 0)

        # Pick top candidate coordinates
        target_cand = cand_data["candidates"][0]
        t_lat, t_lon = target_cand["lat"], target_cand["lon"]

        # POST select-target
        sel_res = self.client.post("/api/select-target", json={"lat": t_lat, "lon": t_lon})
        self.assertEqual(sel_res.status_code, 200)
        self.assertTrue(sel_res.json()["accepted"])

        # POST mission/generate
        gen_res = self.client.post("/api/mission/generate", json={"lat": t_lat, "lon": t_lon, "altitude_m": 35.0})
        self.assertEqual(gen_res.status_code, 200)
        mission_data = gen_res.json()
        self.assertEqual(mission_data["status"], "MISSION_READY")
        self.assertEqual(mission_data["target_alt"], 35.0)

    def test_06_history_endpoints(self):
        """Test GET /api/missions and GET /api/deployments."""
        missions_res = self.client.get("/api/missions")
        self.assertEqual(missions_res.status_code, 200)
        self.assertIsInstance(missions_res.json(), list)

        deployments_res = self.client.get("/api/deployments")
        self.assertEqual(deployments_res.status_code, 200)
        self.assertIsInstance(deployments_res.json(), list)

    def test_07_not_implemented_stubs(self):
        """Test MAVLink-dependent 501 stubs."""
        send_res = self.client.post("/api/mission/send")
        self.assertEqual(send_res.status_code, 501)
        self.assertEqual(send_res.json()["phase_required"], 6)

        abort_res = self.client.post("/api/mission/abort")
        self.assertEqual(abort_res.status_code, 501)
        self.assertEqual(abort_res.json()["phase_required"], 6)


class TestPhase16BackendClientMocked(unittest.TestCase):
    """Test BackendClient wrapper methods using mocked _http_request calls."""

    def setUp(self):
        self.client = BackendClient("http://localhost:8000")

    def test_01_set_base_url(self):
        """Test set_base_url stripping trailing slashes."""
        self.client.set_base_url("http://192.168.1.100:8000/")
        self.assertEqual(self.client.base_url, "http://192.168.1.100:8000")

    @patch.object(BackendClient, "_http_request")
    def test_02_sync_wrappers(self, mock_req):
        """Test that sync helper methods invoke _http_request with correct arguments."""
        mock_req.return_value = {"status": "ok"}

        res = self.client.check_status_sync()
        mock_req.assert_called_with("/api/status", method="GET")
        self.assertTrue(self.client.is_connected)

        poly = [{"lat": 10.0, "lon": 20.0}]
        self.client.post_area_sync(poly)
        mock_req.assert_called_with("/api/area", method="POST", payload={"polygon": poly})

        self.client.analyze_coverage_sync()
        mock_req.assert_called_with("/api/analyze", method="POST")

        self.client.get_candidates_sync()
        mock_req.assert_called_with("/api/candidates", method="GET")

        self.client.select_target_sync(10.0, 20.0)
        mock_req.assert_called_with("/api/select-target", method="POST", payload={"lat": 10.0, "lon": 20.0})

        self.client.generate_mission_sync(10.0, 20.0, 40.0)
        mock_req.assert_called_with(
            "/api/mission/generate", method="POST", payload={"lat": 10.0, "lon": 20.0, "altitude_m": 40.0}
        )

        self.client.get_nodes_sync()
        mock_req.assert_called_with("/api/nodes", method="GET")

        self.client.get_missions_sync()
        mock_req.assert_called_with("/api/missions", method="GET")

        self.client.get_deployments_sync()
        mock_req.assert_called_with("/api/deployments", method="GET")


class TestPhase16BackendWorkerThread(unittest.TestCase):
    """Test BackendWorkerThread execution and signal emissions."""

    def test_01_worker_success(self):
        """Test BackendWorkerThread emitting success signal on function return."""
        def dummy_func(x, y):
            return x + y

        worker = BackendWorkerThread(dummy_func, 10, 20)
        results = []

        worker.success.connect(lambda res: results.append(res), Qt.ConnectionType.DirectConnection)
        worker.start()
        worker.wait()
        QCoreApplication.processEvents()

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0], 30)

    def test_02_worker_error(self):
        """Test BackendWorkerThread emitting error signal on exception."""
        def failing_func():
            raise ValueError("Test Error")

        worker = BackendWorkerThread(failing_func)
        errors = []

        worker.error.connect(lambda err: errors.append(err), Qt.ConnectionType.DirectConnection)
        worker.start()
        worker.wait()
        QCoreApplication.processEvents()

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0], "Test Error")


class TestPhase16AppStateIntegration(unittest.TestCase):
    """Test AppState Phase 16 signals and helper methods."""

    def setUp(self):
        app_state.backend_connected = False

    def test_01_set_backend_connected(self):
        """Test set_backend_connected emits backend_connection_changed signal."""
        events = []
        app_state.backend_connection_changed.connect(lambda val: events.append(val))

        app_state.set_backend_connected(True)
        self.assertTrue(app_state.backend_connected)
        self.assertEqual(events, [True])

        # Setting same state should not re-emit
        app_state.set_backend_connected(True)
        self.assertEqual(len(events), 1)

        # Transition back to false
        app_state.set_backend_connected(False)
        self.assertFalse(app_state.backend_connected)
        self.assertEqual(events, [True, False])

    @patch.object(backend_client, "check_status")
    def test_02_fetch_backend_status(self, mock_check):
        """Test fetch_backend_status invokes backend_client.check_status()."""
        app_state.fetch_backend_status()
        mock_check.assert_called_once()

    @patch.object(backend_client, "post_area")
    def test_03_post_area_to_backend(self, mock_post):
        """Test post_area_to_backend invokes backend_client.post_area()."""
        poly = [{"lat": 1.0, "lon": 2.0}]
        app_state.post_area_to_backend(poly)
        mock_post.assert_called_once_with(poly)


class TestPhase16LeftPanelIntegration(unittest.TestCase):
    """Test LeftPanel REST API status label and ping interactions."""

    def setUp(self):
        self.left_panel = LeftPanel()

    def test_01_rest_api_status_widget_exists(self):
        """Test LeftPanel contains REST API status label and ping button."""
        self.assertIsNotNone(self.left_panel.lbl_rest_status)
        self.assertIsNotNone(self.left_panel.btn_check_rest)
        self.assertIn("OFFLINE", self.left_panel.lbl_rest_status.text())

    def test_02_backend_connection_changed_updates_label(self):
        """Test emitting app_state.backend_connection_changed updates LeftPanel status label."""
        app_state.set_backend_connected(True)
        QCoreApplication.processEvents()
        self.assertIn("ONLINE", self.left_panel.lbl_rest_status.text())

        app_state.set_backend_connected(False)
        QCoreApplication.processEvents()
        self.assertIn("OFFLINE", self.left_panel.lbl_rest_status.text())


if __name__ == "__main__":
    unittest.main()

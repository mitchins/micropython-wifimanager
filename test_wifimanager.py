"""Unit tests for wifi_manager.py"""
import base64
import json
import os
import unittest
import sys
import re
import tempfile
from pathlib import Path
from unittest.mock import patch

from test import network as fake_network
from test import webrepl as fake_webrepl
from test import logging as fake_logging

sys.modules['network'] = fake_network
sys.modules['webrepl'] = fake_webrepl
sys.modules['logging'] = fake_logging

# That upon which we test
import wifi_manager

TEST_ROOT = Path(__file__).resolve().parent

# The tests

class SchedulerTests(unittest.TestCase):
    def test_scheduler_basic(self):
        # Basic test to ensure the test framework works
        self.assertTrue(hasattr(wifi_manager, "__version__"))

    def test_version_metadata_is_synced(self):
        with open(TEST_ROOT / "wifi_manager" / "metadata.txt", "r") as metadata_file:
            metadata = metadata_file.read()
        match = re.search(r"(?m)^version = (.+)$", metadata)
        self.assertIsNotNone(match)
        version = match.group(1).strip()

        self.assertEqual(wifi_manager.__version__, version)
        self.assertIn(f"version = {version}", metadata)

        with open(TEST_ROOT / "wifi_manager" / "setup.py", "r") as setup_file:
            setup = setup_file.read()
        self.assertRegex(setup, rf"(?m)^version = ['\"]{re.escape(version)}['\"]$")
        self.assertIn("version = version", setup)


class FakeReceiveConnection:
    def __init__(self, chunks):
        self._chunks = list(chunks)

    def recv(self, _size):
        if self._chunks:
            return self._chunks.pop(0)
        return b""


class FakeSendConnection:
    def __init__(self, max_chunk_size):
        self.max_chunk_size = max_chunk_size
        self.payload = b""

    def send(self, data):
        chunk = data[:self.max_chunk_size]
        self.payload += chunk
        return len(chunk)


class WifiManagerHelperTests(unittest.TestCase):
    def setUp(self):
        self.manager = wifi_manager.WifiManager
        self.original_state = {
            "config_file": self.manager.config_file,
            "_config_server_password": self.manager._config_server_password,
            "_config_server_enabled": self.manager._config_server_enabled,
            "_config_server_task": self.manager._config_server_task,
            "_connection_callbacks": list(self.manager._connection_callbacks),
            "_last_connection_state": self.manager._last_connection_state,
            "webrepl_triggered": self.manager.webrepl_triggered,
        }
        self.original_ubinascii = sys.modules.pop("ubinascii", None)
        fake_network.DEBUG_RESET()
        self.temp_paths = []

    def tearDown(self):
        self.manager.config_file = self.original_state["config_file"]
        self.manager._config_server_password = self.original_state["_config_server_password"]
        self.manager._config_server_enabled = self.original_state["_config_server_enabled"]
        self.manager._config_server_task = self.original_state["_config_server_task"]
        self.manager._connection_callbacks = self.original_state["_connection_callbacks"]
        self.manager._last_connection_state = self.original_state["_last_connection_state"]
        self.manager.webrepl_triggered = self.original_state["webrepl_triggered"]
        if self.original_ubinascii is not None:
            sys.modules["ubinascii"] = self.original_ubinascii
        for path in self.temp_paths:
            if os.path.exists(path):
                os.unlink(path)

    def _make_temp_config(self, config):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w") as config_file:
            json.dump(config, config_file)
        self.temp_paths.append(path)
        return path

    @staticmethod
    def _auth_request(method, path, password, body=""):
        credentials = base64.b64encode(("admin:%s" % password).encode()).decode()
        request = [
            "%s %s HTTP/1.1" % (method, path),
            "Authorization: Basic %s" % credentials,
        ]
        if body:
            request.append("Content-Length: %d" % len(body))
        request.append("")
        request.append(body)
        return "\r\n".join(request)

    @staticmethod
    def _response_body(response):
        return response.split("\r\n\r\n", 1)[1]

    def test_load_config_normalizes_access_point_and_starts_server(self):
        config_path = self._make_temp_config({
            "schema": 2,
            "known_networks": [{"ssid": "HomeNetwork", "password": "sekret"}],
            "access_point": {
                "essid": "FlatAP",
                "channel": 6,
                "password": "flatpass",
                "enables_webrepl": True,
                "start_policy": "fallback",
            },
            "config_server": {"enabled": True, "password": "adminpass"},
        })
        self.manager.config_file = config_path

        with patch.object(self.manager, "start_config_server", return_value=True) as start_server:
            self.assertTrue(self.manager._load_config())

        self.assertEqual(self.manager.preferred_networks[0]["ssid"], "HomeNetwork")
        self.assertEqual(self.manager.ap_config["config"]["essid"], "FlatAP")
        self.assertEqual(self.manager.ap_config["config"]["password"], "flatpass")
        self.assertEqual(self.manager.ap_config["start_policy"], "fallback")
        start_server.assert_called_once_with("adminpass")

    def test_load_config_missing_file_falls_back_to_recovery_ap(self):
        self.manager.config_file = "/tmp/definitely-missing-wifimanager-config.json"

        with patch.object(self.manager, "start_config_server", return_value=True) as start_server:
            self.assertFalse(self.manager._load_config())

        self.assertEqual(self.manager.preferred_networks, [])
        self.assertEqual(self.manager.ap_config["config"]["essid"], "MicroPython-AP")
        self.assertEqual(self.manager.ap_config["start_policy"], "always")
        start_server.assert_called_once_with(self.manager._config_server_password)

    def test_load_config_invalid_shape_falls_back_to_recovery_ap(self):
        config_path = self._make_temp_config({
            "schema": 2,
            "known_networks": "not-a-list",
            "access_point": {"config": {"essid": "BadAP"}},
        })
        self.manager.config_file = config_path

        with patch.object(self.manager, "start_config_server", return_value=True) as start_server:
            self.assertFalse(self.manager._load_config())

        self.assertEqual(self.manager.preferred_networks, [])
        self.assertEqual(self.manager.ap_config["config"]["essid"], "MicroPython-AP")
        start_server.assert_called_once_with(self.manager._config_server_password)

    def test_check_basic_auth_accepts_valid_credentials(self):
        self.manager._config_server_password = "secret"
        request = self._auth_request("GET", "/config", "secret")
        self.assertTrue(self.manager._check_basic_auth(request))
        self.assertFalse(self.manager._check_basic_auth("GET /config HTTP/1.1\r\n\r\n"))

    def test_handle_config_request_get_masks_passwords(self):
        config_path = self._make_temp_config({
            "schema": 2,
            "known_networks": [{"ssid": "HomeNetwork", "password": "wifi-pass"}],
            "access_point": {
                "config": {"essid": "AP", "password": "ap-pass"},
                "enables_webrepl": False,
                "start_policy": "never",
            },
        })
        self.manager.config_file = config_path
        self.manager._config_server_password = "secret"

        response = self.manager._handle_config_request(
            self._auth_request("GET", "/config", "secret")
        )

        body = json.loads(self._response_body(response))
        self.assertEqual(body["known_networks"][0]["password"], "***")
        self.assertEqual(body["access_point"]["config"]["password"], "***")

    def test_handle_config_request_post_preserves_masked_passwords(self):
        config_path = self._make_temp_config({
            "schema": 2,
            "known_networks": [{"ssid": "HomeNetwork", "password": "wifi-pass"}],
            "access_point": {
                "config": {"essid": "AP", "password": "ap-pass"},
                "enables_webrepl": False,
                "start_policy": "never",
            },
        })
        self.manager.config_file = config_path
        self.manager._config_server_password = "secret"
        payload = json.dumps({
            "schema": 2,
            "known_networks": [{"ssid": "HomeNetwork", "password": "***"}],
            "access_point": {
                "config": {"essid": "UpdatedAP", "password": "***"},
                "enables_webrepl": False,
                "start_policy": "never",
            },
        })

        with patch.object(self.manager, "setup_network", return_value=True) as setup_network:
            response = self.manager._handle_config_request(
                self._auth_request("POST", "/config", "secret", payload)
            )

        with open(config_path, "r") as config_file:
            stored = json.load(config_file)

        self.assertIn("200 OK", response)
        self.assertEqual(stored["known_networks"][0]["password"], "wifi-pass")
        self.assertEqual(stored["access_point"]["config"]["password"], "ap-pass")
        self.assertEqual(stored["access_point"]["config"]["essid"], "UpdatedAP")
        setup_network.assert_called_once_with()

    def test_handle_config_request_post_preserves_masked_passwords_by_ssid(self):
        config_path = self._make_temp_config({
            "schema": 2,
            "known_networks": [
                {"ssid": "HomeNetwork", "password": "home-pass"},
                {"ssid": "OfficeNetwork", "password": "office-pass"},
            ],
            "access_point": {
                "config": {"essid": "AP", "password": "ap-pass"},
                "enables_webrepl": False,
                "start_policy": "never",
            },
        })
        self.manager.config_file = config_path
        self.manager._config_server_password = "secret"
        payload = json.dumps({
            "schema": 2,
            "known_networks": [
                {"ssid": "OfficeNetwork", "password": "***"},
                {"ssid": "HomeNetwork", "password": "***"},
            ],
            "access_point": {
                "config": {"essid": "AP", "password": "***"},
                "enables_webrepl": False,
                "start_policy": "never",
            },
        })

        with patch.object(self.manager, "setup_network", return_value=True):
            response = self.manager._handle_config_request(
                self._auth_request("POST", "/config", "secret", payload)
            )

        with open(config_path, "r") as config_file:
            stored = json.load(config_file)

        self.assertIn("200 OK", response)
        self.assertEqual(stored["known_networks"][0]["password"], "office-pass")
        self.assertEqual(stored["known_networks"][1]["password"], "home-pass")

    def test_handle_config_request_requires_auth(self):
        self.manager._config_server_password = "secret"
        response = self.manager._handle_config_request("GET /config HTTP/1.1\r\n\r\n")
        self.assertIn("401 Unauthorized", response)

    def test_read_http_request_and_send_http_response(self):
        request = (
            b"POST /config HTTP/1.1\r\nHost: test\r\nContent-Length: 5\r\n\r\nhe",
            b"llo",
        )
        received = self.manager._read_http_request(FakeReceiveConnection(request))
        sender = FakeSendConnection(max_chunk_size=4)
        self.manager._send_http_response(sender, "HTTP/1.1 200 OK\r\n\r\nhello")

        self.assertIn("Content-Length: 5", received)
        self.assertTrue(received.endswith("hello"))
        self.assertEqual(sender.payload.decode(), "HTTP/1.1 200 OK\r\n\r\nhello")

    def test_read_http_request_rejects_oversized_requests(self):
        oversized = (
            b"POST /config HTTP/1.1\r\nContent-Length: 20000\r\n\r\n",
            b"x" * 128,
        )
        with self.assertRaises(ValueError):
            self.manager._read_http_request(FakeReceiveConnection(oversized))

    def test_scan_available_networks_sorts_and_skips_invalid_entries(self):
        interface = fake_network.WLAN(fake_network.STA_IF)
        interface.scan_results = [
            (b"HomeNetwork", b"\x01\x02\x03\x04\x05\x06", 1, -80, 3, False),
            (b"\xff", b"\x01\x02\x03\x04\x05\x07", 1, -10, 3, False),
            (b"Office", b"\x01\x02\x03\x04\x05\x08", 6, -40, 3, False),
        ]

        networks = self.manager._scan_available_networks()

        self.assertEqual([network["ssid"] for network in networks], ["Office", "HomeNetwork"])

    def test_build_connection_candidates_skips_non_dict_preferences(self):
        self.manager.preferred_networks = [
            "HomeNetwork",
            {"ssid": "Office", "password": "secret", "enables_webrepl": True},
        ]

        candidates = self.manager._build_connection_candidates([
            {"ssid": "Office", "bssid": b"\x01\x02\x03\x04\x05\x06", "strength": -20},
        ])

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["ssid"], "Office")

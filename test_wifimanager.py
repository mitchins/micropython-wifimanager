"""Unit tests for wifi_manager.py"""
import functools
import unittest
import sys
import re
from pathlib import Path

sys.modules['network'] = __import__('fake_network')

# That upon which we test
import wifi_manager

TEST_ROOT = Path(__file__).resolve().parent

# The tests

class SchedulerTests(unittest.TestCase):

    def setUp(self):
        #if 'network' in sys.modules:
        #	del sys.modules['network']
        pass

    def test_scheduler_basic(self):
        # Basic test to ensure the test framework works
        self.assertTrue(True)

    def test_version_metadata_is_synced(self):
        version = wifi_manager.__version__
        self.assertEqual(version, "1.0.3")

        with open(TEST_ROOT / "wifi_manager" / "metadata.txt", "r") as metadata_file:
            metadata = metadata_file.read()
        self.assertIn(f"version = {version}", metadata)

        with open(TEST_ROOT / "wifi_manager" / "setup.py", "r") as setup_file:
            setup = setup_file.read()
        self.assertRegex(setup, rf"(?m)^version = ['\"]{re.escape(version)}['\"]$")
        self.assertIn("version = version", setup)
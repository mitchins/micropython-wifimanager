"""Unit tests for wifi_manager.py"""
import functools
import unittest
import sys

sys.modules['network'] = __import__('fake_network')

# That upon which we test
import wifi_manager

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
        self.assertEqual(wifi_manager.__version__, "1.0.3")

        with open("wifi_manager/metadata.txt", "r") as metadata_file:
            metadata = metadata_file.read()
        self.assertIn("version = 1.0.3", metadata)

        with open("wifi_manager/setup.py", "r") as setup_file:
            setup = setup_file.read()
        self.assertIn("version = version", setup)
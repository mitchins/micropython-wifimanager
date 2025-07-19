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
import sys

import unittest
import uasyncio as asyncio
# Hackery - we are not and cannot test under micropython
from . import network
from . import webrepl
from . import sample_scans
from . import logging
sys.modules['network'] = network
sys.modules['webrepl'] = webrepl
sys.modules['logging'] = logging

# Important - do hackery before importing me
from wifi_manager import WifiManager

class LogicTests(unittest.TestCase):

    # Choose BSSID for a network among a list of unique SSID
    def test_fallback_choose_single(self):
        network.DEBUG_RESET()
        interface = network.WLAN(network.STA_IF)
        host = network.WLAN(network.AP_IF)
        interface.scan_results = sample_scans.scan1()
        WifiManager.config_file = 'test/networks_fallback.json'
        WifiManager.setup_network()
        # Checks on the client
        self.assertTrue(interface.isconnected())
        self.assertTrue(interface.DEBUG_CONNECTED_SSID == "HomeNetwork")
        self.assertTrue(interface.DEBUG_CONNECTED_BSSID == b'\x90r@\x1f\xf0\xe4')
        # Checks on th AP
        self.assertTrue(not host.active())

    # Choose BSSID for a network among a list with multiple instances of the SSID
    def test_fallback_choose_best(self):
        network.DEBUG_RESET()
        interface = network.WLAN(network.STA_IF)
        host = network.WLAN(network.AP_IF)
        interface.scan_results = sample_scans.scan2()
        WifiManager.config_file = 'test/networks_fallback.json'
        WifiManager.setup_network()
        # Checks on the client
        self.assertTrue(interface.isconnected())
        self.assertTrue(interface.DEBUG_CONNECTED_SSID == "HomeNetwork")
        self.assertTrue(interface.DEBUG_CONNECTED_BSSID == b'\x90r@\x1f\xf0\xe4')
        # Checks on th AP
        self.assertTrue(not host.active())

    # No known networks found and fallback AP policy so should have just the AP started
    def test_fallback_ap(self):
        network.DEBUG_RESET()
        interface = network.WLAN(network.STA_IF)
        host = network.WLAN(network.AP_IF)
        interface.scan_results = sample_scans.scan3()
        WifiManager.config_file = 'test/networks_fallback.json'
        WifiManager.setup_network()
        # Checks on the client
        self.assertTrue(not interface.isconnected())
        self.assertTrue(interface.DEBUG_CONNECTED_SSID is None)
        self.assertTrue(interface.DEBUG_CONNECTED_BSSID is None)
        # Checks on th AP
        self.assertTrue(host.active())
        self.assertTrue(host.config_dict['essid'] == "Micropython-Dev")

    # Should have both managed access and AP started as AP always policy and known networks joined
    def test_always_ap(self):
        network.DEBUG_RESET()
        interface = network.WLAN(network.STA_IF)
        host = network.WLAN(network.AP_IF)
        interface.scan_results = sample_scans.scan1()
        WifiManager.config_file = 'test/networks_always.json'
        WifiManager.setup_network()
        # Checks on the client
        self.assertTrue(interface.isconnected())
        self.assertTrue(interface.DEBUG_CONNECTED_SSID == "HomeNetwork")
        self.assertTrue(interface.DEBUG_CONNECTED_BSSID == b'\x90r@\x1f\xf0\xe4')
        # Checks on th AP
        self.assertTrue(host.active())
        self.assertTrue(host.config_dict['essid'] == "Micropython-Dev")

    # Should connect to nothing as no known networks and no AP policy
    def test_never_ap(self):
        network.DEBUG_RESET()
        interface = network.WLAN(network.STA_IF)
        host = network.WLAN(network.AP_IF)
        interface.scan_results = sample_scans.scan1()
        WifiManager.config_file = 'test/networks_always.json'
        WifiManager.setup_network()
        # Checks on the client
        self.assertTrue(interface.isconnected())
        self.assertTrue(interface.DEBUG_CONNECTED_SSID == "HomeNetwork")
        self.assertTrue(interface.DEBUG_CONNECTED_BSSID == b'\x90r@\x1f\xf0\xe4')
        # Checks on th AP
        self.assertTrue(host.active())
        self.assertTrue(host.config_dict['essid'] == "Micropython-Dev")

class AsyncTests(unittest.TestCase):

    def testStart(self):
        network.DEBUG_RESET()
        WifiManager.config_file = 'test/networks_fallback.json'
        WifiManager.start_managing()
        loop = asyncio.get_event_loop()
        async def tester():
            print("Time's up")
        # TODO: Tests here
        loop.run_until_complete(tester())
        #loop.run_until_complete()


if __name__ == '__main__':
    unittest.main()

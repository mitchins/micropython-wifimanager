"""
Test script for WiFi Manager connection callbacks
Uses mocked network module to simulate connection state changes
"""

import sys
import json
import time
import tempfile
import os
from unittest.mock import Mock

# Mock the MicroPython modules before importing wifi_manager
sys.modules['network'] = Mock()
sys.modules['webrepl'] = Mock()
sys.modules['uasyncio'] = Mock()
sys.modules['ubinascii'] = Mock()

# Mock network constants
network = sys.modules['network']
network.STA_IF = 0
network.AP_IF = 1
network.STAT_GOT_IP = 5
network.STAT_CONNECTING = 2

# Create a mock WLAN class
class MockWLAN:
    def __init__(self, interface):
        self.interface = interface
        self.is_active = False
        self.is_connected = False
        self.current_ssid = None
        self.current_ip = "192.168.1.100"
        self.scan_results = []
        
    def active(self, state=None):
        if state is not None:
            self.is_active = state
        return self.is_active
    
    def isconnected(self):
        return self.is_connected
    
    def connect(self, ssid, password, **kwargs):
        # Simulate connection attempt
        self.current_ssid = ssid
        if ssid == "TestNetwork":
            self.is_connected = True
        else:
            self.is_connected = False
    
    def scan(self):
        return self.scan_results
    
    def ifconfig(self):
        if self.is_connected:
            return (self.current_ip, "255.255.255.0", "192.168.1.1", "8.8.8.8")
        return ("0.0.0.0", "0.0.0.0", "0.0.0.0", "0.0.0.0")
    
    def config(self, param=None, **kwargs):
        if param == 'ssid':
            return self.current_ssid
        if kwargs:
            self.current_ssid = kwargs.get('essid', self.current_ssid)
        return None
    
    def status(self):
        return network.STAT_GOT_IP if self.is_connected else 0

# Mock the network.WLAN constructor
network.WLAN = MockWLAN

# Now import the wifi_manager
sys.path.append('wifi_manager')
from wifi_manager import WifiManager

class CallbackTester:
    def __init__(self):
        self.events = []
        
    def callback_handler(self, event, **kwargs):
        """Test callback that records all events"""
        self.events.append({
            'event': event,
            'kwargs': kwargs,
            'timestamp': time.time()
        })
        print(f"📡 Callback: {event} - {kwargs}")
    
    def print_events(self):
        print("\n📊 Recorded Events:")
        for i, event in enumerate(self.events):
            print(f"  {i+1}. {event['event']} - {event['kwargs']}")
    
    def assert_event_occurred(self, event_type, **expected_kwargs):
        """Check if an event with specific parameters occurred"""
        for event in self.events:
            if event['event'] == event_type:
                match = True
                for key, value in expected_kwargs.items():
                    if event['kwargs'].get(key) != value:
                        match = False
                        break
                if match:
                    return True
        return False

def create_test_config():
    """Create a test configuration file"""
    config = {
        "schema": 2,
        "known_networks": [
            {
                "ssid": "TestNetwork",
                "password": "testpass123",
                "enables_webrepl": False
            },
            {
                "ssid": "UnknownNetwork",
                "password": "badpass",
                "enables_webrepl": False
            }
        ],
        "access_point": {
            "config": {
                "essid": "TestAP",
                "channel": 11,
                "hidden": False,
                "password": "appass123"
            },
            "enables_webrepl": True,
            "start_policy": "fallback"
        }
    }
    
    # Create temporary config file
    fd, path = tempfile.mkstemp(suffix='.json')
    with os.fdopen(fd, 'w') as f:
        json.dump(config, f)
    
    return path

def test_connection_callbacks():
    """Test the connection callback functionality"""
    print("🧪 Testing WiFi Manager Connection Callbacks\n")
    
    # Create test configuration
    config_path = create_test_config()
    WifiManager.config_file = config_path
    
    # Create callback tester
    tester = CallbackTester()
    
    # Register callback
    WifiManager.on_connection_change(tester.callback_handler)
    print("✅ Registered callback handler")
    
    try:
        # Test 1: Successful connection
        print("\n🔗 Test 1: Successful Connection")
        
        # Mock available networks (include our test network)
        mock_wlan = WifiManager.wlan()
        mock_wlan.scan_results = [
            (b'TestNetwork', b'\x00\x01\x02\x03\x04\x05', 1, -50, 4, 0),  # Available
            (b'OtherNetwork', b'\x00\x01\x02\x03\x04\x06', 6, -70, 4, 0)
        ]
        
        # Setup network (should connect to TestNetwork)
        result = WifiManager.setup_network()
        print(f"Setup result: {result}")
        
        # Verify connection callback was fired
        assert tester.assert_event_occurred('connected', ssid='TestNetwork'), "❌ Connected event not found"
        print("✅ Connected event verified")
        
        # Test 2: Connection state monitoring
        print("\n📡 Test 2: Connection State Monitoring")
        
        # Simulate connection loss
        mock_wlan.is_connected = False
        WifiManager._check_and_notify_connection_state()
        
        assert tester.assert_event_occurred('disconnected'), "❌ Disconnected event not found"
        print("✅ Disconnected event verified")
        
        # Test 3: Connection failure
        print("\n❌ Test 3: Connection Failure")
        
        # Clear previous events
        tester.events.clear()
        
        # Mock no matching networks
        mock_wlan.scan_results = [
            (b'WrongNetwork', b'\x00\x01\x02\x03\x04\x07', 1, -50, 4, 0)
        ]
        mock_wlan.is_connected = False
        
        WifiManager.setup_network()
        
        # Should trigger connection_failed and ap_started
        assert tester.assert_event_occurred('connection_failed'), "❌ Connection failed event not found"
        assert tester.assert_event_occurred('ap_started', essid='TestAP'), "❌ AP started event not found"
        print("✅ Connection failure and AP fallback events verified")
        
        # Test 4: Multiple callbacks
        print("\n🔄 Test 4: Multiple Callbacks")
        
        def second_callback(event, **kwargs):
            print(f"📡 Second callback: {event}")
        
        WifiManager.on_connection_change(second_callback)
        
        # Trigger an event
        mock_wlan.is_connected = True
        WifiManager._check_and_notify_connection_state()
        
        print("✅ Multiple callbacks test completed")
        
        # Test 5: Callback removal
        print("\n🗑️  Test 5: Callback Removal")
        
        WifiManager.remove_connection_callback(second_callback)
        print("✅ Callback removal test completed")
        
        # Print all recorded events
        tester.print_events()
        
        print("\n🎉 All callback tests passed!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # Clean up
        os.unlink(config_path)
        WifiManager._connection_callbacks.clear()
        print("\n🧹 Cleanup completed")

if __name__ == '__main__':
    test_connection_callbacks()

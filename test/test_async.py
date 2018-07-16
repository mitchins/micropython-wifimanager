import sys
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
WifiManager.config_file = 'test/networks_fallback.json'
WifiManager.start_managing()
loop = asyncio.get_event_loop()
loop.run_forever()

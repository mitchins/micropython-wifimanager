"""Implementation of a controller to connect to preferred wifi network(s) [For ESP8266, micro-python]

Config is loaded from a file kept by default in '/networks.json'

Priority of networks is determined implicitly by order in array, first being the highest.
It will go through the list of preferred networks, connecting to the ones it detects present.

Default behaviour is to always start the webrepl after setup,
and only start the access point if we can't connect to a known access point ourselves.

Future scope is to use BSSID instead of SSID when micropython allows it,
this would allow multiple access points with the same name, and we can select by signal strength.


"""

import json
import time

from micropython import const
import network
import webrepl

# Describes the conditions on when to start the AP
start_ap_always = const(0)
start_ap_fallback = const(1)
start_ap_never = const(2)

# Describes the conditions on when to start the webrepl
start_wr_connected = const(0)
start_wr_connected_managed = const(1)
start_wr_connected_adhoc = const(2)


class WifiManager:
    start_ap = start_ap_fallback  # Only tart if we can't connect (default)
    start_wr = start_wr_connected  # Start with any connection (default)

    @classmethod
    def wlan(cls):
        return network.WLAN(network.STA_IF)

    @classmethod
    def accesspoint(cls):
        return network.WLAN(network.AP_IF)

    @classmethod
    def wants_accesspoint(cls) -> bool:
        if cls.start_ap == start_ap_always:
            return True
        elif cls.start_ap == start_ap_fallback:
            return not cls.wlan().isconnected()
        else:
            return False

    @classmethod
    def wants_webrepl(cls):
        if cls.start_wr == start_wr_connected:
            return cls.wlan().isconnected() or cls.accesspoint().active()
        elif cls.start_wr == start_wr_connected_managed:
            return not cls.wlan().isconnected()
        elif cls.start_wr == start_wr_connected_adhoc:
            return not cls.accesspoint().active()
        else:
            return False

    @classmethod
    def setup_network(cls, config_file='/networks.json') -> bool:
        # now see our prioritised list of networks and find the first available network
        with open(config_file, "r") as f:
            preferred_networks = json.loads(f.read())

        # set things up
        cls.wlan().active(True)

        # scan what’s available
        available_networks = {}
        for network in cls.wlan().scan():
            available_networks[network[0].decode("utf-8")] = network[1:]

        # Go over the preferred networks that are available, attempting first items or moving on if n/a
        for preference in [p for p in preferred_networks if p[0] in available_networks]:
                print("connecting to network {0}...".format(preference[0]))
                if cls.connect_to(network_ssid=preference[0], password=preference[1]):
                    break  # We are connected so don't try more

        # start the access point according to the rules
        cls.accesspoint().active(cls.wants_accesspoint())

        # start the webrepl according to the rules
        if cls.wants_webrepl():
            webrepl.start()

        # return the success status, which is ultimately if we connected to managed and not ad hoc wifi.
        return cls.wlan().isconnected()

    @classmethod
    def connect_to(cls, *, network_ssid: str, password: str) -> bool:
        cls.wlan().connect(network_ssid, password)

        for check in range(0, 10):  # Wait a maximum of 10 times (10 * 500ms = 5 seconds) for success
            if cls.wlan().isconnected():
                return True
            time.sleep_ms(500)
        return False

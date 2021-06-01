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
import os

# Micropython modules
import network
try:
    import webrepl
except ImportError:
    pass
try:
    import uasyncio as asyncio
except ImportError:
    pass

# Micropython libraries (install view uPip)
try:
    import logging
    log = logging.getLogger("wifi_manager")
except ImportError:
    # Todo: stub logging, this can probably be improved easily, though logging is common to install
    def fake_log(msg, *args):
        print("[?] No logger detected. (log dropped)")
    log = type("", (), {"debug": fake_log, "info": fake_log, "warning": fake_log, "error": fake_log,
                            "critical": fake_log})()

class WifiManager:
    webrepl_triggered = False
    _ap_start_policy = "never"
    config_file = '/networks.json'

    # Starts the managing call as a co-op async activity
    @classmethod
    def start_managing(cls):
        loop = asyncio.get_event_loop()
        loop.create_task(cls.manage()) # Schedule ASAP
        # Make sure you loop.run_forever() (we are a guest here)

    # Checks the status and configures if needed
    @classmethod
    async def manage(cls):
        while True:
            status = cls.wlan().status()
            # ESP32 does not currently return
            if (status != network.STAT_GOT_IP) or \
            (cls.wlan().ifconfig()[0] == '0.0.0.0'):  # temporary till #3967
                log.info("Network not connected: managing")
                # Ignore connecting status for now.. ESP32 is a bit strange
                # if status != network.STAT_CONNECTING: <- do not care yet
                cls.setup_network()
            await asyncio.sleep(10)  # Pause 5 seconds

    @classmethod
    def wlan(cls):
        return network.WLAN(network.STA_IF)

    @classmethod
    def accesspoint(cls):
        return network.WLAN(network.AP_IF)

    @classmethod
    def wants_accesspoint(cls) -> bool:
        static_policies = {"never": False, "always": True}
        if cls._ap_start_policy in static_policies:
            return static_policies[cls._ap_start_policy]
        # By default, that leaves "Fallback"
        return cls.wlan().status() != network.STAT_GOT_IP  # Discard intermediate states and check for not connected/ok

    @classmethod
    def setup_network(cls) -> bool:
        # now see our prioritised list of networks and find the first available network
        try:
            with open(cls.config_file, "r") as f:
                config = json.loads(f.read())
                cls.preferred_networks = config['known_networks']
                cls.ap_config = config["access_point"]
                if config.get("schema", 0) != 2:
                    log.warning("Did not get expected schema [2] in JSON config.")
        except Exception as e:
            log.error("Failed to load config file, no known networks selected")
            cls.preferred_networks = []
            return

        # set things up
        cls.webrepl_triggered = False  # Until something wants it
        cls.wlan().active(True)

        # scan what’s available
        available_networks = []
        for network in cls.wlan().scan():
            ssid = network[0].decode("utf-8")
            bssid = network[1]
            strength = network[3]
            available_networks.append(dict(ssid=ssid, bssid=bssid, strength=strength))
        # Sort fields by strongest first in case of multiple SSID access points
        available_networks.sort(key=lambda station: station["strength"], reverse=True)

        # Get the ranked list of BSSIDs to connect to, ranked by preference and strength amongst duplicate SSID
        candidates = []
        for aPreference in cls.preferred_networks:
            for aNetwork in available_networks:
                if aPreference["ssid"] == aNetwork["ssid"]:
                    connection_data = {
                        "ssid": aNetwork["ssid"],
                        "bssid": aNetwork["bssid"],  # NB: One day we might allow collection by exact BSSID
                        "password": aPreference["password"],
                        "enables_webrepl": aPreference["enables_webrepl"]}
                    candidates.append(connection_data)

        for new_connection in candidates:
            log.info("Attempting to connect to network {0}...".format(new_connection["ssid"]))
            # Micropython 1.9.3+ supports BSSID specification so let's use that
            if cls.connect_to(ssid=new_connection["ssid"], password=new_connection["password"],
                              bssid=new_connection["bssid"]):
                log.info("Successfully connected {0}".format(new_connection["ssid"]))
                cls.webrepl_triggered = new_connection["enables_webrepl"]
                break  # We are connected so don't try more


        # Check if we are to start the access point
        cls._ap_start_policy = cls.ap_config.get("start_policy", "never")
        should_start_ap = cls.wants_accesspoint()
        cls.accesspoint().active(should_start_ap)
        if should_start_ap:  # Only bother setting the config if it WILL be active
            log.info("Enabling your access point...")
            cls.accesspoint().config(**cls.ap_config["config"])
            cls.webrepl_triggered = cls.ap_config["enables_webrepl"]
        cls.accesspoint().active(cls.wants_accesspoint())  # It may be DEACTIVATED here

        # may need to reload the config if access points trigger it

        # start the webrepl according to the rules
        if cls.webrepl_triggered:
            try:
                webrepl.start()
            except NameError:
                # Log error here (not after import) to not log it if webrepl is not configured to start.
                log.error("Failed to start webrepl, module is not available.")

        # return the success status, which is ultimately if we connected to managed and not ad hoc wifi.
        return cls.wlan().isconnected()

    @classmethod
    def connect_to(cls, *, ssid, password, **kwargs) -> bool:
        cls.wlan().connect(ssid, password, **kwargs)

        for check in range(0, 10):  # Wait a maximum of 10 times (10 * 500ms = 5 seconds) for success
            if cls.wlan().isconnected():
                return True
            time.sleep_ms(500)
        return False

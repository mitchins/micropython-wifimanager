# Stubbed status
STAT_IDLE = 1
STAT_CONNECTING = 2
STAT_GOT_IP = 3
STAT_NO_AP_FOUND = 10
STAT_WRONG_PASSWORD = 11
STAT_BEACON_TIMEOUT = 12
STAT_ASSOC_FAIL = 13
STAT_HANDSHAKE_TIMEOUT = 14

class AbstractNetwork:
    def __init__(self):
        self.config_dict = {}
        self.is_active = False

    def active(self, *args):
        if args:
            self.is_active = args[0]
        else:
            return self.is_active

    def config(self, *args, **kwargs):
        if kwargs:
            self.config_dict.update(kwargs)
        elif len(args) == 1:
            return self.config_dict[args[0]]


# The client access interface
class StaIf(AbstractNetwork):
    def __init__(self):
        AbstractNetwork.__init__(self)
        self.scan_results = []
        self.connected = False
        # Cache the argument to 'successful' connect call (if the network was in scan_results)
        self.DEBUG_CONNECTED_SSID = None
        self.DEBUG_CONNECTED_BSSID = None

    #def connect(self, ssid, key=None, **kwargs):
    def connect(self, ssid, _key=None, *, bssid):
        for network in self.scan_results:
            should_connect = network[0].decode('utf-8') == ssid and \
                (bssid is None or bssid == network[1])
            if should_connect:
                self.connected = True
                self.DEBUG_CONNECTED_SSID = ssid
                self.DEBUG_CONNECTED_BSSID = bssid
                return
        self.connected = False

    def scan(self):
        return self.scan_results

    def isconnected(self):
        return self.connected

    def ifconfig(self):
        if self.connected:
            return ("192.168.1.100", "255.255.255.0", "192.168.1.1", "8.8.8.8")
        return ("0.0.0.0", "0.0.0.0", "0.0.0.0", "0.0.0.0")

    def config(self, *args, **kwargs):
        if len(args) == 1 and args[0] == 'ssid':
            return self.DEBUG_CONNECTED_SSID
        return AbstractNetwork.config(self, *args, **kwargs)

    def status(self):
        # "STAT_IDLE" "STAT_CONNECTING" "STAT_WRONG_PASSWORD" "STAT_NO_AP_FOUND" "STAT_CONNECT_FAIL" "STAT_GOT_IP"
        if self.connected:
            return STAT_GOT_IP
        else:
            return STAT_IDLE


# The adhoc access point master
class ApIf(AbstractNetwork):
    def __init__(self):
        AbstractNetwork.__init__(self)


# Function to imitate the micropython network factory
STA_IF = StaIf
AP_IF = ApIf
interfaces = {STA_IF: STA_IF(), AP_IF: AP_IF()}


def wlan(kind):
    return interfaces[kind]


def debug_reset():
    interfaces[STA_IF] = STA_IF()
    interfaces[AP_IF] = AP_IF()


WLAN = wlan
DEBUG_RESET = debug_reset

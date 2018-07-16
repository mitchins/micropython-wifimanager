# micropython-wifimanager
A simple network configuration utility for MicroPython on the ESP-8266 aboard

Simply upload your JSON file with your networks, the default path is '/networks.json', however the keyword argument `config_file` in setup_network of the WifiManager class can be wherever you like.

The file looks like this:

    {
        "known_networks": [
          {
            "ssid": "HomeNetwork",
            "password": "XYZ12345",
            "enables_webrepl": false
          }
        ],
        "access_point": {
            "essid": "Micropython-Dev",
            "channel": 11,
            "hidden": false,
            "password": "P@55W0rd",
            "enables_webrepl": true,
            "start_policy": "fallback"
        }
    }


Here's an example of how to use the WifiManager.

    MicroPython v1.9.4 on 2018-05-11; ESP32 module with ESP32
    Type "help()" for more information.
    >>> from wifi_manager import WifiManager
    >>> WifiManager.setup_network()
    connecting to network Foo-Network...
    WebREPL daemon started on ws://10.1.1.234:8266
    Started webrepl in normal mode
    True

There exist the following class properties:
* start_ap - When to start the access point, default is fallback when failing to connect to known networks
* start_wr - When to start WebREPL, default is whenever a connection (either Managed or AdHoc) is made


#### More options:
	>>> from wifi_manager import WifiManager, START_AP_ALWAYS
	>>> WifiManager.start_ap = START_AP_ALWAYS
	>>> WifiManager.setup_network()
	connecting to network MitChi...
	Enabling your access point...
	#6 ets_task(4020edc0, 29, 3fff95d8, 10)
	WebREPL daemon started on ws://192.168.4.1:8266
	WebREPL daemon started on ws://10.1.1.234:8266
	Started webrepl in normal mode
	True
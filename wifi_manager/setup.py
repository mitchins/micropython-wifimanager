import sys
# Remove current dir from sys.path, otherwise setuptools will peek up our
# module instead of system's.
sys.path.pop(0)
from setuptools import setup
sys.path.append("..")
import sdist_upip

from distutils.core import setup
setup(
  name = 'micropython-wifimanager',
  cmdclass={'sdist': sdist_upip.sdist},
  py_modules = ['wifi_manager'],
  version = '0.3.6',
  description = 'A simple network configuration utility for MicroPython on the ESP-8266 and ESP-32 boards',
  long_description = "# micropython-wifimanager\r\nA simple network configuration utility for MicroPython on boards such as ESP8266 and ESP32.\r\n\r\n#### Configuration\r\n\r\nSimply upload your JSON file with your networks, the default path is '/networks.json', which is specified in the class property `config_file`.\r\n\r\nA sample configuration may look like this:\r\n\r\n\t{\r\n\t\t\"schema\": 2,\r\n\t\t\"known_networks\": [\r\n\t\t\t{\r\n\t\t\t\t\"ssid\": \"User\\u2019s iPhone\",\r\n\t\t\t\t\"password\": \"Password1\",\r\n\t\t\t\t\"enables_webrepl\": false\r\n\t\t\t},\r\n\t\t\t{\r\n\t\t\t\t\"ssid\": \"HomeNetwork\",\r\n\t\t\t\t\"password\": \"Password2\",\r\n\t\t\t\t\"enables_webrepl\": true\r\n\t\t\t}\r\n\t\t],\r\n\t\t\"access_point\": {\r\n\t\t\t\"config\": {\r\n\t\t\t\t\"essid\": \"Micropython-Dev\",\r\n\t\t\t\t\"channel\": 11,\r\n\t\t\t\t\"hidden\": false,\r\n\t\t\t\t\"password\": \"P@55W0rd\"\r\n\t\t\t},\r\n\t\t\t\"enables_webrepl\": true,\r\n\t\t\t\"start_policy\": \"fallback\"\r\n\t\t}\r\n\t}\r\n\r\n#### Configuration schema\r\n\r\n* **schema**: currently this should be `2`\r\n* **known_networks**: list of networks to connect to, in order of most preferred first\r\n\t* SSID - the name of the access point\r\n\t* password - the clear test password to use\r\n\t* enables_webrepl - a boolean value to indicate if connection to this network desires webrepl being started\r\n* **access_point**: the details for the access point (AP) of this device\r\n\t* config - the keys for the AP config, exactly as per the micropython documentation\r\n\t* enables_weprepl - a boolean value to indicate if ceating this network desires webrepl being started\r\n\t* start_policy - A policy from the below list to indicate when to enable the AP\r\n\t\t* 'always' - regardless of the connection to any base station, AP will be started\r\n\t\t* 'fallback' - the AP will only be started if no network could be connected to\r\n\t\t* 'never' - The AP will not be started under any condition\r\n\r\n#### Simple usage (one shot)\r\n\r\nHere's an example of how to use the WifiManager.\r\n\r\n\tMicroPython v1.9.4 on 2018-05-11; ESP32 module with ESP32\r\n\tType \"help()\" for more information.\r\n\t>>> from wifi_manager import WifiManager\r\n\t>>> WifiManager.setup_network()\r\n\tconnecting to network Foo-Network...\r\n\tWebREPL daemon started on ws://10.1.1.234:8266\r\n\tStarted webrepl in normal mode\r\n\tTrue\r\n\r\n\r\n#### Asynchronous usage (event loop)\r\n\r\nThe WifiManager can be run asynchronously, via the cooperative scheduling that micropthon has in uasyncio. If you call `WifiManager.start_managing()` as follows, it will ensure that periodically the network status is scanned, and connection will be re-established as per preferences as needed.\r\n\r\n\timport uasyncio as asyncio\r\n\tfrom wifi_manager import WifiManager\r\n\r\n\tWifiManager.start_managing()\r\n\tasyncio.get_event_loop().run_forever()\r\n\r\n\r\n#### Contribution\r\n\r\nFound a bug, or want a feature? open an issue.\r\n\r\nIf you want to contribute, create a pull request.\r\n\r\n#### System flow\r\n\r\n![System flow](https://github.com/mitchins/micropython-wifimanager/raw/master/system_flow.png)\r\n",
  long_description_content_type='text/markdown',
  author = 'Mitchell Currie',
  author_email = 'mitch@mitchellcurrie.com',
  url = 'https://github.com/mitchins/micropython-wifimanager',
  download_url = 'https://github.com/mitchins/micropython-wifimanager/archive/0.3.4.tar.gz',
  keywords = ['micropython', 'esp8266', 'esp32', 'wifi', 'manager'],
  classifiers = [],
)

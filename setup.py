import sys
# Remove current dir from sys.path, otherwise setuptools will peek up our
# module instead of system's.
sys.path.pop(0)
from setuptools import setup
sys.path.append("..")
#import optimize_upip

from distutils.core import setup
setup(
  name = 'micropython-wifimanager',
  py_modules = ['wifi_manager'],
  version = '0.2',
  description = 'A simple network configuration utility for MicroPython on the ESP-8266 board',
  author = 'Mitchell Currie',
  author_email = 'mitch@mitchellcurrie.com',
  url = 'https://github.com/mitchins/micropython-wifimanager',
  download_url = 'https://github.com/mitchins/micropython-wifimanager/archive/0.2.tar.gz',
  keywords = ['micropython', 'esp8266', 'wifi', 'manager'],
  classifiers = [],
)

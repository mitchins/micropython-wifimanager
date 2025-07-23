import os
import sys
# Remove current dir from sys.path, otherwise setuptools will peek up our
# module instead of system's.
sys.path.pop(0)
from setuptools import setup
sys.path.append("..")

try:
    import sdist_upip
except ImportError:
    # Fallback for environments without sdist_upip
    sdist_upip = None
setup(
  name = 'micropython-wifimanager',
  cmdclass={'sdist': sdist_upip.sdist} if sdist_upip else {},
  py_modules = ['wifi_manager'],
  version = '1.0.2',
  description = 'A simple network configuration utility for MicroPython on the ESP-8266 and ESP-32 boards',
    long_description = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'README.md')).read(),
  long_description_content_type='text/markdown',
  author = 'Mitchell Currie',
  author_email = 'mitch@mitchellcurrie.com',
  url = 'https://github.com/mitchins/micropython-wifimanager',
  download_url = 'https://github.com/mitchins/micropython-wifimanager/archive/1.0.1.tar.gz',
  keywords = ['micropython', 'esp8266', 'esp32', 'wifi', 'manager'],
  classifiers = [],
)

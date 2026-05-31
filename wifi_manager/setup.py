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

version = '1.0.3'

setup(
  name = 'micropython-wifimanager',
  cmdclass={'sdist': sdist_upip.sdist} if sdist_upip else {},
  py_modules = ['wifi_manager'],
  version = version,
  description = 'A simple network configuration utility for MicroPython on the ESP-8266 and ESP-32 boards',
  long_description = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'README.md'), encoding='utf-8').read(),
  long_description_content_type='text/markdown',
  author = 'Mitchell Currie',
  author_email = 'mitch@mitchellcurrie.com',
  url = 'https://github.com/mitchins/micropython-wifimanager',
  download_url = 'https://github.com/mitchins/micropython-wifimanager/archive/v{0}.tar.gz'.format(version),
  keywords = ['micropython', 'esp8266', 'esp32', 'wifi', 'manager'],
  classifiers = [
     'Development Status :: 5 - Production/Stable',
     'License :: OSI Approved :: BSD License',
     'Programming Language :: Python :: 3',
     'Topic :: Communications',
     'Topic :: System :: Networking',
  ],
)

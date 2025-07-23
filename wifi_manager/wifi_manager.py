"""Implementation of a controller to connect to preferred wifi network(s) [For ESP8266, micro-python]

Config is loaded from a file kept by default in '/networks.json'

Priority of networks is determined implicitly by order in array, first being the highest.
It will go through the list of preferred networks, connecting to the ones it detects present.

Default behaviour is to always start the webrepl after setup,
and only start the access point if we can't connect to a known access point ourselves.

Future scope is to use BSSID instead of SSID when micropython allows it,
this would allow multiple access points with the same name, and we can select by signal strength.


"""
__version__ = "1.0.2"

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

# Robust logger setup
try:
    import logging
    log = logging.getLogger("wifi_manager")
except ImportError:
    # Try ulogging (some ports bundle it as ulogging)
    try:
        import ulogging as logging
        log = logging.getLogger("wifi_manager")
    except (ImportError, AttributeError):
        # Last resort: minimal stub
        class StubLog:
            def __init__(self, name): self.name = name
            def _log(self, level, *args):
                print(f"[{level}] {self.name}:", *args)
            def debug(self, *args):    self._log("DEBUG", *args)
            def info(self, *args):     self._log(" INFO", *args)
            def warning(self, *args):  self._log(" WARN", *args)
            def error(self, *args):    self._log("ERROR", *args)
            def critical(self, *args): self._log("CRIT",  *args)
        log = StubLog("wifi_manager")

class WifiManager:
    webrepl_triggered = False
    _ap_start_policy = "never"
    config_file = '/networks.json'
    _config_server_enabled = False
    _config_server_password = "micropython"
    _connection_callbacks = []
    _last_connection_state = None
    
    # Minimal HTML for config interface
    _config_html = """<!DOCTYPE html>
<html><head><title>WiFi Manager Config</title>
<style>body{font-family:Arial,sans-serif;margin:20px;}textarea{width:100%;}</style>
</head><body>
<h2>WiFi Manager Configuration</h2>
<textarea id="config" rows="25" placeholder="Loading configuration..."></textarea><br><br>
<button onclick="loadConfig()">Reload Config</button>
<button onclick="saveConfig()">Save & Apply</button>
<button onclick="testConfig()">Validate JSON</button><br><br>
<div id="status"></div>

<script>
function setStatus(msg, isError) {
    const status = document.getElementById('status');
    status.innerHTML = msg;
    status.style.color = isError ? 'red' : 'green';
}

function loadConfig() {
    fetch('/config')
        .then(response => response.text())
        .then(data => {
            try {
                const formatted = JSON.stringify(JSON.parse(data), null, 2);
                document.getElementById('config').value = formatted;
                setStatus('Configuration loaded successfully');
            } catch(e) {
                document.getElementById('config').value = data;
                setStatus('Loaded raw config (JSON parse failed)', true);
            }
        })
        .catch(e => setStatus('Failed to load config: ' + e, true));
}

function testConfig() {
    try {
        const config = document.getElementById('config').value;
        const parsed = JSON.parse(config);
        if (!parsed.known_networks || !parsed.access_point) {
            throw new Error('Missing required sections');
        }
        setStatus('JSON is valid!');
    } catch(e) {
        setStatus('JSON Error: ' + e.message, true);
    }
}

function saveConfig() {
    const configText = document.getElementById('config').value;
    try {
        JSON.parse(configText); // Validate first
    } catch(e) {
        setStatus('Cannot save: Invalid JSON - ' + e.message, true);
        return;
    }
    
    fetch('/config', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: configText
    })
    .then(response => response.text())
    .then(data => {
        setStatus('Configuration saved! Device will reconnect with new settings...');
        setTimeout(loadConfig, 3000); // Reload after reconnection
    })
    .catch(e => setStatus('Save failed: ' + e, true));
}

// Load config on page load
loadConfig();
</script>
</body></html>"""

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
            # Check for connection state changes and notify callbacks
            cls._check_and_notify_connection_state()
            
            status = cls.wlan().status()
            # ESP32 does not currently return
            if (status != network.STAT_GOT_IP) or \
            (cls.wlan().ifconfig()[0] == '0.0.0.0'):  # temporary till #3967
                log.info("Network not connected: managing")
                # Ignore connecting status for now.. ESP32 is a bit strange
                # if status != network.STAT_CONNECTING: <- do not care yet
                cls.setup_network()
            await asyncio.sleep(10)  # Pause 10 seconds between checks

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
                
                # Check for config server settings
                if "config_server" in config:
                    server_config = config["config_server"]
                    if server_config.get("enabled", False):
                        password = server_config.get("password", "micropython")
                        cls.start_config_server(password)
                
                if config.get("schema", 0) != 2:
                    log.warning("Did not get expected schema [2] in JSON config.")
        except Exception as e:
            log.error("Failed to load config file: {}. No known networks selected".format(e))
            cls.preferred_networks = []
            cls.ap_config = {"config": {"essid": "MicroPython-AP", "password": "micropython"}, 
                           "enables_webrepl": False, "start_policy": "never"}
            return False

        # set things up
        cls.webrepl_triggered = False  # Until something wants it
        cls.wlan().active(True)

        # scan what's available
        available_networks = []
        try:
            scan_results = cls.wlan().scan()
            for network in scan_results:
                try:
                    ssid = network[0].decode("utf-8")
                    bssid = network[1]
                    strength = network[3]
                    available_networks.append(dict(ssid=ssid, bssid=bssid, strength=strength))
                except (IndexError, UnicodeDecodeError) as e:
                    log.warning("Failed to parse network scan result: {}".format(e))
                    continue
        except OSError as e:
            log.error("Network scan failed: {}".format(e))
            return False
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

        connected = False
        for new_connection in candidates:
            log.info("Attempting to connect to network {0}...".format(new_connection["ssid"]))
            # Micropython 1.9.3+ supports BSSID specification so let's use that
            if cls.connect_to(ssid=new_connection["ssid"], password=new_connection["password"],
                              bssid=new_connection["bssid"]):
                log.info("Successfully connected {0}".format(new_connection["ssid"]))
                cls.webrepl_triggered = new_connection["enables_webrepl"]
                
                # Notify successful connection
                try:
                    ifconfig = cls.wlan().ifconfig()
                    ip = ifconfig[0] if ifconfig else "unknown"
                    cls._notify_connection_change("connected", ssid=new_connection["ssid"], ip=ip)
                except Exception as e:
                    log.warning(f"Failed to notify connection: {e}")
                
                connected = True
                break  # We are connected so don't try more
        
        # If no connection was successful and we have candidates, notify failure
        if not connected and candidates:
            try:
                failed_ssids = [c["ssid"] for c in candidates]
                cls._notify_connection_change("connection_failed", attempted_networks=failed_ssids)
            except Exception as e:
                log.warning(f"Failed to notify connection failure: {e}")


        # Check if we are to start the access point
        cls._ap_start_policy = cls.ap_config.get("start_policy", "never")
        should_start_ap = cls.wants_accesspoint()
        try:
            cls.accesspoint().active(should_start_ap)
            if should_start_ap:  # Only bother setting the config if it WILL be active
                log.info("Enabling your access point...")
                cls.accesspoint().config(**cls.ap_config["config"])
                cls.webrepl_triggered = cls.ap_config["enables_webrepl"]
                
                # Notify AP started
                try:
                    essid = cls.ap_config["config"].get("essid", "unknown")
                    cls._notify_connection_change("ap_started", essid=essid)
                except Exception as e:
                    log.warning(f"Failed to notify AP start: {e}")
                    
            cls.accesspoint().active(cls.wants_accesspoint())  # It may be DEACTIVATED here
        except OSError as e:
            log.error("Failed to configure access point: {}".format(e))

        # may need to reload the config if access points trigger it

        # start the webrepl according to the rules
        if cls.webrepl_triggered:
            try:
                webrepl.start()
            except (NameError, TypeError) as e:
                log.warning(f"Could not start WebREPL: {e}")

        # return the success status, which is ultimately if we connected to managed and not ad hoc wifi.
        return cls.wlan().isconnected()

    @classmethod
    def connect_to(cls, *, ssid, password, **kwargs) -> bool:
        try:
            cls.wlan().connect(ssid, password, **kwargs)
        except OSError as e:
            log.error("Failed to initiate connection to {}: {}".format(ssid, e))
            return False

        for check in range(0, 10):  # Wait a maximum of 10 times (10 * 500ms = 5 seconds) for success
            try:
                if cls.wlan().isconnected():
                    return True
            except OSError as e:
                log.warning("Connection check failed for {}: {}".format(ssid, e))
                break
            time.sleep_ms(500)
        return False

    @classmethod
    def _check_basic_auth(cls, request):
        """Check HTTP Basic Authentication"""
        if not cls._config_server_password:
            return True  # No password required
            
        auth_header = None
        for line in request.split('\r\n'):
            if line.lower().startswith('authorization: basic '):
                auth_header = line.split(' ', 2)[2]
                break
        
        if not auth_header:
            return False
            
        try:
            # Decode base64 credentials
            import ubinascii
            decoded = ubinascii.a2b_base64(auth_header).decode()
            if ':' in decoded:
                username, password = decoded.split(':', 1)
                return username == "admin" and password == cls._config_server_password
        except:
            pass
        return False

    @classmethod
    def _handle_config_request(cls, request: str) -> str:
        """
        Handle HTTP requests for the configuration web server.
        Supports:
          - GET /config       → returns JSON config
          - POST /config      → updates JSON config
          - GET / or /index   → returns HTML editor
        Requires Basic Auth username “admin” and password cls._config_server_password,
        unless password is None or empty (in which case auth is skipped).
        """
        # 1) Authentication
        if cls._config_server_password:
            # look for “Authorization: Basic …”
            auth = None
            for line in request.split('\r\n'):
                if line.lower().startswith("authorization: basic "):
                    auth = line.split(" ", 2)[2]
                    break
            if not auth:
                return (
                    "HTTP/1.1 401 Unauthorized\r\n"
                    "WWW-Authenticate: Basic realm=\"WiFi Config\"\r\n"
                    "Content-Type: text/plain\r\n"
                    "\r\n"
                    "Authentication required"
                )
            # decode and verify
            try:
                import ubinascii
                user_pass = ubinascii.a2b_base64(auth).decode()
                user, pwd = user_pass.split(":", 1)
                if user != "admin" or pwd != cls._config_server_password:
                    raise ValueError
            except Exception:
                return (
                    "HTTP/1.1 401 Unauthorized\r\n"
                    "WWW-Authenticate: Basic realm=\"WiFi Config\"\r\n"
                    "Content-Type: text/plain\r\n"
                    "\r\n"
                    "Invalid credentials"
                )

        # 2) POST /config → update config
        if request.startswith("POST /config"):
            # extract body
            idx = request.find("\r\n\r\n")
            if idx < 0:
                return "HTTP/1.1 400 Bad Request\r\nContent-Type: text/plain\r\n\r\nNo request body"
            body = request[idx+4:]
            # parse JSON
            try:
                import json
                cfg = json.loads(body)
                if "known_networks" not in cfg or "access_point" not in cfg:
                    raise ValueError("Missing required keys")
            except ValueError as ve:
                return (
                    "HTTP/1.1 400 Bad Request\r\n"
                    "Content-Type: text/plain\r\n"
                    f"\r\nInvalid JSON: {ve}"
                )
            except Exception as e:
                return (
                    "HTTP/1.1 400 Bad Request\r\n"
                    "Content-Type: text/plain\r\n"
                    f"\r\nJSON parse error: {e}"
                )
            # write file
            try:
                with open(cls.config_file, "w") as f:
                    f.write(body)
                log.info("Configuration updated via web interface")
                # reconfigure network immediately
                try:
                    cls.setup_network()
                except Exception as e:
                    log.warning(f"Network re-setup failed: {e}")
                return "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\nConfiguration updated successfully"
            except Exception as e:
                return (
                    "HTTP/1.1 500 Internal Server Error\r\n"
                    "Content-Type: text/plain\r\n"
                    f"\r\nFailed to save config: {e}"
                )

        # 3) GET /config → serve JSON
        if request.startswith("GET /config"):
            try:
                with open(cls.config_file, "r") as f:
                    data = f.read()
                return (
                    "HTTP/1.1 200 OK\r\n"
                    "Content-Type: application/json\r\n"
                    "\r\n"
                    f"{data}"
                )
            except Exception as e:
                return (
                    "HTTP/1.1 500 Internal Server Error\r\n"
                    "Content-Type: text/plain\r\n"
                    f"\r\nCould not read config: {e}"
                )

        # 4) GET / or /index → serve HTML editor
        if request.startswith("GET / ") or "GET /index" in request:
            return (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: text/html\r\n"
                "\r\n"
                f"{cls._config_html}"
            )

        # 5) anything else → 404
        return (
            "HTTP/1.1 404 Not Found\r\n"
            "Content-Type: text/plain\r\n"
            "\r\n"
            "Not found"
        )

    @classmethod
    async def _run_config_server(cls):
        """Run the configuration web server"""
        try:
            import socket
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind(('0.0.0.0', 8080))
            server_socket.listen(1)
            server_socket.settimeout(1.0)  # Non-blocking with timeout
            
            log.info("Config server started on port 8080")
            
            while cls._config_server_enabled:
                try:
                    conn, addr = server_socket.accept()
                    log.debug(f"Config server connection from {addr}")
                    
                    # Read request with timeout
                    conn.settimeout(5.0)
                    request = conn.recv(4096).decode()
                    
                    # Handle request
                    response = cls._handle_config_request(request)
                    
                    # Send response
                    conn.send(response.encode())
                    conn.close()
                    
                except OSError:
                    # Timeout or no connection - yield control
                    await asyncio.sleep_ms(100)
                except Exception as e:
                    log.warning(f"Config server request error: {e}")
                    
            server_socket.close()
            log.info("Config server stopped")
            
        except Exception as e:
            log.error(f"Config server failed to start: {e}")

    @classmethod
    def start_config_server(cls, password="micropython"):
        """Start the configuration web server"""
        if not asyncio:
            log.error("Config server requires asyncio")
            return False
            
        cls._config_server_password = password
        cls._config_server_enabled = True
        
        # Start server as async task
        loop = asyncio.get_event_loop()
        loop.create_task(cls._run_config_server())
        
        log.info("Config server starting on http://[device-ip]:8080")
        return True

    @classmethod
    def stop_config_server(cls):
        """Stop the configuration web server"""
        cls._config_server_enabled = False

    @classmethod
    def on_connection_change(cls, callback):
        """Register a callback function for connection state changes
        
        Callback will be called with (event, **kwargs) where event is one of:
        - 'connected': Successfully connected to a network
        - 'disconnected': Lost connection to network  
        - 'ap_started': Access point was activated
        - 'connection_failed': All connection attempts failed
        
        Example:
            def my_callback(event, **kwargs):
                if event == 'connected':
                    print(f"Connected to {kwargs.get('ssid')} with IP {kwargs.get('ip')}")
                elif event == 'disconnected':
                    print("Lost connection")
            
            WifiManager.on_connection_change(my_callback)
        """
        if callback not in cls._connection_callbacks:
            cls._connection_callbacks.append(callback)
            log.debug(f"Registered connection callback: {callback}")

    @classmethod 
    def remove_connection_callback(cls, callback):
        """Remove a previously registered connection callback"""
        if callback in cls._connection_callbacks:
            cls._connection_callbacks.remove(callback)
            log.debug(f"Removed connection callback: {callback}")

    @classmethod
    def _notify_connection_change(cls, event, **kwargs):
        """Notify all registered callbacks of a connection state change"""
        log.debug(f"Connection event: {event} with args: {kwargs}")
        
        for callback in cls._connection_callbacks:
            try:
                callback(event, **kwargs)
            except Exception as e:
                log.warning(f"Connection callback error: {e}")
        
        # Update last known state for state change detection
        cls._last_connection_state = event

    @classmethod
    def _check_and_notify_connection_state(cls):
        """Check current connection state and notify if changed"""
        try:
            is_connected = cls.wlan().isconnected()
            current_state = "connected" if is_connected else "disconnected"
            
            # Only notify on state changes
            if cls._last_connection_state != current_state:
                if is_connected:
                    # Get connection details
                    ifconfig = cls.wlan().ifconfig()
                    ip = ifconfig[0] if ifconfig else "unknown"
                    # Try to get connected SSID (not all MicroPython versions support this)
                    ssid = "unknown"
                    try:
                        config = cls.wlan().config('ssid')
                        if config:
                            ssid = config
                    except:
                        pass
                    
                    cls._notify_connection_change("connected", ssid=ssid, ip=ip)
                else:
                    cls._notify_connection_change("disconnected")
                    
        except Exception as e:
            log.warning(f"Connection state check failed: {e}")

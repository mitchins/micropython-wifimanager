"""Implementation of a controller to connect to preferred wifi network(s) [For ESP8266, micro-python]

Config is loaded from a file kept by default in '/networks.json'

Priority of networks is determined implicitly by order in array, first being the highest.
It will go through the list of preferred networks, connecting to the ones it detects present.

Default behaviour is to always start the webrepl after setup,
and only start the access point if we can't connect to a known access point ourselves.

Future scope is to use BSSID instead of SSID when micropython allows it,
this would allow multiple access points with the same name, and we can select by signal strength.


"""
__version__ = "1.0.3"

import json
import time

# Micropython modules
import network
try:
    import webrepl
except ImportError:
    webrepl = None
try:
    import uasyncio as asyncio
except ImportError:
    try:
        import asyncio
    except ImportError:
        asyncio = None

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
                print("[%s] %s:" % (level, self.name), *args)
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
    _config_server_task = None
    _connection_callbacks = []
    _last_connection_state = None
    _masked_password = "***"
    _max_request_bytes = 16384
    
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
        if asyncio is None:
            log.error("Managing requires asyncio")
            return False

        loop = cls._get_event_loop()
        loop.create_task(cls.manage()) # Schedule ASAP
        # Make sure you loop.run_forever() (we are a guest here)
        return True

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
    def _get_event_loop(cls):
        try:
            return asyncio.get_event_loop()
        except (AttributeError, RuntimeError):
            if hasattr(asyncio, "new_event_loop") and hasattr(asyncio, "set_event_loop"):
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                return loop
            raise

    @staticmethod
    def _sleep_ms(duration_ms):
        sleep_ms = getattr(time, "sleep_ms", None)
        if sleep_ms is not None:
            sleep_ms(duration_ms)
            return
        time.sleep(duration_ms / 1000.0)

    @staticmethod
    async def _sleep_async_ms(duration_ms):
        if hasattr(asyncio, "sleep_ms"):
            await asyncio.sleep_ms(duration_ms)
            return
        await asyncio.sleep(duration_ms / 1000.0)

    @classmethod
    def _normalise_access_point_config(cls, ap_config):
        if not isinstance(ap_config, dict):
            raise ValueError("access_point must be a JSON object")
        ap_config = dict(ap_config or {})
        if "config" in ap_config:
            if not isinstance(ap_config.get("config") or {}, dict):
                raise ValueError("access_point.config must be a JSON object")
            ap_config["config"] = dict(ap_config.get("config") or {})
            return ap_config

        raw_config = {}
        for key in ("essid", "channel", "hidden", "authmode", "password", "max_clients"):
            if key in ap_config:
                raw_config[key] = ap_config.pop(key)
        ap_config["config"] = raw_config
        return ap_config

    @classmethod
    def _setup_recovery_ap(cls):
        cls.preferred_networks = []
        cls.ap_config = {
            "config": {"essid": "MicroPython-AP", "password": "micropython"},
            "enables_webrepl": True,
            "start_policy": "always"
        }
        cls.start_config_server(cls._config_server_password)

    @classmethod
    def _mask_passwords(cls, value):
        if isinstance(value, dict):
            masked = {}
            for key, item in value.items():
                if key == "password" and item:
                    masked[key] = cls._masked_password
                else:
                    masked[key] = cls._mask_passwords(item)
            return masked
        if isinstance(value, list):
            return [cls._mask_passwords(item) for item in value]
        return value

    @classmethod
    def _merge_masked_networks(cls, candidate_networks, existing_networks):
        existing_networks = existing_networks if isinstance(existing_networks, list) else []
        existing_by_ssid = {}
        for network in existing_networks:
            if not isinstance(network, dict):
                continue
            ssid = network.get("ssid")
            if ssid is None or ssid in existing_by_ssid:
                continue
            existing_by_ssid[ssid] = network

        merged = []
        for network in candidate_networks:
            existing_network = None
            if isinstance(network, dict):
                existing_network = existing_by_ssid.get(network.get("ssid"))
            merged.append(cls._merge_masked_config(network, existing_network))
        return merged

    @classmethod
    def _merge_masked_config(cls, candidate, existing):
        if isinstance(candidate, dict):
            existing = existing if isinstance(existing, dict) else {}
            merged = {}
            for key, value in candidate.items():
                if key == "known_networks" and isinstance(value, list):
                    merged[key] = cls._merge_masked_networks(value, existing.get(key))
                    continue
                if key == "password" and value == cls._masked_password:
                    merged[key] = existing.get(key, "")
                else:
                    merged[key] = cls._merge_masked_config(value, existing.get(key))
            return merged
        if isinstance(candidate, list):
            existing = existing if isinstance(existing, list) else []
            merged = []
            for index, value in enumerate(candidate):
                existing_value = existing[index] if index < len(existing) else None
                merged.append(cls._merge_masked_config(value, existing_value))
            return merged
        return candidate

    @classmethod
    def _read_http_request(cls, conn):
        content_length = 0
        data = b""
        header_end = -1

        while True:
            chunk = conn.recv(512)
            if not chunk:
                break
            data += chunk
            if len(data) > cls._max_request_bytes:
                raise ValueError("Request too large")

            if header_end < 0:
                header_end = data.find(b"\r\n\r\n")
                if header_end >= 0:
                    headers = data[:header_end].decode()
                    for line in headers.split("\r\n"):
                        if line.lower().startswith("content-length:"):
                            try:
                                content_length = int(line.split(":", 1)[1].strip())
                            except ValueError:
                                content_length = 0
                            break
                    if content_length > cls._max_request_bytes:
                        raise ValueError("Request too large")

            if header_end >= 0:
                body_length = len(data) - (header_end + 4)
                if body_length >= content_length:
                    break

        return data.decode()

    @staticmethod
    def _send_http_response(conn, response):
        data = response.encode()
        while data:
            sent = conn.send(data)
            data = data[sent:]

    @staticmethod
    def _build_http_response(status, body, content_type="text/plain", extra_headers=None):
        headers = ["HTTP/1.1 %s" % status]
        for header in extra_headers or []:
            headers.append(header)
        headers.append("Content-Type: %s" % content_type)
        headers.append("")
        headers.append(body)
        return "\r\n".join(headers)

    @classmethod
    def _normalise_loaded_config(cls, config):
        if not isinstance(config, dict):
            raise ValueError("Configuration must be a JSON object")
        if "known_networks" not in config or "access_point" not in config:
            raise ValueError("Missing required configuration keys")

        preferred_networks = config.get("known_networks")
        if not isinstance(preferred_networks, list):
            raise ValueError("known_networks must be a list")

        server_config = config.get("config_server") or {}
        if not isinstance(server_config, dict):
            raise ValueError("config_server must be a JSON object")

        return (
            preferred_networks,
            cls._normalise_access_point_config(config.get("access_point")),
            server_config,
            config.get("schema", 0),
        )

    @classmethod
    def _load_config(cls):
        try:
            with open(cls.config_file, "r") as config_file:
                config = json.load(config_file)
            preferred_networks, ap_config, server_config, schema = cls._normalise_loaded_config(
                config
            )
        except (OSError, TypeError, ValueError) as error:
            log.error("Failed to load config file: {}. Falling back to recovery AP.".format(error))
            cls._setup_recovery_ap()
            return False

        cls.preferred_networks = preferred_networks
        cls.ap_config = ap_config

        if server_config.get("enabled", False):
            password = server_config.get("password", cls._config_server_password)
            cls.start_config_server(password)
        else:
            cls.stop_config_server()

        if schema != 2:
            log.warning("Did not get expected schema [2] in JSON config.")
        return True

    @classmethod
    def _scan_available_networks(cls):
        try:
            scan_results = cls.wlan().scan()
        except OSError as error:
            log.error("Network scan failed: {}".format(error))
            return None

        try:
            scan_results = list(scan_results)
        except TypeError as error:
            log.error("Network scan returned invalid data: {}".format(error))
            return []

        available_networks = []
        for scan_result in scan_results:
            try:
                ssid = scan_result[0].decode("utf-8")
                bssid = scan_result[1]
                strength = scan_result[3]
            except (AttributeError, IndexError, TypeError, UnicodeDecodeError) as error:
                log.warning("Failed to parse network scan result: {}".format(error))
                continue
            available_networks.append({
                "ssid": ssid,
                "bssid": bssid,
                "strength": strength,
            })

        available_networks.sort(key=lambda station: station["strength"], reverse=True)
        return available_networks

    @classmethod
    def _build_connection_candidates(cls, available_networks):
        candidates = []
        for preference in cls.preferred_networks:
            if not isinstance(preference, dict):
                continue
            preferred_ssid = preference.get("ssid")
            if preferred_ssid is None:
                continue
            for network_info in available_networks:
                if preferred_ssid != network_info["ssid"]:
                    continue
                candidates.append({
                    "ssid": network_info["ssid"],
                    "bssid": network_info["bssid"],
                    "password": preference.get("password", ""),
                    "enables_webrepl": preference.get("enables_webrepl", False),
                })
        return candidates

    @classmethod
    def _notify_connection_success(cls, connection_data):
        try:
            ifconfig = cls.wlan().ifconfig()
            ip = ifconfig[0] if ifconfig else "unknown"
            cls._notify_connection_change("connected", ssid=connection_data["ssid"], ip=ip)
        except (AttributeError, IndexError, OSError, TypeError) as error:
            log.warning(f"Failed to notify connection: {error}")

    @classmethod
    def _connect_candidates(cls, candidates):
        for connection_data in candidates:
            log.info("Attempting to connect to network {0}...".format(connection_data["ssid"]))
            if not cls.connect_to(
                ssid=connection_data["ssid"],
                password=connection_data["password"],
                bssid=connection_data["bssid"],
            ):
                continue
            log.info("Successfully connected {0}".format(connection_data["ssid"]))
            cls.webrepl_triggered = connection_data["enables_webrepl"]
            cls._notify_connection_success(connection_data)
            return True
        return False

    @classmethod
    def _notify_connection_failure(cls, candidates):
        try:
            failed_ssids = [candidate["ssid"] for candidate in candidates]
            if not failed_ssids:
                failed_ssids = [
                    item.get("ssid")
                    for item in cls.preferred_networks
                    if isinstance(item, dict) and item.get("ssid")
                ]
            cls._notify_connection_change("connection_failed", attempted_networks=failed_ssids)
        except (AttributeError, TypeError, ValueError) as error:
            log.warning(f"Failed to notify connection failure: {error}")

    @classmethod
    def _notify_access_point_started(cls, ap_settings):
        try:
            essid = ap_settings.get("essid", "unknown")
            cls._notify_connection_change("ap_started", essid=essid)
        except (AttributeError, TypeError, ValueError) as error:
            log.warning(f"Failed to notify AP start: {error}")

    @classmethod
    def _configure_access_point(cls):
        cls._ap_start_policy = cls.ap_config.get("start_policy", "never")
        should_start_ap = cls.wants_accesspoint()

        try:
            access_point = cls.accesspoint()
            access_point.active(should_start_ap)
            if should_start_ap:
                log.info("Enabling your access point...")
                ap_settings = cls.ap_config.get("config", {})
                if ap_settings:
                    access_point.config(**ap_settings)
                cls.webrepl_triggered = cls.ap_config.get("enables_webrepl", False)
                cls._notify_access_point_started(ap_settings)
            access_point.active(should_start_ap)
        except (AttributeError, KeyError, OSError, TypeError, ValueError) as error:
            log.error("Failed to configure access point: {}".format(error))

    @classmethod
    def _start_webrepl_if_requested(cls):
        if not cls.webrepl_triggered:
            return
        if webrepl is None:
            log.warning("Could not start WebREPL: module unavailable")
            return
        try:
            webrepl.start()
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as error:
            log.warning(f"Could not start WebREPL: {error}")

    @staticmethod
    def _extract_request_body(request):
        body_separator = "\r\n\r\n"
        body_index = request.find(body_separator)
        if body_index < 0:
            return None
        return request[body_index + len(body_separator):]

    @classmethod
    def _load_existing_config(cls):
        try:
            with open(cls.config_file, "r") as config_file:
                return json.load(config_file)
        except (OSError, TypeError, ValueError):
            return {}

    @staticmethod
    def _validate_config_payload(config):
        if "known_networks" not in config or "access_point" not in config:
            raise ValueError("Missing required keys")

    @classmethod
    def _handle_config_post_request(cls, request):
        body = cls._extract_request_body(request)
        if body is None:
            return cls._build_http_response("400 Bad Request", "No request body")

        try:
            config = json.loads(body)
            cls._validate_config_payload(config)
        except (TypeError, ValueError) as error:
            return cls._build_http_response("400 Bad Request", "Invalid JSON: {}".format(error))

        try:
            existing_config = cls._load_existing_config()
            config_to_save = cls._merge_masked_config(config, existing_config)
            with open(cls.config_file, "w") as config_file:
                config_file.write(json.dumps(config_to_save))
        except (OSError, TypeError, ValueError) as error:
            return cls._build_http_response(
                "500 Internal Server Error",
                "Failed to save config: {}".format(error),
            )

        log.info("Configuration updated via web interface")
        cls.setup_network()
        return cls._build_http_response("200 OK", "Configuration updated successfully")

    @classmethod
    def _handle_config_get_request(cls):
        try:
            with open(cls.config_file, "r") as config_file:
                data = json.dumps(cls._mask_passwords(json.load(config_file)))
        except (OSError, TypeError, ValueError) as error:
            return cls._build_http_response(
                "500 Internal Server Error",
                "Could not read config: {}".format(error),
            )

        return cls._build_http_response("200 OK", data, content_type="application/json")

    @classmethod
    def setup_network(cls) -> bool:
        cls._load_config()
        # set things up
        cls.webrepl_triggered = False  # Until something wants it
        cls.wlan().active(True)

        available_networks = cls._scan_available_networks()
        if available_networks is None:
            return False

        candidates = cls._build_connection_candidates(available_networks)
        connected = cls._connect_candidates(candidates)
        if not connected:
            cls._notify_connection_failure(candidates)

        cls._configure_access_point()
        cls._start_webrepl_if_requested()

        # return the success status, which is ultimately if we connected to managed and not ad hoc wifi.
        return cls.wlan().isconnected()

    @classmethod
    def connect_to(cls, *, ssid, password, **kwargs) -> bool:
        try:
            cls.wlan().connect(ssid, password, **kwargs)
        except OSError as e:
            log.error("Failed to initiate connection to {}: {}".format(ssid, e))
            return False

        for _ in range(0, 10):  # Wait a maximum of 10 times (10 * 500ms = 5 seconds) for success
            try:
                if cls.wlan().isconnected():
                    return True
            except OSError as e:
                log.warning("Connection check failed for {}: {}".format(ssid, e))
                break
            cls._sleep_ms(500)
        return False

    @classmethod
    def _check_basic_auth(cls, request):
        """Check HTTP Basic Authentication"""
        if not cls._config_server_password:
            return True  # No password required
            
        auth_header = None
        for line in request.split('\r\n'):
            if line.lower().startswith('authorization: basic '):
                auth_header = line.split(' ', 2)[2].strip()
                break
        
        if not auth_header:
            return False
            
        try:
            try:
                import ubinascii as binascii
            except ImportError:
                import binascii
            decode_error = getattr(binascii, "Error", ValueError)
            decoded = binascii.a2b_base64(auth_header).decode()
        except (TypeError, UnicodeError, ValueError, decode_error):
            return False

        if ':' not in decoded:
            return False
        username, password = decoded.split(':', 1)
        return username == "admin" and password == cls._config_server_password

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
        if not cls._check_basic_auth(request):
            return cls._build_http_response(
                "401 Unauthorized",
                "Authentication required",
                extra_headers=['WWW-Authenticate: Basic realm="WiFi Config"'],
            )

        # 2) POST /config → update config
        if request.startswith("POST /config"):
            return cls._handle_config_post_request(request)

        # 3) GET /config → serve JSON
        if request.startswith("GET /config"):
            return cls._handle_config_get_request()

        # 4) GET / or /index → serve HTML editor
        if request.startswith("GET / ") or "GET /index" in request:
            return cls._build_http_response("200 OK", cls._config_html, content_type="text/html")

        # 5) anything else → 404
        return cls._build_http_response("404 Not Found", "Not found")

    @classmethod
    async def _run_config_server(cls):
        """Run the configuration web server"""
        server_socket = None
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
                except OSError:
                    # Timeout or no connection - yield control
                    await cls._sleep_async_ms(100)
                    continue

                try:
                    log.debug(f"Config server connection from {addr}")

                    # Read request with timeout
                    conn.settimeout(5.0)
                    request = cls._read_http_request(conn)

                    # Handle request
                    response = cls._handle_config_request(request)

                    # Send response
                    cls._send_http_response(conn, response)
                except Exception as e:
                    log.warning(f"Config server request error: {e}")
                finally:
                    try:
                        conn.close()
                    except OSError:
                        pass

            log.info("Config server stopped")
            
        except OSError as e:
            log.error(f"Config server failed to start: {e}")
            cls._config_server_enabled = False
        finally:
            if server_socket is not None:
                try:
                    server_socket.close()
                except OSError:
                    pass
            cls._config_server_task = None

    @classmethod
    def start_config_server(cls, password="micropython"):
        """Start the configuration web server"""
        if asyncio is None:
            log.error("Config server requires asyncio")
            return False
            
        cls._config_server_password = password
        if cls._config_server_enabled and cls._config_server_task is not None:
            return True
        
        # Start server as async task
        cls._config_server_enabled = True
        loop = cls._get_event_loop()
        cls._config_server_task = loop.create_task(cls._run_config_server())
        
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
        if event in ("connected", "disconnected"):
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
                    except (AttributeError, KeyError, OSError, TypeError, ValueError) as error:
                        log.debug(f"Failed to read connected SSID: {error}")
                    
                    cls._notify_connection_change("connected", ssid=ssid, ip=ip)
                else:
                    cls._notify_connection_change("disconnected")
                    
        except Exception as e:
            log.warning(f"Connection state check failed: {e}")

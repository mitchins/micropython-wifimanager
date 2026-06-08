"""Passive AP-mode honeypot for micropython-wifimanager.

Hooks into WifiManager connection callbacks and only runs a lightweight HTTP
listener when the access point is active.
"""

try:
    import uasyncio as asyncio
except ImportError:
    import asyncio

try:
    import usocket as socket
except ImportError:
    import socket

try:
    import utime as time
except ImportError:
    import time


class HoneypotAP:
    """Low-impact defensive trap AP that only logs passive traffic."""

    _enabled = False
    _running = False
    _installed = False
    _stop_on_connected = True
    _task = None
    _server = None
    _wifi_manager = None

    log_file = "/honeypot.log"
    port = 80
    banner_name = "MicroPython Device"
    max_request_bytes = 1024

    @classmethod
    def install(
        cls,
        wifi_manager,
        *,
        log_file="/honeypot.log",
        port=80,
        banner_name="MicroPython Device",
        stop_on_connected=True,
    ):
        """Register and enable the honeypot."""
        cls._wifi_manager = wifi_manager
        cls.log_file = log_file
        cls.port = port
        cls.banner_name = banner_name
        cls._stop_on_connected = stop_on_connected
        cls._enabled = True

        if not cls._installed:
            wifi_manager.on_connection_change(cls._on_wifi_event)
            cls._installed = True

        return cls

    @classmethod
    def _on_wifi_event(cls, event, **kwargs):
        if event == "ap_started":
            cls.start()
        elif event == "connected" and cls._stop_on_connected:
            cls.stop()

    @classmethod
    def start(cls):
        if cls._running or not cls._enabled:
            return

        if asyncio is None:
            cls._log("honeypot_unavailable", "-", "-", "asyncio missing")
            return

        cls._running = True
        loop = asyncio.get_event_loop()
        cls._task = loop.create_task(cls._run_server())
        cls._log("honeypot_started", "-", "-", "server scheduled")

    @classmethod
    def stop(cls):
        if not cls._running:
            return

        cls._running = False
        server = cls._server
        task = cls._task

        if task is not None:
            try:
                task.cancel()
            except Exception:
                pass
            cls._task = None

        if server is not None:
            try:
                server.close()
            except Exception:
                pass
            cls._server = None

        cls._log("honeypot_stopped", "-", "-", "stopped")

    @classmethod
    async def _run_server(cls):
        server = None
        cls._server = None

        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(("0.0.0.0", cls.port))
            server.listen(1)
            server.settimeout(1)
            cls._server = server

            while cls._running:
                try:
                    conn, addr = server.accept()
                    conn.settimeout(3)
                    raw = conn.recv(cls.max_request_bytes)
                    request = raw.decode("utf-8", "ignore") if raw else ""

                    method, path, ua = cls._parse_request(request)
                    peer = addr[0] if addr else "unknown"
                    cls._log(peer, method, path, ua)

                    cls._send(conn, cls._response(path))
                    conn.close()
                except OSError:
                    await cls._sleep_ms(100)
                except Exception as exc:
                    cls._log("server_error", "-", "-", repr(exc))
                    await cls._sleep_ms(250)

        except asyncio.CancelledError:
            pass
        finally:
            if server:
                try:
                    server.close()
                except Exception:
                    pass

            cls._server = None
            cls._running = False
            cls._task = None

    @staticmethod
    def _sleep_ms(duration_ms):
        sleep_ms = getattr(time, "sleep_ms", None)
        if sleep_ms is not None:
            sleep_ms(duration_ms)
        else:
            time.sleep(duration_ms / 1000.0)

    @classmethod
    def _parse_request(cls, request):
        method = "-"
        path = "-"
        user_agent = "-"

        lines = request.split("\r\n")
        if lines:
            parts = lines[0].split(" ")
            if len(parts) >= 2:
                method = parts[0]
                path = parts[1]

        for line in lines:
            if line.lower().startswith("user-agent:"):
                user_agent = line.split(":", 1)[1].strip()
                break

        return method, path, user_agent

    @classmethod
    def _response(cls, path):
        body = """<!doctype html>
<html>
<head>
  <title>{name}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta charset="utf-8">
</head>
<body>
  <h1>{name}</h1>
  <p>Device configuration service is temporarily unavailable.</p>
</body>
</html>
""".format(name=cls.banner_name)

        return (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/html\r\n"
            "Cache-Control: no-store\r\n"
            "Connection: close\r\n"
            "Content-Length: {}\r\n"
            "\r\n"
            "{}"
        ).format(len(body), body).encode()

    @classmethod
    def _send(cls, conn, data):
        if data is None:
            return
        view = memoryview(data)
        while view:
            try:
                sent = conn.send(view)
            except TypeError:
                # Some MicroPython ports need raw bytes and return int sent.
                sent = conn.send(data)
                data = b""
                continue
            if sent <= 0:
                break
            data = data[sent:]
            view = memoryview(data)

    @classmethod
    def _log(cls, peer, method, path, user_agent="-"):
        try:
            ts = time.time()
        except Exception:
            ts = 0

        line = "{}\t{}\t{}\t{}\t{}\n".format(
            ts,
            peer,
            method,
            path,
            user_agent,
        )

        try:
            with open(cls.log_file, "a") as handle:
                handle.write(line)
        except Exception:
            # Avoid crashing WifiManager callbacks if logging is not available.
            pass

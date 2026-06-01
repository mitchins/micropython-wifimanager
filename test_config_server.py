"""
Test script for the WiFi Manager config server
Can be run on a regular Python installation to test the web interface
"""

import json
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse

# Mock the wifi_manager for testing
class MockWifiManager:
    config_file = './test_networks.json'
    _config_server_password = "micropython"
    
    # Create a test config file
    test_config = {
        "schema": 2,
        "known_networks": [
            {
                "ssid": "TestNetwork",
                "password": "testpass123",
                "enables_webrepl": False
            }
        ],
        "access_point": {
            "config": {
                "essid": "MicroPython-Test",
                "channel": 11,
                "hidden": False,
                "password": "testap123"
            },
            "enables_webrepl": True,
            "start_policy": "fallback"
        },
        "config_server": {
            "enabled": True,
            "password": "testpass"
        }
    }
    
    @classmethod
    def setup_test_config(cls):
        with open(cls.config_file, 'w') as f:
            json.dump(cls.test_config, f, indent=2)
    
    @classmethod
    def _check_basic_auth(cls, headers):
        """Check HTTP Basic Authentication"""
        if not cls._config_server_password:
            return True
            
        auth_header = headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Basic '):
            return False
            
        try:
            import base64
            encoded = auth_header.split(' ', 1)[1]
            decoded = base64.b64decode(encoded).decode()
            if ':' in decoded:
                username, password = decoded.split(':', 1)
                return username == "admin" and password == cls._config_server_password
        except:
            pass
        return False

# Test HTTP server
class ConfigServerHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not MockWifiManager._check_basic_auth(self.headers):
            self.send_response(401)
            self.send_header('WWW-Authenticate', 'Basic realm="WiFi Config"')
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Authentication required')
            return
            
        if self.path == '/' or self.path == '/index':
            # Serve the HTML interface (simplified for testing)
            html = """<!DOCTYPE html>
<html><head><title>WiFi Manager Config Test</title></head>
<body>
<h2>WiFi Manager Configuration (Test Mode)</h2>
<textarea id="config" rows="25" style="width:100%"></textarea><br><br>
<button onclick="loadConfig()">Load Config</button>
<button onclick="saveConfig()">Save Config</button>
<div id="status"></div>

<script>
function loadConfig() {
    fetch('/config')
        .then(r => r.text())
        .then(data => {
            document.getElementById('config').value = JSON.stringify(JSON.parse(data), null, 2);
            document.getElementById('status').innerHTML = 'Loaded!';
        });
}
function saveConfig() {
    fetch('/config', {method:'POST', body:document.getElementById('config').value})
        .then(() => document.getElementById('status').innerHTML = 'Saved!');
}
loadConfig();
</script>
</body></html>"""
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(html.encode())
            
        elif self.path == '/config':
            try:
                with open(MockWifiManager.config_file, 'r') as f:
                    config_data = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(config_data.encode())
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(f'Error: {e}'.encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        if not MockWifiManager._check_basic_auth(self.headers):
            self.send_response(401)
            self.send_header('WWW-Authenticate', 'Basic realm="WiFi Config"')
            self.end_headers()
            return
            
        if self.path == '/config':
            try:
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length).decode()
                
                # Validate JSON
                config = json.loads(post_data)
                
                # Save config
                with open(MockWifiManager.config_file, 'w') as f:
                    f.write(post_data)
                
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(b'Configuration updated')
                print("Config updated successfully!")
                
            except Exception as e:
                self.send_response(400)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(f'Error: {e}'.encode())

if __name__ == '__main__':
    print("Setting up test config server...")
    MockWifiManager.setup_test_config()
    MockWifiManager._config_server_password = "testpass"
    
    server = HTTPServer(('localhost', 8080), ConfigServerHandler)
    print("Test config server running at: http://localhost:8080")
    print("Username: admin")
    print("Password: testpass")
    print("Press Ctrl+C to stop")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.server_close()
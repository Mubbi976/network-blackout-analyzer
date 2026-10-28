"""
Network Blackout Analyzer - Modern Web Dashboard Server
Runs a lightweight local web server to serve the interactive NOC dashboard.

Usage:
  python server.py
"""

import http.server
import socketserver
import webbrowser
import os
import sys

PORT = 8080
DIRECTORY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

def main():
    print(f"\n=======================================================")
    print(f" NETWORK BLACKOUT ANALYZER - MODERN WEB NOC DASHBOARD ")
    print(f"=======================================================")
    print(f"[*] Serving modern UI from: {DIRECTORY}")
    print(f"[*] Local URL: http://localhost:{PORT}")
    print(f"[*] Press Ctrl+C in this terminal to stop the server.\n")
    
    webbrowser.open(f"http://localhost:{PORT}")
    
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[!] Server stopped.")

if __name__ == "__main__":
    main()

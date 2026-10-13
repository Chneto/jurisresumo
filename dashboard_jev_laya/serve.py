"""Lightweight local HTTP server for the JEV / LAYA Strategic Dashboard.

Desenvolvido por FChNeto.
"""

import functools
import http.server
import os
from pathlib import Path
import socket
import socketserver
import sys

BASE_DIR = Path(__file__).resolve().parent


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Checks whether the given TCP port is currently occupied."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0


def find_available_port(start_port: int = 8500, max_attempts: int = 50) -> int:
    """Finds the first available port starting from start_port."""
    for port in range(start_port, start_port + max_attempts):
        if not is_port_in_use(port):
            return port
    return start_port


def main():
    host = "127.0.0.1"
    port = find_available_port(8500)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(BASE_DIR))

    class ReusableTCPServer(socketserver.TCPServer):
        allow_reuse_address = True

    with ReusableTCPServer((host, port), handler) as httpd:
        url = f"http://{host}:{port}/index.html"
        print(f"\n=======================================================")
        print(f" JURISRESUMO — DASHBOARD ESTRATÉGICO JEV / LAYA ONLINE")
        print(f" Servidor ativo em: {url}")
        print(f"=======================================================\n")
        sys.stdout.flush()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServidor encerrado pelo usuário.")


if __name__ == "__main__":
    main()

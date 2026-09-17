"""Launcher - JURISRESUMO (Eel Native Desktop App & FastAPI Server).

Desenvolvido por FChNeto.
"""

__author__ = "FChNeto"
DEVELOPED_BY = "FChNeto"

import argparse
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if not str(BASE_DIR) in sys.path:
    sys.path.insert(0, str(BASE_DIR))


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Checks whether the given TCP port is currently occupied."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0


def find_available_port(start_port: int = 8000, max_attempts: int = 20) -> int:
    """Finds the first available port starting from start_port."""
    for port in range(start_port, start_port + max_attempts):
        if not is_port_in_use(port):
            return port
    return start_port


def open_browser(url: str, delay: float = 1.2):
    """Opens browser after server has started."""
    time.sleep(delay)
    print(f"\n[INFO] Abrindo navegador em: {url}")
    webbrowser.open(url)


def run_server(args):
    """Runs FastAPI backend with Uvicorn."""
    import uvicorn

    port = args.port
    if is_port_in_use(port, args.host):
        alt_port = find_available_port(port + 1)
        print(f"[AVISO] Porta {port} em uso. Utilizando porta alternativa: {alt_port}")
        port = alt_port

    url = f"http://{args.host}:{port}"

    print("=" * 75)
    print("  JURISRESUMO - Confecção Automatizada de Resumos de Audiência (PJe)")
    print("  Servidor FastAPI / Google Stitch & Nano Banana")
    print("=" * 75)
    print(f"  Servidor local: {url}")
    print("  Pressione Ctrl+C para encerrar.")
    print("=" * 75)

    if not args.no_browser:
        threading.Thread(target=open_browser, args=(url,), daemon=True).start()

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=port,
        reload=args.reload,
        log_level="info",
    )


def main():
    parser = argparse.ArgumentParser(description="JURISRESUMO - Launcher")
    parser.add_argument("--server", action="store_true", help="Start FastAPI/Uvicorn server instead of Eel desktop app")
    parser.add_argument("--host", default="127.0.0.1", help="Host address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port (default: 8000)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open browser automatically")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")

    args = parser.parse_args()

    if args.server:
        run_server(args)
    else:
        try:
            from run_eel import launch
            launch()
        except Exception as exc:
            print(f"[AVISO] Falha ao iniciar modo Eel desktop ({exc}). Alternando para servidor local...")
            run_server(args)


if __name__ == "__main__":
    main()

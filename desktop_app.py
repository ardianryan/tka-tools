import sys
import os
import time
import socket
import threading
import urllib.request
import logging

# Ensure pyinstaller splash screen closes if present
try:
    import pyi_splash
    pyi_splash.close()
except ImportError:
    pass

from config import RESOURCE_DIR, SERVER_HOST, SERVER_PORT
from app import app

logger = logging.getLogger("SmartTKADesktop")

def find_available_port(host, preferred_port, max_attempts=20):
    """
    Finds a port that is truly free to bind, starting from preferred_port.
    This prevents collisions with dev servers or zombie processes.
    """
    for p in range(preferred_port, preferred_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, p))
                return p
            except OSError:
                continue
    return preferred_port

def main():
    # Set explicit AppUserModelID so Windows taskbar groups and shows the icon properly
    if sys.platform.startswith("win"):
        try:
            import ctypes
            myappid = "id.go.kemendikdasmen.smarttka.scanner"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass

    # Detect available port to prevent port collisions
    target_port = find_available_port(SERVER_HOST, SERVER_PORT)
    if target_port != SERVER_PORT:
        logger.warning("Port %d is already in use. Binding to isolated port %d", SERVER_PORT, target_port)

    def run_server():
        app.run(host=SERVER_HOST, port=target_port, debug=False, use_reloader=False)

    if "--headless" in sys.argv or "--server" in sys.argv:
        print(f"[*] Starting Smart TKA Scanner Server on http://{SERVER_HOST}:{target_port}")
        run_server()
        return

    # Start Flask backend in daemon thread
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    url = f"http://{SERVER_HOST}:{target_port}"
    
    # Wait for Flask to boot up on target_port
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"{url}/api/status", timeout=1):
                break
        except Exception:
            time.sleep(0.1)

    # Resolve App Icon
    icon_path = RESOURCE_DIR / "static" / "favicon.ico"
    if not icon_path.exists():
        icon_path = RESOURCE_DIR / "app_icon.ico"
    if not icon_path.exists():
        icon_path = RESOURCE_DIR / "app_icon.png"

    # Launch Native Desktop Window via pywebview
    try:
        import webview
        window = webview.create_window(
            title="Smart TKA Scanner & Auto-Uploader",
            url=url,
            width=1280,
            height=850,
            min_size=(960, 600)
        )
        webview.start(icon=str(icon_path) if icon_path.exists() else None)
    except Exception as e:
        import webbrowser
        print(f"[*] Native window not available ({e}). Launching default web browser...")
        webbrowser.open(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down Smart TKA Assistant...")

if __name__ == "__main__":
    main()

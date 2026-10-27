import sys
import os
import time
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

def run_server():
    app.run(host=SERVER_HOST, port=SERVER_PORT, debug=False, use_reloader=False)

def main():
    if "--headless" in sys.argv or "--server" in sys.argv:
        print(f"[*] Starting Smart TKA Scanner Server on http://{SERVER_HOST}:{SERVER_PORT}")
        run_server()
        return

    # Start Flask backend in daemon thread
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    url = f"http://{SERVER_HOST}:{SERVER_PORT}"
    
    # Wait for Flask to boot up
    for _ in range(50):
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

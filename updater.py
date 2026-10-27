import sys
import re
import json
import time
import socket
import logging
import threading
import urllib.request
from typing import Dict, Any, Optional
from config import APP_VERSION, GITHUB_REPO

logger = logging.getLogger("SmartTKAUpdater")

def parse_semver(ver_str: str):
    """
    Parses a version string into a comparable tuple.
    Handles 'v1.0.0', '1.0.1', 'v1.2.0-beta', etc.
    """
    clean = re.sub(r'^[vV]', '', str(ver_str).strip())
    parts = []
    for piece in re.split(r'[-+.]', clean):
        if piece.isdigit():
            parts.append(int(piece))
        else:
            parts.append(piece)
    return tuple(parts)

def is_newer_version(latest_tag: str, current_tag: str) -> bool:
    """
    Returns True if latest_tag represents a strictly higher version than current_tag.
    """
    try:
        from packaging import version
        return version.parse(str(latest_tag).lstrip("vV")) > version.parse(str(current_tag).lstrip("vV"))
    except Exception:
        return parse_semver(latest_tag) > parse_semver(current_tag)

def detect_platform_asset(assets: list) -> Optional[Dict[str, Any]]:
    """
    Selects the best download asset from GitHub release assets based on the host OS.
    """
    if not assets:
        return None
    
    current_os = sys.platform
    keywords = []
    if current_os.startswith("win"):
        keywords = ["windows", "win-x64", "win64", ".zip", ".exe"]
    elif current_os.startswith("linux"):
        keywords = ["linux", "tar.gz", ".deb", ".rpm"]
    elif current_os == "darwin":
        keywords = ["macos", "darwin", "osx", ".zip", ".dmg"]
    
    # Priority 1: Match OS keyword and primary binary extension
    for kw in keywords[:2]:
        for asset in assets:
            name = asset.get("name", "").lower()
            if kw in name:
                return asset

    # Priority 2: Any matching keyword
    for kw in keywords:
        for asset in assets:
            name = asset.get("name", "").lower()
            if kw in name:
                return asset
                
    # Fallback: First asset
    return assets[0]

class UpdateChecker:
    def __init__(self, current_version: str = APP_VERSION, repo: str = GITHUB_REPO):
        self.current_version = current_version
        self.repo = repo
        self._cache: Optional[Dict[str, Any]] = None
        self._last_checked: float = 0.0
        self._cache_ttl_seconds: float = 900.0  # 15 minutes cache
        self._lock = threading.Lock()
        self._is_checking = False

    def check(self, force: bool = False, timeout: int = 5) -> Dict[str, Any]:
        """
        Queries the GitHub API for the latest release.
        Uses in-memory cache if checked recently, unless force=True.
        """
        now = time.time()
        with self._lock:
            if not force and self._cache and (now - self._last_checked < self._cache_ttl_seconds):
                return self._cache

        url = f"https://api.github.com/repos/{self.repo}/releases/latest"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": f"SmartTKAScanner/{self.current_version}",
                "Accept": "application/vnd.github.v3+json"
            }
        )

        # Force IPv4 resolution for api.github.com to circumvent Windows NAT64 connection resets (WinError 10054)
        orig_getaddrinfo = socket.getaddrinfo
        def safe_getaddrinfo(host, port, family=0, socktype=0, proto=0, flags=0):
            if host == "api.github.com":
                family = socket.AF_INET
            return orig_getaddrinfo(host, port, family, socktype, proto, flags)

        try:
            socket.getaddrinfo = safe_getaddrinfo
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.warning("Update check failed for %s: %s", self.repo, e)
            error_msg = str(e)
            if "WinError 10054" in error_msg:
                error_msg = "Koneksi jaringan terputus (WinError 10054)."
            elif "timed out" in error_msg.lower():
                error_msg = "Waktu koneksi habis (timeout)."

            result = {
                "success": False,
                "update_available": False,
                "current_version": self.current_version,
                "latest_version": None,
                "release_name": None,
                "release_notes": None,
                "published_at": None,
                "download_url": None,
                "html_url": f"https://github.com/{self.repo}/releases",
                "asset_name": None,
                "asset_size": None,
                "error": error_msg,
                "checked_at": now
            }
            with self._lock:
                # Cache failure briefly for 60 seconds to avoid repeating failed network calls
                if not self._cache:
                    self._cache = result
                    self._last_checked = now
            return result
        finally:
            socket.getaddrinfo = orig_getaddrinfo

        latest_tag = data.get("tag_name", "").strip()
        has_update = is_newer_version(latest_tag, self.current_version) if latest_tag else False
        
        assets = data.get("assets", [])
        matched_asset = detect_platform_asset(assets)
        download_url = matched_asset.get("browser_download_url") if matched_asset else data.get("html_url")
        asset_name = matched_asset.get("name") if matched_asset else None
        asset_size = matched_asset.get("size") if matched_asset else None

        result = {
            "success": True,
            "update_available": has_update,
            "current_version": self.current_version,
            "latest_version": latest_tag,
            "release_name": data.get("name") or latest_tag,
            "release_notes": data.get("body") or "",
            "published_at": data.get("published_at"),
            "download_url": download_url,
            "html_url": data.get("html_url"),
            "asset_name": asset_name,
            "asset_size": asset_size,
            "error": None,
            "checked_at": now
        }

        with self._lock:
            self._cache = result
            self._last_checked = now

        if has_update:
            logger.info("New update available for Smart TKA Scanner: %s -> %s (%s)", self.current_version, latest_tag, download_url)
        else:
            logger.info("Smart TKA Scanner is up to date (%s)", self.current_version)

        return result

    def start_background_check(self):
        """
        Runs check in a background daemon thread so application startup is non-blocking.
        """
        def _worker():
            try:
                self.check(force=False)
            except Exception as e:
                logger.debug("Background update check error: %s", e)

        thread = threading.Thread(target=_worker, name="BackgroundUpdateChecker", daemon=True)
        thread.start()

# Global singleton
update_checker = UpdateChecker()

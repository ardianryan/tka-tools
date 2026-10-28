import sys
import re
import json
import time
import socket
import logging
import threading
import urllib.request
import urllib.error
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
        # Prioritize Windows Setup installer or zip
        keywords = ["setup", "windows", "win-x64", "win64", ".exe", ".zip"]
    elif current_os.startswith("linux"):
        keywords = ["linux", "tar.gz", ".deb", ".rpm"]
    elif current_os == "darwin":
        keywords = ["macos", "darwin", "osx", ".dmg", ".zip"]
    
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

    def _fetch_from_web_fallback(self, timeout: int = 8) -> Optional[Dict[str, Any]]:
        """
        Fallback parser that checks https://github.com/{repo}/releases/latest
        and expanded_assets if the GitHub REST API hits rate limits (HTTP 403).
        """
        try:
            latest_url = f"https://github.com/{self.repo}/releases/latest"
            req = urllib.request.Request(
                latest_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                final_url = resp.geturl()
                tag = final_url.rstrip("/").split("/")[-1]
                if not tag or tag == "releases":
                    return None

            # Fetch expanded assets list for this tag
            assets_url = f"https://github.com/{self.repo}/releases/expanded_assets/{tag}"
            req_assets = urllib.request.Request(
                assets_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            with urllib.request.urlopen(req_assets, timeout=timeout) as resp_assets:
                html = resp_assets.read().decode("utf-8", errors="ignore")

            matches = re.findall(rf'href="(/[^"]+/{re.escape(tag)}/([^"]+))"', html)
            assets = []
            for path, name in matches:
                assets.append({
                    "name": name,
                    "browser_download_url": f"https://github.com{path}",
                    "size": None
                })

            return {
                "tag_name": tag,
                "name": f"Smart TKA Scanner {tag}",
                "body": f"Versi terbaru {tag} tersedia di GitHub Releases.",
                "published_at": None,
                "html_url": final_url,
                "assets": assets
            }
        except Exception as e:
            logger.debug("Web fallback release fetch failed: %s", e)
            return None

    def check(self, force: bool = False, timeout: int = 5) -> Dict[str, Any]:
        """
        Queries the GitHub API for the latest release, with automatic web fallback
        if rate limited. Uses in-memory cache if checked recently, unless force=True.
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

        orig_getaddrinfo = socket.getaddrinfo
        def safe_getaddrinfo(host, port, family=0, socktype=0, proto=0, flags=0):
            if host in ["api.github.com", "github.com"]:
                family = socket.AF_INET
            return orig_getaddrinfo(host, port, family, socktype, proto, flags)

        data = None
        error_msg = None

        try:
            socket.getaddrinfo = safe_getaddrinfo
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 403:
                logger.info("GitHub API rate limited (403), falling back to public web scraper...")
                data = self._fetch_from_web_fallback(timeout=timeout + 3)
            if not data:
                error_msg = f"HTTP Error {e.code}: {e.reason}"
        except Exception as e:
            error_msg = str(e)
            logger.info("GitHub API check failed (%s), attempting web fallback...", error_msg)
            data = self._fetch_from_web_fallback(timeout=timeout + 3)
        finally:
            socket.getaddrinfo = orig_getaddrinfo

        if not data:
            if "WinError 10054" in str(error_msg):
                error_msg = "Koneksi jaringan terputus (WinError 10054)."
            elif "timed out" in str(error_msg).lower():
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
                if not self._cache:
                    self._cache = result
                    self._last_checked = now
            return result

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

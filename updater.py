import sys
import os
import re
import json
import time
import socket
import logging
import zipfile
import shutil
import threading
import subprocess
from pathlib import Path
import urllib.request
import urllib.error
from typing import Dict, Any, Optional

from config import APP_VERSION, GITHUB_REPO, BASE_DIR

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

def detect_platform_assets(assets: list) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Selects the best download assets for in-place portable update (ZIP) and setup installer (EXE).
    """
    result = {
        "portable": None,
        "installer": None
    }
    if not assets:
        return result

    current_os = sys.platform
    if current_os.startswith("win"):
        for asset in assets:
            name = asset.get("name", "").lower()
            if ".zip" in name and "win" in name:
                result["portable"] = asset
            elif ".exe" in name and "setup" in name:
                result["installer"] = asset
            elif ".zip" in name and not result["portable"]:
                result["portable"] = asset
    elif current_os.startswith("linux"):
        for asset in assets:
            name = asset.get("name", "").lower()
            if "linux" in name and (".tar.gz" in name or ".zip" in name):
                result["portable"] = asset
    elif current_os == "darwin":
        for asset in assets:
            name = asset.get("name", "").lower()
            if "macos" in name or "darwin" in name:
                result["portable"] = asset

    # Fallback portable to first asset if not detected
    if not result["portable"] and assets:
        result["portable"] = assets[0]

    return result

class UpdateChecker:
    def __init__(self, current_version: str = APP_VERSION, repo: str = GITHUB_REPO):
        self.current_version = current_version
        self.repo = repo
        self._cache: Optional[Dict[str, Any]] = None
        self._last_checked: float = 0.0
        self._cache_ttl_seconds: float = 900.0  # 15 minutes cache
        self._lock = threading.Lock()

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
                "portable_url": None,
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
        matched_assets = detect_platform_assets(assets)
        portable_asset = matched_assets.get("portable")
        installer_asset = matched_assets.get("installer")

        portable_url = portable_asset.get("browser_download_url") if portable_asset else None
        installer_url = installer_asset.get("browser_download_url") if installer_asset else None
        primary_download = portable_url or installer_url or data.get("html_url")

        result = {
            "success": True,
            "update_available": has_update,
            "current_version": self.current_version,
            "latest_version": latest_tag,
            "release_name": data.get("name") or latest_tag,
            "release_notes": data.get("body") or "",
            "published_at": data.get("published_at"),
            "download_url": primary_download,
            "portable_url": portable_url,
            "installer_url": installer_url,
            "html_url": data.get("html_url"),
            "asset_name": portable_asset.get("name") if portable_asset else (installer_asset.get("name") if installer_asset else None),
            "asset_size": portable_asset.get("size") if portable_asset else (installer_asset.get("size") if installer_asset else None),
            "error": None,
            "checked_at": now
        }

        with self._lock:
            self._cache = result
            self._last_checked = now

        if has_update:
            logger.info("New update available for Smart TKA Scanner: %s -> %s (%s)", self.current_version, latest_tag, primary_download)
        else:
            logger.info("Smart TKA Scanner is up to date (%s)", self.current_version)

        return result

    def start_background_check(self):
        def _worker():
            try:
                self.check(force=False)
            except Exception as e:
                logger.debug("Background update check error: %s", e)

        thread = threading.Thread(target=_worker, name="BackgroundUpdateChecker", daemon=True)
        thread.start()

def get_secure_update_dir() -> Path:
    """Returns a safe, user-writable directory for downloading and staging update packages."""
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        p = Path(local_app_data) / "SmartTKAScanner" / "updates"
    else:
        import tempfile
        p = Path(tempfile.gettempdir()) / "SmartTKAScanner_updates"
    p.mkdir(parents=True, exist_ok=True)
    return p

def is_base_dir_writable() -> bool:
    """Checks whether the application directory is writable by the current process without UAC elevation."""
    try:
        test_file = BASE_DIR / ".perm_check"
        test_file.touch()
        test_file.unlink()
        return True
    except Exception:
        return False

class InAppUpdateManager:
    """
    Manages in-place zero-data-loss application updates (similar to VS Code / Antigravity).
    Downloads the update package in background and replaces application binaries
    while strictly preserving user data (settings.json, inbox, processed, logs).
    """
    def __init__(self, checker: UpdateChecker):
        self.checker = checker
        self.update_dir = get_secure_update_dir()
        self._lock = threading.Lock()
        self.state = {
            "is_downloading": False,
            "is_applying": False,
            "progress_percent": 0.0,
            "downloaded_bytes": 0,
            "total_bytes": 0,
            "status_text": "Siap",
            "error": None,
            "ready_to_apply": False,
            "target_version": None,
            "zip_path": None
        }

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self.state)

    def start_download_and_apply(self, download_url: str = None, target_version: str = None):
        with self._lock:
            if self.state["is_downloading"] or self.state["is_applying"]:
                return False, "Proses pembaruan sedang berlangsung."
            self.state["is_downloading"] = True
            self.state["progress_percent"] = 0.0
            self.state["status_text"] = "Memulai pengunduhan pembaruan..."
            self.state["error"] = None
            self.state["ready_to_apply"] = False
            self.state["target_version"] = target_version

        def _worker():
            try:
                url = download_url
                if not url:
                    chk = self.checker.check(force=True)
                    url = chk.get("portable_url") or chk.get("download_url")

                if not url or "releases" in url.split("/")[-1]:
                    raise ValueError("URL paket pembaruan tidak valid atau belum dirilis.")

                # Ensure temp_update directory
                self.update_dir.mkdir(parents=True, exist_ok=True)
                dest_zip = self.update_dir / "update_package.zip"

                with self._lock:
                    self.state["status_text"] = "Mengunduh paket pembaruan dari GitHub..."

                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                )

                with urllib.request.urlopen(req, timeout=30) as resp:
                    total_size = int(resp.headers.get("Content-Length", 0))
                    with self._lock:
                        self.state["total_bytes"] = total_size

                    downloaded = 0
                    chunk_size = 64 * 1024
                    with open(dest_zip, "wb") as f_out:
                        while True:
                            chunk = resp.read(chunk_size)
                            if not chunk:
                                break
                            f_out.write(chunk)
                            downloaded += len(chunk)
                            percent = round((downloaded / total_size) * 100, 1) if total_size > 0 else 50.0
                            with self._lock:
                                self.state["downloaded_bytes"] = downloaded
                                self.state["progress_percent"] = percent
                                self.state["status_text"] = f"Mengunduh pembaruan ({percent}% - {round(downloaded / (1024*1024), 1)} MB)..."

                with self._lock:
                    self.state["is_downloading"] = False
                    self.state["ready_to_apply"] = True
                    self.state["zip_path"] = str(dest_zip)
                    self.state["status_text"] = "Pengunduhan selesai. Menyiapkan instalasi otomatis..."

                # Automatically trigger apply
                self.apply_update()

            except Exception as e:
                logger.error("In-app update download failed: %s", e)
                with self._lock:
                    self.state["is_downloading"] = False
                    self.state["error"] = str(e)
                    self.state["status_text"] = f"Gagal mengunduh pembaruan: {e}"

        threading.Thread(target=_worker, name="InAppUpdateWorker", daemon=True).start()
        return True, "Pengunduhan pembaruan dimulai."

    def apply_update(self) -> tuple:
        with self._lock:
            self.state["is_applying"] = True
            self.state["status_text"] = "Mengekstrak dan memasang pembaruan..."

        try:
            zip_path = self.update_dir / "update_package.zip"
            if not zip_path.exists():
                raise FileNotFoundError("Berkas paket pembaruan tidak ditemukan.")

            extract_dir = self.update_dir / "extracted"
            if extract_dir.exists():
                shutil.rmtree(extract_dir, ignore_errors=True)
            extract_dir.mkdir(parents=True, exist_ok=True)

            # 1. Extract zip package
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)

            # Check if extracted root contains a single subfolder (e.g. SmartTKAScanner/)
            subdirs = [d for d in extract_dir.iterdir() if d.is_dir()]
            files = [f for f in extract_dir.iterdir() if f.is_file()]
            payload_dir = extract_dir
            if len(subdirs) == 1 and not files:
                payload_dir = subdirs[0]

            # 2. CRITICAL PROTECTION: Remove any user data files from payload so user data is NEVER overwritten
            protected_patterns = [
                "settings.json", "inbox", "processed", "logs",
                "temp_uploads", "DokumenTKA", ".env"
            ]
            for item in payload_dir.iterdir():
                if item.name in protected_patterns:
                    if item.is_dir():
                        shutil.rmtree(item, ignore_errors=True)
                    else:
                        try:
                            item.unlink()
                        except Exception:
                            pass

            # 3. Create Windows bootstrap runner apply_update.cmd
            cmd_script = self.update_dir / "apply_update.cmd"
            script_content = f"""@echo off
chcp 65001 >nul
title Smart TKA Scanner - Pembaruan Otomatis
echo.
echo ========================================================
echo   MEMASANG PEMBARUAN SMART TKA SCANNER...
echo   Mohon tunggu beberapa detik, jangan tutup jendela ini.
echo ========================================================
echo.

:: Tutup proses SmartTKAScanner jika masih berjalan
taskkill /f /im SmartTKAScanner.exe >nul 2>&1
timeout /t 2 /nobreak >nul

:: Salin binary dan aset aplikasi baru tanpa menimpa folder data pengguna
xcopy /E /Y /I "{payload_dir}\\*" "{BASE_DIR}\\" >nul 2>&1

:: Bersihkan folder sementara
timeout /t 1 /nobreak >nul
rd /s /q "{self.update_dir}" >nul 2>&1

:: Relaunch Smart TKA Scanner
echo.
echo Pembaruan selesai! Memulai kembali aplikasi...
start "" "{BASE_DIR}\\SmartTKAScanner.exe"
exit
"""
            with open(cmd_script, "w", encoding="utf-8") as f_cmd:
                f_cmd.write(script_content)

            with self._lock:
                self.state["status_text"] = "Pembaruan siap dipasang! Merestart aplikasi dalam 2 detik..."

            # 4. Spawn detached bootstrap updater runner
            if not is_base_dir_writable():
                logger.info("Application directory is protected (Program Files). Requesting UAC elevation for update...")
                ps_script = f"Start-Process cmd.exe -ArgumentList '/c \"\"{cmd_script}\"\"' -Verb RunAs"
                subprocess.Popen(
                    ["powershell.exe", "-WindowStyle", "Hidden", "-Command", ps_script],
                    creationflags=0x08000000 | 0x00000008,
                    close_fds=True
                )
            else:
                subprocess.Popen(
                    ["cmd.exe", "/c", str(cmd_script)],
                    cwd=str(BASE_DIR),
                    creationflags=0x08000000 | 0x00000008,  # CREATE_NO_WINDOW | DETACHED_PROCESS
                    close_fds=True
                )

            # 5. Smoothly exit after 1.5 seconds
            def _delayed_exit():
                time.sleep(1.5)
                os._exit(0)

            threading.Thread(target=_delayed_exit, daemon=True).start()
            return True, "Pembaruan berhasil disiapkan. Aplikasi akan merestart otomatis."

        except Exception as e:
            logger.error("Failed to apply update: %s", e)
            with self._lock:
                self.state["is_applying"] = False
                self.state["error"] = str(e)
                self.state["status_text"] = f"Gagal memasang pembaruan: {e}"
            return False, str(e)

# Global singletons
update_checker = UpdateChecker()
in_app_updater = InAppUpdateManager(update_checker)

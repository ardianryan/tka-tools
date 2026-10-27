import logging
import socket
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from config import TKA_BASE_URL, TKA_USERNAME, TKA_PASSWORD, TKA_KD_UJIAN

# Force IPv4 on Windows to prevent IPv6 NAT64 connection resets
_orig_getaddrinfo = socket.getaddrinfo

def _ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)

socket.getaddrinfo = _ipv4_getaddrinfo

logger = logging.getLogger("TKAClient")

class TKAClient:
    def __init__(self, username=TKA_USERNAME, password=TKA_PASSWORD, base_url=TKA_BASE_URL):
        self.username = username
        self.password = password
        self.base_url = base_url.rstrip("/")
        self.is_authenticated = False
        self.session = None
        self._init_session()

    def _init_session(self):
        """Initializes a new requests Session with retries and connection management"""
        if self.session:
            try:
                self.session.close()
            except Exception:
                pass
        self.session = requests.Session()
        retries = Retry(
            total=3,
            connect=3,
            read=3,
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504],
            raise_on_status=False
        )
        adapter = HTTPAdapter(max_retries=retries, pool_connections=5, pool_maxsize=10)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{self.base_url}/"
        })
        self.is_authenticated = False

    def login(self) -> bool:
        """Performs authentication with portal TKA"""
        try:
            self._init_session()
            # 1. Warm-up session
            self.session.get(f"{self.base_url}/", timeout=15)
            
            # 2. Post login
            login_url = f"{self.base_url}/api/v1/login"
            payload = {
                "username": self.username,
                "password": self.password,
                "secure": ""
            }
            res = self.session.post(login_url, data=payload, timeout=20)
            data = res.json()
            if data.get("login"):
                self.is_authenticated = True
                logger.info("Successfully authenticated with TKA Portal as %s", self.username)
                return True
            else:
                self.is_authenticated = False
                logger.error("Login failed: %s", data.get("msg"))
                return False
        except Exception as e:
            self.is_authenticated = False
            logger.error("Login exception: %s", str(e))
            return False

    def ensure_authenticated(self):
        if not self.is_authenticated:
            if not self.login():
                raise ConnectionError("Gagal login ke portal TKA Kemendikdasmen.")

    def _safe_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """
        Executes request with automatic re-login and reconnect if remote connection was terminated.
        """
        max_attempts = 2
        last_error = None
        
        for attempt in range(max_attempts):
            try:
                self.ensure_authenticated()
                if "timeout" not in kwargs:
                    kwargs["timeout"] = 25
                res = self.session.request(method, url, **kwargs)
                
                # Check if server redirected to login or returned empty session
                if res.status_code in [401, 403] or "/login" in res.url:
                    logger.warning("Session expired or unauthorized, re-authenticating...")
                    self.is_authenticated = False
                    self.login()
                    continue
                    
                return res
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, Exception) as e:
                last_error = e
                logger.warning("Request failed on attempt %d: %s. Re-authenticating...", attempt + 1, str(e))
                self.is_authenticated = False
                time.sleep(0.5)
                self.login()

        raise ConnectionError(f"Gagal menghubungi server TKA setelah beberapa percobaan: {last_error}")

    def get_absen_slots(self, kd_ujian=TKA_KD_UJIAN):
        url = f"{self.base_url}/api/v2/absen/getAll"
        res = self._safe_request("POST", url, data={"kd_ujian": kd_ujian})
        try:
            data = res.json()
            return data.get("rows", [])
        except Exception as e:
            logger.error("Failed to parse absen JSON: %s (Content: %s)", str(e), res.text[:200])
            return []

    def get_pelaksanaan_slots(self, kd_ujian=TKA_KD_UJIAN):
        url = f"{self.base_url}/api/v2/pelaksanaan/getAll"
        res = self._safe_request("POST", url, data={"kd_ujian": kd_ujian})
        try:
            data = res.json()
            return data.get("rows", [])
        except Exception as e:
            logger.error("Failed to parse pelaksanaan JSON: %s (Content: %s)", str(e), res.text[:200])
            return []

    def upload_absen(self, slot_data: dict, file_path: str):
        url = f"{self.base_url}/api/v2/absen/save"
        filename = file_path.split("/")[-1].split("\\")[-1]
        
        form_data = {k: str(v) for k, v in slot_data.items() if k not in ["filename_1", "status"]}
        form_data["absen1"] = filename
        
        with open(file_path, "rb") as f:
            files = {
                "absen1_file": (filename, f, "image/jpeg")
            }
            res = self._safe_request(
                "POST",
                url,
                data=form_data,
                files=files,
                headers={"X-Requested-With": "XMLHttpRequest"},
                timeout=60
            )
            try:
                return res.json()
            except Exception:
                return {"success": False, "msg": f"Server raw response ({res.status_code}): {res.text[:200]}"}

    def upload_pelaksanaan(self, slot_data: dict, file_path: str):
        url = f"{self.base_url}/api/v2/pelaksanaan/upload"
        filename = file_path.split("/")[-1].split("\\")[-1]
        
        form_data = {k: str(v) for k, v in slot_data.items() if k not in ["filename", "status"]}
        form_data["gambar"] = filename
        
        with open(file_path, "rb") as f:
            files = {
                "gambar_file": (filename, f, "image/jpeg")
            }
            res = self._safe_request(
                "POST",
                url,
                data=form_data,
                files=files,
                headers={"X-Requested-With": "XMLHttpRequest"},
                timeout=60
            )
            try:
                return res.json()
            except Exception:
                return {"success": False, "msg": f"Server raw response ({res.status_code}): {res.text[:200]}"}

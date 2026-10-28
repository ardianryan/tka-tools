import json
import logging
import random
import re
import socket
import string
import time
from pathlib import Path
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from config import BASE_DIR, TKA_BASE_URL, TKA_USERNAME, TKA_PASSWORD, TKA_KD_UJIAN

# Force IPv4 on Windows to prevent IPv6 NAT64 connection resets
_orig_getaddrinfo = socket.getaddrinfo

def _ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)

socket.getaddrinfo = _ipv4_getaddrinfo

logger = logging.getLogger("TKAClient")
SESSION_FILE = BASE_DIR / ".tka_session.json"

class TKAClient:
    def __init__(self, username=TKA_USERNAME, password=TKA_PASSWORD, base_url=TKA_BASE_URL):
        self.username = username
        self.password = password
        self.base_url = (base_url or TKA_BASE_URL).rstrip("/")
        self.is_authenticated = False
        self.require_captcha = False
        self.last_login_msg = ""
        self.session = None
        self.csrf_token = None
        self.user_kode = {}
        self._init_session()
        # Restore active persistent session if available
        if self.username:
            self.load_session()

    def _init_session(self):
        """Initializes a new requests Session with retries and browser headers"""
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
            "Referer": f"{self.base_url}/"
        })
        self.is_authenticated = False
        self.csrf_token = None
        self._parse_user_kode()

    def save_session(self):
        """Persists active session cookies and CSRF token to survive app restarts"""
        try:
            data = {
                "username": self.username,
                "cookies": self.session.cookies.get_dict(),
                "csrf_token": self.csrf_token,
                "saved_at": time.time()
            }
            with open(SESSION_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f)
            logger.info("TKA session cookies saved to disk (%s)", SESSION_FILE.name)
        except Exception as e:
            logger.debug("Failed saving TKA session: %s", e)

    def load_session(self) -> bool:
        """Loads and verifies existing persistent session from disk"""
        try:
            if not SESSION_FILE.exists():
                return False
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("username") and self.username and data.get("username") != self.username:
                return False
            cookies = data.get("cookies", {})
            if cookies:
                self.session.cookies.update(cookies)
                self.csrf_token = data.get("csrf_token")
                return self.verify_session()
        except Exception as e:
            logger.debug("Failed loading saved session: %s", e)
        return False

    def verify_session(self) -> bool:
        """Checks if current session is authenticated without triggering captcha"""
        try:
            home_url = f"{self.base_url}/user/home"
            res = self.session.get(home_url, timeout=15)
            if res.status_code == 200 and "/login" not in res.url:
                m = re.search(r'csrfToken\s*=\s*[\'"]([^\'"]+)[\'"]', res.text)
                if m:
                    self.csrf_token = m.group(1)
                self.is_authenticated = True
                self.require_captcha = False
                logger.info("Active TKA session verified and restored for %s (CSRF: %s...)", self.username, (self.csrf_token or "")[:10])
                return True
        except Exception as e:
            logger.debug("Session verification failed: %s", e)
        self.is_authenticated = False
        return False

    def get_captcha_image(self) -> bytes:
        """Fetches fresh captcha image from /login/secure?sid=... using current session"""
        try:
            if not self.session.cookies:
                self.session.get(f"{self.base_url}/", timeout=15)
            r = self.session.get(f"{self.base_url}/login/secure?sid={random.random()}", timeout=15)
            if r.status_code == 200:
                return r.content
        except Exception as e:
            logger.error("Failed fetching captcha image: %s", e)
        return b""

    def _parse_user_kode(self):
        """Extracts kd_jenjang, kd_prop, kd_kota, kd_sek from school username (e.g. U05120005)"""
        u = (self.username or "").strip()
        if len(u) >= 9:
            self.user_kode = {
                "kd_jenjang": u[0],
                "kd_prop": u[1:3],
                "kd_kota": u[3:5],
                "kd_sek": u[5:9]
            }
        else:
            self.user_kode = {}

    def _get_request_id(self) -> str:
        """Generates a unique request ID per API call to prevent server replay rejection"""
        t = hex(int(time.time() * 1000))[2:]
        rand_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        return f"{t}-{rand_str}"

    def login(self, username=None, password=None, secure="") -> bool:
        """Performs authentication with portal TKA and captures active CSRF token from /user/home"""
        if username:
            self.username = username
            self._parse_user_kode()
        if password:
            self.password = password

        try:
            # 1. Warm-up session
            if not self.session.cookies:
                self.session.get(f"{self.base_url}/", timeout=15)
            
            # 2. Post login
            login_url = f"{self.base_url}/api/v1/login"
            payload = {
                "username": self.username,
                "password": self.password,
                "secure": secure or ""
            }
            res = self.session.post(login_url, data=payload, headers={"X-Requested-With": "XMLHttpRequest"}, timeout=20)
            data = res.json()
            if not data.get("login"):
                self.is_authenticated = False
                self.last_login_msg = data.get("msg", "Login gagal")
                if data.get("showSecure") or "keamanan" in self.last_login_msg.lower():
                    self.require_captcha = True
                    logger.warning("TKA Portal requires captcha challenge: %s", self.last_login_msg)
                else:
                    self.require_captcha = False
                    logger.error("Login failed: %s", self.last_login_msg)
                return False

            # 3. Standard browser page navigation to /user/home to capture active CSRF token
            home_url = f"{self.base_url}/user/home"
            home_res = self.session.get(home_url, timeout=20)
            if home_res.status_code == 200:
                match = re.search(r'csrfToken\s*=\s*[\'"]([^\'"]+)[\'"]', home_res.text)
                if match:
                    self.csrf_token = match.group(1)
                    logger.info("Captured CSRF token for session: %s...", self.csrf_token[:10])

            self.is_authenticated = True
            self.require_captcha = False
            self.last_login_msg = "Login berhasil"
            self.save_session()
            logger.info("Successfully authenticated with TKA Portal as %s", self.username)
            return True
        except Exception as e:
            self.is_authenticated = False
            self.require_captcha = False
            self.last_login_msg = str(e)
            logger.error("Login exception: %s", str(e))
            return False

    def ensure_authenticated(self):
        if not self.is_authenticated:
            if not self.verify_session():
                if not self.login():
                    if self.require_captcha:
                        raise ConnectionError("Portal TKA memerlukan kode keamanan (CAPTCHA). Silakan buka antarmuka dan masukkan kode keamanan.")
                    raise ConnectionError(f"Gagal login ke portal TKA Kemendikdasmen: {self.last_login_msg}")

    def _safe_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """
        Executes request with anti-replay X-REQUEST-ID, CSRF headers, and automatic re-login.
        """
        max_attempts = 2
        last_error = None
        
        for attempt in range(max_attempts):
            try:
                self.ensure_authenticated()
                if "timeout" not in kwargs:
                    kwargs["timeout"] = 25

                # Setup anti-replay & CSRF headers
                headers = kwargs.get("headers", {})
                headers["X-Requested-With"] = "XMLHttpRequest"
                headers["X-REQUEST-ID"] = self._get_request_id()
                if self.csrf_token:
                    headers["X-CSRF-TOKEN"] = self.csrf_token
                kwargs["headers"] = headers

                # Inject _csrf_token into form data if dict
                if self.csrf_token and "data" in kwargs and isinstance(kwargs["data"], dict):
                    kwargs["data"]["_csrf_token"] = self.csrf_token

                res = self.session.request(method, url, **kwargs)
                
                # Check if server redirected to login or returned CSRF/session error
                if res.status_code in [401, 403] or "/login" in res.url:
                    last_error = f"HTTP {res.status_code}: {res.text[:200]}"
                    logger.warning("Session expired or unauthorized (%s), re-authenticating...", last_error)
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

    def get_ujian_list(self) -> list:
        """Queries /api/v2/combo/ujian to discover available exam categories for this school"""
        url = f"{self.base_url}/api/v2/combo/ujian"
        payload = dict(self.user_kode) if self.user_kode else {}
        try:
            res = self._safe_request(
                "POST",
                url,
                data=payload,
                headers={"Referer": f"{self.base_url}/user/pelaksanaan"}
            )
            data = res.json()
            rows = data.get("rows", [])
            return [r.get("key") for r in rows if r.get("key")]
        except Exception as e:
            logger.warning("Failed to fetch ujian combo list: %s", e)
            return []

    def get_pelaksanaan_slots(self, kd_ujian=None) -> list:
        """Fetches pelaksanaan (BAP) slots from the portal with automatic school code parameters"""
        url = f"{self.base_url}/api/v2/pelaksanaan/getAll"
        
        keys = [kd_ujian] if kd_ujian else []
        if not keys:
            keys = self.get_ujian_list()
        if not keys and self.user_kode.get("kd_jenjang"):
            keys = [self.user_kode["kd_jenjang"]]
        if not keys:
            keys = [TKA_KD_UJIAN]

        all_rows = []
        for key in keys:
            payload = dict(self.user_kode) if self.user_kode else {}
            payload["kd_ujian"] = key
            try:
                res = self._safe_request(
                    "POST",
                    url,
                    data=payload,
                    headers={"Referer": f"{self.base_url}/user/pelaksanaan"}
                )
                data = res.json()
                rows = data.get("rows", [])
                if rows:
                    all_rows.extend(rows)
            except Exception as e:
                logger.error("Failed to parse pelaksanaan JSON for ujian %s: %s", key, str(e))

        return all_rows

    def get_absen_slots(self, kd_ujian=None) -> list:
        """Fetches absen (Daftar Hadir) slots from the portal with automatic school code parameters"""
        url = f"{self.base_url}/api/v2/absen/getAll"
        
        keys = [kd_ujian] if kd_ujian else []
        if not keys:
            keys = self.get_ujian_list()
        if not keys and self.user_kode.get("kd_jenjang"):
            keys = [self.user_kode["kd_jenjang"]]
        if not keys:
            keys = [TKA_KD_UJIAN]

        all_rows = []
        for key in keys:
            payload = dict(self.user_kode) if self.user_kode else {}
            payload["kd_ujian"] = key
            try:
                res = self._safe_request(
                    "POST",
                    url,
                    data=payload,
                    headers={"Referer": f"{self.base_url}/user/absen"}
                )
                data = res.json()
                rows = data.get("rows", [])
                if rows:
                    all_rows.extend(rows)
            except Exception as e:
                logger.error("Failed to parse absen JSON for ujian %s: %s", key, str(e))

        return all_rows

    def upload_absen(self, slot_data: dict, file_path: str):
        """Uploads scanned Daftar Hadir image to /api/v2/absen/save"""
        url = f"{self.base_url}/api/v2/absen/save"
        filename = Path(file_path).name
        
        form_data = {k: str(v) for k, v in slot_data.items() if v is not None and k not in ["filename_1", "status"]}
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
                headers={"Referer": f"{self.base_url}/user/absen"},
                timeout=60
            )
            try:
                return res.json()
            except Exception:
                return {"success": False, "msg": f"Server raw response ({res.status_code}): {res.text[:200]}"}

    def upload_pelaksanaan(self, slot_data: dict, file_path: str):
        """Uploads scanned Berita Acara Pelaksanaan image to /api/v2/pelaksanaan/upload"""
        url = f"{self.base_url}/api/v2/pelaksanaan/upload"
        filename = Path(file_path).name
        
        form_data = {k: str(v) for k, v in slot_data.items() if v is not None and k not in ["filename", "status"]}
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
                headers={"Referer": f"{self.base_url}/user/pelaksanaan"},
                timeout=60
            )
            try:
                return res.json()
            except Exception:
                return {"success": False, "msg": f"Server raw response ({res.status_code}): {res.text[:200]}"}

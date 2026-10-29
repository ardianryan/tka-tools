import os
import sys
from pathlib import Path

# Detect PyInstaller bundle mode
if getattr(sys, 'frozen', False):
    # PyInstaller extracts bundled files (templates, static) to sys._MEIPASS
    RESOURCE_DIR = Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent))
    # Executable base directory
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    RESOURCE_DIR = Path(__file__).resolve().parent
    BASE_DIR = Path(__file__).resolve().parent

# Persistent User Configuration Directory (Safe from updates, re-installs, and UAC restrictions)
if sys.platform == "win32":
    appdata_base = os.getenv("APPDATA") or os.getenv("LOCALAPPDATA") or str(Path.home() / "AppData" / "Roaming")
    USER_DATA_DIR = Path(appdata_base) / "SmartTKAScanner"
else:
    USER_DATA_DIR = Path.home() / ".config" / "smart-tka-scanner"

USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

# Read .env if present
env_file = BASE_DIR / ".env"
if not env_file.exists():
    env_file = USER_DATA_DIR / ".env"
if env_file.exists():
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

# Application Metadata & GitHub Repository for Updates
APP_VERSION = os.getenv("APP_VERSION", "v1.0.5")
GITHUB_REPO = os.getenv("GITHUB_REPO", "ardianryan/tka-tools")

# TKA Portal Credentials (Default kosong untuk keamanan open-source, atur via settings.json atau Dashboard)
TKA_BASE_URL = os.getenv("TKA_BASE_URL", "https://tka.kemendikdasmen.go.id").rstrip("/")
TKA_USERNAME = os.getenv("TKA_USERNAME", "")
TKA_PASSWORD = os.getenv("TKA_PASSWORD", "")
TKA_KD_UJIAN = os.getenv("TKA_KD_UJIAN", "U")

# Server Binding (Default to localhost for security)
SERVER_HOST = os.getenv("SERVER_HOST", "127.0.0.1")
SERVER_PORT = int(os.getenv("SERVER_PORT", "5000"))

# Storage Paths
INBOX_DIR = BASE_DIR / "inbox"
PROCESSED_DIR = BASE_DIR / "processed"
DUPLICATES_DIR = PROCESSED_DIR / "duplicates"
UPLOAD_TEMP_DIR = BASE_DIR / "temp_uploads"
LOGS_DIR = BASE_DIR / "logs"
LOG_CSV_PATH = LOGS_DIR / "riwayat_unggah.csv"
LOG_JSON_PATH = LOGS_DIR / "riwayat_unggah.jsonl"

for p in [INBOX_DIR, PROCESSED_DIR, DUPLICATES_DIR, UPLOAD_TEMP_DIR, LOGS_DIR]:
    p.mkdir(parents=True, exist_ok=True)

# Security Allowlist for file uploads & previews
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}
MAX_CONTENT_LENGTH = 32 * 1024 * 1024 # 32 MB

# Scanner Defaults
DEFAULT_SCANNER_DPI = 200
DEFAULT_SOURCE = "ADF"

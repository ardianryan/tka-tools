import json
import logging
import os
import shutil
from pathlib import Path
from config import BASE_DIR, RESOURCE_DIR, USER_DATA_DIR, TKA_BASE_URL, TKA_USERNAME, TKA_PASSWORD, TKA_KD_UJIAN

logger = logging.getLogger("SettingsManager")

# Primary settings file is always in the user's AppData directory (writable, permanent across updates)
PRIMARY_SETTINGS_FILE = USER_DATA_DIR / "settings.json"
BASE_SETTINGS_FILE = BASE_DIR / "settings.json"
EXAMPLE_FILE = RESOURCE_DIR / "settings.example.json"

# Fallback candidate search paths for automatic seamless detection & migration
FALLBACK_CANDIDATES = [
    BASE_SETTINGS_FILE,
    Path.home() / "Documents" / "tkascanner" / "settings.json",
]

DEFAULT_SETTINGS = {
    "scanner": {
        "device_id": "auto",
        "device_name": "auto",
        "default_source": "ADF",
        "dpi": 200
    },
    "portal": {
        "base_url": TKA_BASE_URL,
        "username": TKA_USERNAME,
        "password": TKA_PASSWORD,
        "kd_ujian": TKA_KD_UJIAN
    },
    "ocr_rules": {
        "date_day_map": {
            "26": 1,
            "27": 2,
            "28": 3,
            "29": 4
        },
        "day_name_map": {
            "senin": 1,
            "selasa": 2,
            "rabu": 3,
            "kamis": 4,
            "jumat": 5,
            "sabtu": 6
        },
        "room_regex": [
            r"Lab\s*([1-9])",
            r"Laboratorium\s*([1-9])",
            r"Ruang\s*([0-9]+)"
        ],
        "server_prefix": "",
        "min_match_score": 60
    },
    "upload": {
        "delay_min": 3.0,
        "delay_max": 5.0
    }
}

def _merge_settings(data: dict) -> dict:
    """Merges loaded dictionary with DEFAULT_SETTINGS to ensure all keys exist."""
    merged = DEFAULT_SETTINGS.copy()
    for section, vals in data.items():
        if isinstance(vals, dict) and section in merged:
            merged[section] = merged[section].copy()
            merged[section].update(vals)
        else:
            merged[section] = vals
    return merged

def load_settings() -> dict:
    """
    Loads application settings with smart multi-location detection and auto-migration.
    1. Reads from PRIMARY_SETTINGS_FILE (%APPDATA%\\SmartTKAScanner\\settings.json)
    2. If missing, scans fallback locations (BASE_DIR, Documents/tkascanner)
    3. Auto-migrates found settings into PRIMARY_SETTINGS_FILE
    4. Falls back to settings.example.json or DEFAULT_SETTINGS
    """
    target_file = None

    if PRIMARY_SETTINGS_FILE.exists():
        target_file = PRIMARY_SETTINGS_FILE
    else:
        # Check fallback candidate paths for automatic migration
        for cand in FALLBACK_CANDIDATES:
            try:
                if cand.resolve() != PRIMARY_SETTINGS_FILE.resolve() and cand.exists():
                    with open(cand, "r", encoding="utf-8") as f:
                        test_data = json.load(f)
                    p = test_data.get("portal", {})
                    if p.get("username"):
                        logger.info("Found existing settings in %s, migrating to %s", cand, PRIMARY_SETTINGS_FILE)
                        target_file = cand
                        # Copy immediately to primary location
                        try:
                            USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(cand, PRIMARY_SETTINGS_FILE)
                            target_file = PRIMARY_SETTINGS_FILE
                        except Exception as e:
                            logger.warning("Could not auto-copy settings to primary: %s", e)
                        break
            except Exception:
                continue

    if not target_file or not target_file.exists():
        # First-time initialization
        if EXAMPLE_FILE.exists() and EXAMPLE_FILE.resolve() != PRIMARY_SETTINGS_FILE.resolve():
            try:
                USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
                shutil.copy2(EXAMPLE_FILE, PRIMARY_SETTINGS_FILE)
                target_file = PRIMARY_SETTINGS_FILE
            except Exception as e:
                logger.warning("Could not copy settings.example.json: %s", str(e))
                save_settings(DEFAULT_SETTINGS)
                return DEFAULT_SETTINGS.copy()
        else:
            save_settings(DEFAULT_SETTINGS)
            return DEFAULT_SETTINGS.copy()

    try:
        with open(target_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return _merge_settings(data)
    except Exception as e:
        logger.error("Failed to read settings from %s: %s", target_file, str(e))
        return DEFAULT_SETTINGS.copy()

def save_settings(new_settings: dict) -> bool:
    """
    Saves settings permanently to PRIMARY_SETTINGS_FILE (%APPDATA%\\SmartTKAScanner\\settings.json).
    Also makes a best-effort mirror to BASE_DIR if writable.
    """
    saved_primary = False
    try:
        USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(PRIMARY_SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(new_settings, f, indent=2, ensure_ascii=False)
        logger.info("Saved settings to primary storage: %s", PRIMARY_SETTINGS_FILE)
        saved_primary = True
    except Exception as e:
        logger.error("Failed to save settings to primary storage %s: %s", PRIMARY_SETTINGS_FILE, str(e))

    # Optional mirror to BASE_DIR (if writable and distinct from primary)
    try:
        if BASE_SETTINGS_FILE.resolve() != PRIMARY_SETTINGS_FILE.resolve():
            with open(BASE_SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(new_settings, f, indent=2, ensure_ascii=False)
            logger.debug("Mirrored settings to %s", BASE_SETTINGS_FILE)
    except Exception:
        pass

    return saved_primary

import json
import logging
import shutil
from pathlib import Path
from config import BASE_DIR, RESOURCE_DIR, TKA_BASE_URL, TKA_USERNAME, TKA_PASSWORD, TKA_KD_UJIAN

logger = logging.getLogger("SettingsManager")
SETTINGS_FILE = BASE_DIR / "settings.json"
EXAMPLE_FILE = RESOURCE_DIR / "settings.example.json"

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

def load_settings() -> dict:
    if not SETTINGS_FILE.exists():
        if EXAMPLE_FILE.exists() and EXAMPLE_FILE != SETTINGS_FILE:
            try:
                shutil.copy2(EXAMPLE_FILE, SETTINGS_FILE)
            except Exception as e:
                logger.warning("Could not copy settings.example.json: %s", str(e))
                save_settings(DEFAULT_SETTINGS)
        else:
            save_settings(DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS.copy()
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Merge with defaults for missing keys
            merged = DEFAULT_SETTINGS.copy()
            for section, vals in data.items():
                if isinstance(vals, dict) and section in merged:
                    merged[section].update(vals)
                else:
                    merged[section] = vals
            return merged
    except Exception as e:
        logger.error("Failed to read settings.json: %s", str(e))
        return DEFAULT_SETTINGS.copy()

def save_settings(new_settings: dict) -> bool:
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(new_settings, f, indent=2, ensure_ascii=False)
        logger.info("Saved settings to %s", SETTINGS_FILE)
        return True
    except Exception as e:
        logger.error("Failed to save settings.json: %s", str(e))
        return False

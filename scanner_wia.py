import sys
import subprocess
import json
import logging
from pathlib import Path
from config import INBOX_DIR, RESOURCE_DIR
from settings_manager import load_settings

logger = logging.getLogger("ScannerWIA")

def _get_subprocess_flags() -> dict:
    """Returns Windows flags to completely prevent console/cmd windows from popping up."""
    flags = {}
    if sys.platform == "win32":
        flags["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0  # SW_HIDE
        flags["startupinfo"] = si
    return flags

PS_CHECK_SCANNER = """
$wia = New-Object -ComObject WIA.DeviceManager
$found = @()
foreach ($info in $wia.DeviceInfos) {
    $name = $info.Properties.Item('Name').Value
    $id = $info.DeviceID
    $found += @{ name = $name; id = $id }
}
$found | ConvertTo-Json -Compress
"""

class ScannerWIA:
    def __init__(self, output_dir=INBOX_DIR):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.script_path = RESOURCE_DIR / "wia_scan.ps1"

    def list_devices(self) -> list:
        if sys.platform != "win32":
            return []
        try:
            cmd = ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass", "-Command", PS_CHECK_SCANNER]
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
                **_get_subprocess_flags()
            )
            out = res.stdout.strip()
            if out:
                data = json.loads(out)
                if isinstance(data, dict):
                    return [data]
                return data
            return []
        except Exception as e:
            logger.error("Error listing WIA devices: %s", str(e))
            return []

    def get_scanner_status(self, device_id: str = None, device_name: str = None) -> dict:
        settings = load_settings().get("scanner", {})
        target_id = device_id or settings.get("device_id", "auto")
        target_name = device_name or settings.get("device_name", "auto")

        devices = self.list_devices()
        if not devices:
            return {"online": False, "device": None, "available_devices": []}

        # 1. Match by specific ID
        if target_id and target_id != "auto":
            for d in devices:
                if d.get("id") == target_id:
                    return {"online": True, "device": d, "available_devices": devices}

        # 2. Match by Name pattern
        if target_name and target_name != "auto":
            for d in devices:
                if target_name.lower() in d.get("name", "").lower():
                    return {"online": True, "device": d, "available_devices": devices}

        # 3. Default to the first detected device
        return {"online": True, "device": devices[0], "available_devices": devices}

    def get_epson_status(self):
        """Backward compatibility alias"""
        return self.get_scanner_status()

    def trigger_scan(self, source: str = None, prefix: str = "Scan", device_id: str = None, device_name: str = None, dpi: int = None) -> dict:
        if sys.platform != "win32":
            return {
                "success": False,
                "msg": "Scanner hardware WIA hanya didukung di Windows. Di macOS/Linux, silakan gunakan pemindaian lewat software vendor dan masukkan berkas ke folder inbox/."
            }
        settings = load_settings().get("scanner", {})
        
        # Source resolution
        if not source:
            source = settings.get("default_source", "ADF")
        source = "ADF" if str(source).strip().upper() == "ADF" else "Flatbed"
        
        # Sanitize parameters
        prefix = "".join(c for c in str(prefix) if c.isalnum() or c in "_-") or "Scan"
        target_id = device_id or settings.get("device_id", "auto")
        target_name = device_name or settings.get("device_name", "auto")
        dpi_val = int(dpi or settings.get("dpi", 200))

        try:
            cmd = [
                "powershell",
                "-NoProfile",
                "-WindowStyle", "Hidden",
                "-ExecutionPolicy", "Bypass",
                "-File", str(self.script_path),
                "-Source", source,
                "-OutputDir", str(self.output_dir.resolve()),
                "-FilePrefix", prefix,
                "-DeviceId", str(target_id),
                "-DeviceName", str(target_name),
                "-Dpi", str(dpi_val)
            ]
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                **_get_subprocess_flags()
            )
            out = res.stdout.strip()
            if "ERROR:" in out:
                return {"success": False, "msg": out}
            
            for line in out.splitlines():
                if line.startswith("{") and line.endswith("}"):
                    return json.loads(line)
            return {"success": False, "msg": out or "Pemindaian tidak mengembalikan output berkas"}
        except subprocess.TimeoutExpired:
            return {"success": False, "msg": "Waktu pemindaian melebihi batas (Timeout 120 detik)"}
        except Exception as e:
            return {"success": False, "msg": f"Gagal memindai: {str(e)}"}

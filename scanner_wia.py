import sys
import os
import subprocess
import json
import logging
import shutil
from pathlib import Path
from config import INBOX_DIR, RESOURCE_DIR, BASE_DIR
from settings_manager import load_settings

logger = logging.getLogger("ScannerWIA")

def get_powershell_exe() -> str:
    """
    Finds powershell.exe with multiple fallback strategies:
    1. SystemRoot\\System32\\WindowsPowerShell\\v1.0\\powershell.exe (standard Windows location)
    2. SystemRoot\\SysWOW64\\WindowsPowerShell\\v1.0\\powershell.exe (32-bit on 64-bit Windows)
    3. pwsh (PowerShell Core / 7+)
    4. shutil.which("powershell.exe") / shutil.which("powershell")
    5. Fallback to "powershell.exe"
    """
    if sys.platform != "win32":
        return shutil.which("pwsh") or shutil.which("powershell") or "powershell"

    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    std_ps = Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if std_ps.is_file():
        return str(std_ps)

    wow_ps = Path(system_root) / "SysWOW64" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if wow_ps.is_file():
        return str(wow_ps)

    for candidate in ["pwsh.exe", "pwsh", "powershell.exe", "powershell"]:
        found = shutil.which(candidate)
        if found and os.path.isfile(found):
            return found

    return "powershell.exe"

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
if ($found.Count -eq 0) {
    Write-Output "[]"
} else {
    $found | ConvertTo-Json -Compress
}
"""

class ScannerWIA:
    def __init__(self, output_dir=INBOX_DIR):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.powershell_exe = get_powershell_exe()

        # Locate wia_scan.ps1 script path robustly
        candidates = [
            RESOURCE_DIR / "wia_scan.ps1",
            BASE_DIR / "wia_scan.ps1",
            BASE_DIR / "_internal" / "wia_scan.ps1",
            Path(__file__).resolve().parent / "wia_scan.ps1"
        ]
        self.script_path = candidates[0]
        for c in candidates:
            if c.is_file():
                self.script_path = c
                break

    def list_devices(self) -> list:
        if sys.platform != "win32":
            return []
        try:
            cmd = [self.powershell_exe, "-NoProfile", "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass", "-Command", PS_CHECK_SCANNER]
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
            logger.error("Error listing WIA devices using %s: %s", self.powershell_exe, str(e))
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
                self.powershell_exe,
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

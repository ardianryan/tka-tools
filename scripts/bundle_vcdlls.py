import shutil
from pathlib import Path

def copy_vc_runtimes(target_dir: Path):
    sys32 = Path(r"C:\Windows\System32")
    dlls = [
        "msvcp140.dll",
        "msvcp140_1.dll",
        "msvcp140_2.dll",
        "msvcp140_atomic_wait.dll",
        "msvcp140_codecvt_ids.dll",
        "vcruntime140.dll",
        "vcruntime140_1.dll",
        "vcruntime140_threads.dll"
    ]
    target_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for dll in dlls:
        src = sys32 / dll
        if src.exists():
            dst = target_dir / dll
            shutil.copy2(src, dst)
            count += 1
            print(f"[+] Bundled: {dll} -> {target_dir.name}")
    print(f"Total VC++ runtime DLLs bundled: {count}")

if __name__ == "__main__":
    internal_dir = Path("dist/SmartTKAScanner/_internal")
    app_root = Path("dist/SmartTKAScanner")
    if internal_dir.exists():
        copy_vc_runtimes(internal_dir)
    if app_root.exists():
        copy_vc_runtimes(app_root)

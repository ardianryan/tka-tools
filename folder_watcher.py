import time
import threading
import logging
from pathlib import Path
from config import INBOX_DIR

logger = logging.getLogger("FolderWatcher")

class FolderWatcher(threading.Thread):
    """
    Pemantau folder inbox pintar dengan sistem Batch Settling (Debounce).
    Tidak memproses berkas satu per satu saat scanner ADF masih aktif menarik kertas.
    Menunggu proses pemindaian seluruh tumpukan halaman selesai (jeda hening 5 detik),
    kemudian memproses seluruh berkas dalam satu batch berurutan.
    """
    def __init__(self, watch_dir=INBOX_DIR, callback=None, batch_callback=None, poll_interval=1.0, settle_delay=5.0):
        super().__init__(daemon=True)
        self.watch_dir = Path(watch_dir)
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        self.callback = callback
        self.batch_callback = batch_callback
        self.poll_interval = poll_interval
        self.settle_delay = settle_delay  # Jeda hening (detik) untuk memastikan scanner telah selesai
        self._running = False
        self._paused = False
        self._processed_files = set()
        
        # State batching
        self._pending_files = {}  # filename -> {"path": Path, "size": int, "seen_time": float, "stable_count": int}
        self._last_folder_activity = 0.0

    def pause(self):
        """Menjeda pemantauan (misal saat scanning aktif dari dashboard)"""
        self._paused = True
        logger.debug("FolderWatcher dijeda sementara.")

    def resume(self):
        """Melanjutkan pemantauan"""
        self._paused = False
        self._last_folder_activity = time.time()
        logger.debug("FolderWatcher dilanjutkan.")

    def mark_processed(self, filename_or_path):
        """Menandai berkas telah diproses agar tidak diproses ulang"""
        name = Path(filename_or_path).name
        self._processed_files.add(name)
        if name in self._pending_files:
            del self._pending_files[name]

    def run(self):
        self._running = True
        logger.info("Watching folder: %s (Batch Settling: %.1f detik)", self.watch_dir, self.settle_delay)
        
        # Inisialisasi: daftarkan berkas yang sudah ada saat startup agar tidak diproses ganda
        for p in self.watch_dir.glob("*.*"):
            if p.suffix.lower() in [".jpg", ".jpeg", ".png", ".pdf", ".tif", ".tiff"]:
                self._processed_files.add(p.name)

        while self._running:
            try:
                if self._paused:
                    time.sleep(self.poll_interval)
                    continue

                now = time.time()
                current_files = list(self.watch_dir.glob("*.*"))
                valid_extensions = [".jpg", ".jpeg", ".png", ".pdf", ".tif", ".tiff"]

                # 1. Pindai berkas baru atau yang bertambah ukuran
                found_new_activity = False
                for p in current_files:
                    if p.suffix.lower() not in valid_extensions:
                        continue
                    if p.name in self._processed_files:
                        continue

                    try:
                        current_size = p.stat().st_size
                    except Exception:
                        continue

                    if current_size == 0:
                        # Berkas baru dibuat / masih 0 byte
                        found_new_activity = True
                        continue

                    if p.name not in self._pending_files:
                        # Berkas baru masuk ke antrean pending batch
                        self._pending_files[p.name] = {
                            "path": p,
                            "size": current_size,
                            "seen_time": now,
                            "stable_count": 0
                        }
                        found_new_activity = True
                        logger.info("Mendeteksi berkas masuk: %s (Menunggu seluruh batch scan selesai...)", p.name)
                    else:
                        prev = self._pending_files[p.name]
                        if prev["size"] != current_size:
                            # Ukuran berkas masih bertambah (sedang ditulis oleh scanner)
                            prev["size"] = current_size
                            prev["seen_time"] = now
                            prev["stable_count"] = 0
                            found_new_activity = True
                        else:
                            prev["stable_count"] += 1

                if found_new_activity:
                    self._last_folder_activity = now

                # 2. Cek apakah seluruh batch pemindaian telah tenang / selesai (Batch Settling)
                if self._pending_files and self._last_folder_activity > 0:
                    quiescent_time = now - self._last_folder_activity
                    # Pastikan seluruh berkas pending stabil (tidak ada perubahan ukuran dalam 2 iterasi)
                    all_stable = all(item["stable_count"] >= 2 for item in self._pending_files.values())

                    if quiescent_time >= self.settle_delay and all_stable:
                        # Scanner telah selesai memindai seluruh halaman!
                        # Urutkan berkas berdasarkan nama (misal Image_0001, 0002...)
                        batch_items = sorted(list(self._pending_files.values()), key=lambda x: x["path"].name)
                        file_paths = [str(item["path"].resolve()) for item in batch_items]
                        
                        logger.info("Batch pemindaian selesai (%d berkas). Memulai analisis OCR & antrean...", len(file_paths))
                        
                        # Tandai seluruh berkas telah diproses
                        for item in batch_items:
                            self._processed_files.add(item["path"].name)
                        self._pending_files.clear()
                        self._last_folder_activity = 0.0

                        # Eksekusi callback batch atau individual
                        if self.batch_callback:
                            self.batch_callback(file_paths)
                        elif self.callback:
                            for fp in file_paths:
                                self.callback(fp)

                time.sleep(self.poll_interval)
            except Exception as e:
                logger.error("Error in folder watcher loop: %s", str(e))
                time.sleep(self.poll_interval)

    def stop(self):
        self._running = False


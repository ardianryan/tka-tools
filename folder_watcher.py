import time
import threading
import logging
from pathlib import Path
from config import INBOX_DIR

logger = logging.getLogger("FolderWatcher")

class FolderWatcher(threading.Thread):
    def __init__(self, watch_dir=INBOX_DIR, callback=None, poll_interval=2.0):
        super().__init__(daemon=True)
        self.watch_dir = Path(watch_dir)
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        self.callback = callback
        self.poll_interval = poll_interval
        self._running = False
        self._processed_files = set()

    def run(self):
        self._running = True
        logger.info("Watching folder: %s", self.watch_dir)
        while self._running:
            try:
                for file_path in self.watch_dir.glob("*.*"):
                    if file_path.suffix.lower() in [".jpg", ".jpeg", ".png", ".pdf", ".tif", ".tiff"]:
                        if file_path.name not in self._processed_files:
                            # Verify file is not still being written
                            try:
                                prev_size = file_path.stat().st_size
                                time.sleep(0.5)
                                curr_size = file_path.stat().st_size
                                if prev_size == curr_size and curr_size > 0:
                                    self._processed_files.add(file_path.name)
                                    if self.callback:
                                        self.callback(str(file_path))
                            except Exception as e:
                                logger.debug("Waiting for file write completion: %s", str(e))
                time.sleep(self.poll_interval)
            except Exception as e:
                logger.error("Error in folder watcher loop: %s", str(e))
                time.sleep(self.poll_interval)

    def stop(self):
        self._running = False

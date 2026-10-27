import csv
import json
import shutil
import time
from pathlib import Path
from datetime import datetime
from config import LOGS_DIR, LOG_CSV_PATH, LOG_JSON_PATH, PROCESSED_DIR

CSV_HEADERS = [
    "Waktu Unggah",
    "Jenis Dokumen",
    "Hari",
    "Sesi",
    "Ruang / Lab",
    "ID Server",
    "Mata Pelajaran",
    "Nama Berkas",
    "Status",
    "Keterangan Portal"
]

def init_log_files():
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    if not LOG_CSV_PATH.exists():
        with open(LOG_CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_HEADERS)

def record_upload(item: dict, status: str = "SUKSES", portal_msg: str = ""):
    init_log_files()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    slot = item.get("matched_slot") or {}
    
    doc_type_label = "Berita Acara (BAP)" if item.get("doc_type") == "BAP" else "Daftar Hadir (DH)"
    hari_val = f"Hari {slot.get('hari', item.get('hari', '-'))}"
    sesi_val = f"Sesi {slot.get('sesi', item.get('sesi', '-'))}"
    ruang_val = slot.get('nm_ruang', item.get('ruang', '-'))
    server_val = slot.get('kd_server', item.get('kd_server', '-'))
    mapel_val = slot.get('keterangan') or slot.get('mp') or item.get('mapel', '-')
    file_name = item.get("file_name", "-")

    row = [
        now_str,
        doc_type_label,
        hari_val,
        sesi_val,
        ruang_val,
        server_val,
        mapel_val,
        file_name,
        status,
        portal_msg
    ]

    # Write CSV audit log
    try:
        with open(LOG_CSV_PATH, "a", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(row)
    except Exception as e:
        print("Error writing CSV log:", e)

    # Write JSONL audit stream
    try:
        record_obj = {
            "timestamp": now_str,
            "doc_type": item.get("doc_type"),
            "doc_label": doc_type_label,
            "hari": hari_val,
            "sesi": sesi_val,
            "ruang": ruang_val,
            "server": server_val,
            "mapel": mapel_val,
            "file_name": file_name,
            "file_path": item.get("file_path"),
            "status": status,
            "portal_msg": portal_msg
        }
        with open(LOG_JSON_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record_obj, ensure_ascii=False) + "\n")
    except Exception as e:
        print("Error writing JSONL log:", e)

    # Archive uploaded file to processed/ directory
    if status == "SUKSES" and item.get("file_path"):
        try:
            src = Path(item["file_path"])
            if src.exists():
                safe_doc = item.get("doc_type", "DOC")
                safe_hari = f"H{slot.get('hari', item.get('hari', 0))}"
                safe_sesi = f"S{slot.get('sesi', item.get('sesi', 0))}"
                safe_lab = f"Lab{item.get('lab_num') or 1}"
                timestamp_compact = datetime.now().strftime("%Y%m%d_%H%M%S")
                dest_name = f"{safe_doc}_{safe_hari}_{safe_sesi}_{safe_lab}_{timestamp_compact}{src.suffix}"
                dest_path = PROCESSED_DIR / dest_name
                shutil.copy2(src, dest_path)
        except Exception as e:
            print("Error archiving to processed folder:", e)

def get_history(limit: int = 200) -> list:
    init_log_files()
    records = []
    if LOG_JSON_PATH.exists():
        try:
            with open(LOG_JSON_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
        except Exception:
            pass
    records.reverse()
    return records[:limit]

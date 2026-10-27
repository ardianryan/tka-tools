import os
import json
import shutil
import asyncio
import logging
import random
import time
import threading
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

from config import (
    RESOURCE_DIR,
    BASE_DIR,
    INBOX_DIR,
    PROCESSED_DIR,
    DUPLICATES_DIR,
    UPLOAD_TEMP_DIR,
    LOG_CSV_PATH,
    TKA_BASE_URL,
    TKA_USERNAME,
    TKA_PASSWORD,
    TKA_KD_UJIAN,
    ALLOWED_EXTENSIONS,
    MAX_CONTENT_LENGTH,
    SERVER_HOST,
    SERVER_PORT,
    APP_VERSION,
    GITHUB_REPO,
)
from tka_client import TKAClient
from ocr_engine import OCREngine
from scanner_wia import ScannerWIA
from folder_watcher import FolderWatcher
from upload_logger import record_upload, get_history
from settings_manager import load_settings, save_settings
from updater import update_checker

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("SmartTKAServer")

app = Flask(
    __name__,
    template_folder=str(RESOURCE_DIR / "templates"),
    static_folder=str(RESOURCE_DIR / "static")
)
CORS(app)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

# Shared State
init_settings = load_settings()
portal_cfg = init_settings.get("portal", {})
tka_client = TKAClient(
    username=portal_cfg.get("username") or TKA_USERNAME,
    password=portal_cfg.get("password") or TKA_PASSWORD,
    base_url=portal_cfg.get("base_url") or TKA_BASE_URL
)
ocr_engine = OCREngine()
scanner = ScannerWIA(output_dir=INBOX_DIR)

# In-memory queue of scanned & parsed documents
queue = []
cached_slots = {
    "bap": [],
    "dh": [],
    "last_sync": None
}

upload_state = {
    "is_running": False,
    "is_paused": False,
    "should_stop": False,
    "total": 0,
    "current_index": 0,
    "current_file": "",
    "current_slot": "",
    "success_count": 0,
    "fail_count": 0,
    "progress_percent": 0.0,
    "delay_min": 3.0,
    "delay_max": 5.0,
    "countdown": 0.0,
    "status_text": "Siap",
    "logs": []
}

def _run_upload_worker(delay_min=3.0, delay_max=5.0):
    global upload_state
    ready_items = [q for q in queue if q["status"] in ["READY", "FAILED"]]
    upload_state["is_running"] = True
    upload_state["is_paused"] = False
    upload_state["should_stop"] = False
    upload_state["total"] = len(ready_items)
    upload_state["current_index"] = 0
    upload_state["success_count"] = 0
    upload_state["fail_count"] = 0
    upload_state["progress_percent"] = 0.0
    upload_state["delay_min"] = delay_min
    upload_state["delay_max"] = delay_max
    upload_state["logs"] = []

    logger.info("Starting background upload queue for %d items (delay: %.1f - %.1fs)", len(ready_items), delay_min, delay_max)

    for idx, item in enumerate(ready_items):
        if upload_state["should_stop"]:
            upload_state["status_text"] = "Proses dibatalkan oleh operator."
            break

        while upload_state["is_paused"]:
            upload_state["status_text"] = "Dijeda sementara (Paused)..."
            time.sleep(0.5)
            if upload_state["should_stop"]:
                break
        if upload_state["should_stop"]:
            break

        upload_state["current_index"] = idx + 1
        upload_state["current_file"] = item["file_name"]
        slot = item.get("matched_slot", {})
        slot_desc = f"Hari {slot.get('hari')} Sesi {slot.get('sesi')} ({slot.get('nm_ruang')})"
        upload_state["current_slot"] = slot_desc
        upload_state["status_text"] = f"Mengunggah berkas {idx + 1} dari {upload_state['total']}: {item['file_name']}..."
        
        try:
            file_path = item["file_path"]
            doc_type = item["doc_type"]
            if doc_type == "BAP":
                res = tka_client.upload_pelaksanaan(slot, file_path)
            else:
                res = tka_client.upload_absen(slot, file_path)

            if res.get("success"):
                item["status"] = "UPLOADED"
                item["upload_msg"] = res.get("msg", "Berhasil diunggah")
                upload_state["success_count"] += 1
                record_upload(item, status="SUKSES", portal_msg=item["upload_msg"])
                upload_state["logs"].insert(0, {
                    "time": time.strftime("%H:%M:%S"),
                    "file": item["file_name"],
                    "status": "SUCCESS",
                    "msg": f"Sukses diunggah ke {slot_desc}"
                })
            else:
                item["status"] = "FAILED"
                item["upload_msg"] = res.get("msg", "Gagal")
                upload_state["fail_count"] += 1
                record_upload(item, status="GAGAL", portal_msg=item["upload_msg"])
                upload_state["logs"].insert(0, {
                    "time": time.strftime("%H:%M:%S"),
                    "file": item["file_name"],
                    "status": "FAIL",
                    "msg": res.get("msg", "Gagal diunggah")
                })
        except Exception as e:
            item["status"] = "FAILED"
            item["upload_msg"] = str(e)
            upload_state["fail_count"] += 1
            record_upload(item, status="ERROR", portal_msg=str(e))
            upload_state["logs"].insert(0, {
                "time": time.strftime("%H:%M:%S"),
                "file": item["file_name"],
                "status": "ERROR",
                "msg": str(e)
            })

        upload_state["progress_percent"] = round(((idx + 1) / upload_state["total"]) * 100, 1)

        # Anti-bot human delay with countdown before next upload
        if idx < len(ready_items) - 1 and not upload_state["should_stop"]:
            delay = random.uniform(delay_min, delay_max)
            steps = int(delay * 10)
            for s in range(steps, 0, -1):
                if upload_state["should_stop"] or upload_state["is_paused"]:
                    break
                upload_state["countdown"] = round(s / 10.0, 1)
                upload_state["status_text"] = f"Jeda anti-bot ({delay:.1f}s): menunggu {upload_state['countdown']}s sebelum berkas berikutnya..."
                time.sleep(0.1)
            upload_state["countdown"] = 0.0

    upload_state["is_running"] = False
    if upload_state["should_stop"]:
        upload_state["status_text"] = "Proses unggah dihentikan."
    else:
        upload_state["status_text"] = f"Selesai! {upload_state['success_count']} berkas berhasil diunggah."
    
    try:
        sync_portal_slots()
    except Exception:
        pass

def sync_portal_slots():
    try:
        bap = tka_client.get_pelaksanaan_slots(TKA_KD_UJIAN)
        dh = tka_client.get_absen_slots(TKA_KD_UJIAN)
        if not bap and not dh:
            raise Exception("Portal mengembalikan data kosong atau gagal dihubungi.")
        cached_slots["bap"] = bap
        cached_slots["dh"] = dh
        cached_slots["last_sync"] = True
        logger.info("Synced portal slots: %d BAP, %d DH", len(bap), len(dh))
        return True, f"Berhasil sinkronisasi {len(bap)} BAP & {len(dh)} Daftar Hadir."
    except Exception as e:
        logger.error("Failed to sync portal slots: %s", str(e))
        return False, str(e)

def find_duplicate_in_queue(doc_type, hari, sesi, lab_num, kd_server, matched_slot, current_file_path, participants=None):
    """
    Mendeteksi berkas rangkap 2 yang identik dalam antrean secara cerdas.
    Mengembalikan berkas utama pertama yang cocok, atau None.
    """
    for item in queue:
        if item.get("file_path") == current_file_path:
            continue
        if item.get("doc_type") != doc_type:
            continue
        
        # 1. Bandingkan Fingerprint Peserta Didik (Siswa)
        # Jika kedua berkas memiliki daftar siswa yang berbeda sama sekali (0 overlap), PASTI BUKAN duplikat!
        if participants and item.get("participants"):
            overlap = set(item.get("participants", [])) & set(participants)
            if len(participants) >= 8 and len(item.get("participants", [])) >= 8 and len(overlap) == 0:
                continue
            # Jika minimal 3 nomor peserta identik, 100% berkas dan ruangan yang sama (Rangkap 2)!
            if len(overlap) >= 3:
                return item

        # 2. Bandingkan slot jadwal yang dicocokkan
        if matched_slot and item.get("matched_slot"):
            s1 = matched_slot
            s2 = item.get("matched_slot")
            if s1.get("id") and s1.get("id") == s2.get("id"):
                return item
            if (str(s1.get("hari", "")) == str(s2.get("hari", "")) and
                str(s1.get("sesi", "")) == str(s2.get("sesi", "")) and
                s1.get("nm_ruang", "") and s1.get("nm_ruang") == s2.get("nm_ruang")):
                return item

        # 3. Bandingkan metadata hasil OCR (Hari, Sesi, dan Ruang)
        # PENTING: Ruang/Lab yang berbeda (misal Lab 1 vs Lab 2) BUKAN duplikat meski servernya sama!
        if lab_num and item.get("lab_num") and item.get("lab_num") != lab_num:
            continue

        if (hari and str(item.get("hari", "")) == str(hari) and
            sesi and str(item.get("sesi", "")) == str(sesi)):
            if lab_num and item.get("lab_num") == lab_num:
                return item
            if not lab_num and not item.get("lab_num") and kd_server and item.get("kd_server") == kd_server:
                return item

    return None

def process_image_file(file_path: str):
    """Parses a new scanned or imported image file and adds it to queue"""
    try:
        # Check if already in queue
        abs_path = str(Path(file_path).resolve())
        for item in queue:
            if item.get("file_path") == abs_path:
                return item

        # Run OCR asynchronously in loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        parsed = loop.run_until_complete(ocr_engine.scan_and_parse_image(abs_path))
        loop.close()

        # Match against portal slots
        doc_type = parsed.get("doc_type", "UNKNOWN")
        slots = cached_slots["bap"] if doc_type == "BAP" else cached_slots["dh"]
        
        matched_slot, score, reason = ocr_engine.match_slot(parsed, slots)
        participants = parsed.get("participants", [])

        # Smart Deduplication (Deteksi Rangkap 2)
        dup_item = find_duplicate_in_queue(
            doc_type=doc_type,
            hari=parsed.get("hari"),
            sesi=parsed.get("sesi"),
            lab_num=parsed.get("lab_num"),
            kd_server=parsed.get("kd_server"),
            matched_slot=matched_slot,
            current_file_path=abs_path,
            participants=participants
        )

        is_duplicate = False
        duplicate_of = None
        status = "READY" if matched_slot and score >= 60 else "NEEDS_REVIEW"

        if dup_item:
            # Evaluasi kualitas metadata antara berkas lama vs berkas baru
            if dup_item.get("sesi") is None and parsed.get("sesi") is not None:
                # Berkas baru lebih lengkap! Jadikan berkas baru READY dan turunkan berkas lama ke DUPLICATE_SKIPPED
                dup_item["status"] = "DUPLICATE_SKIPPED"
                dup_item["is_duplicate"] = True
                dup_item["duplicate_of"] = Path(file_path).name
                dup_item["match_reason"] = f"Rangkap 2 Terdeteksi: Digantikan oleh {Path(file_path).name} yang hasil OCR-nya lebih lengkap."
                is_duplicate = False
                status = "READY" if matched_slot and score >= 60 else "NEEDS_REVIEW"
            else:
                is_duplicate = True
                duplicate_of = dup_item.get("file_name")
                status = "DUPLICATE_SKIPPED"
                reason = f"Rangkap 2 Terdeteksi: Berkas identik dengan {duplicate_of} (Hari {parsed.get('hari') or '-'}, Sesi {parsed.get('sesi') or '-'}, {parsed.get('ruang') or '-'}). Diabaikan otomatis agar tidak terunggah ganda."
                logger.info("Smart Deduplication: %s diabaikan (duplikat rangkap 2 dari %s)", Path(file_path).name, duplicate_of)
                try:
                    dup_dest = DUPLICATES_DIR / f"DUP_{Path(file_path).name}"
                    if not dup_dest.exists():
                        shutil.copy2(file_path, dup_dest)
                except Exception as e:
                    logger.debug("Failed archiving duplicate: %s", str(e))

        queue_item = {
            "id": f"doc_{len(queue) + 1}_{int(Path(file_path).stat().st_mtime)}",
            "file_name": Path(file_path).name,
            "file_path": abs_path,
            "doc_type": doc_type,
            "hari": parsed.get("hari"),
            "sesi": parsed.get("sesi"),
            "ruang": parsed.get("ruang"),
            "lab_num": parsed.get("lab_num"),
            "kd_server": parsed.get("kd_server"),
            "mapel": parsed.get("mapel"),
            "tanggal": parsed.get("tanggal"),
            "participants": participants,
            "matched_slot": matched_slot,
            "match_score": score,
            "match_reason": reason,
            "is_duplicate": is_duplicate,
            "duplicate_of": duplicate_of,
            "status": status,
            "upload_msg": ""
        }
        queue.append(queue_item)
        logger.info("Processed: %s -> %s (Score: %d%%, Status: %s)", Path(file_path).name, doc_type, score, status)
        return queue_item
    except Exception as e:
        logger.error("Error processing %s: %s", file_path, str(e))
        return None

def process_batch_files(file_paths: list) -> list:
    """
    Memproses sekumpulan berkas hasil pemindaian secara sekuensial
    SETELAH seluruh proses scanning berhenti dan berkas tersimpan utuh di inbox.
    """
    if not file_paths:
        return []
    
    # Urutkan berkas secara natural (0001, 0002, ...)
    sorted_paths = sorted(file_paths, key=lambda p: Path(p).name)
    logger.info("Memulai analisis batch OCR & pencocokan untuk %d berkas...", len(sorted_paths))
    
    results = []
    for fp in sorted_paths:
        item = process_image_file(fp)
        if item:
            results.append(item)
            
    logger.info("Batch OCR selesai: %d berkas diproses.", len(results))
    return results

# Start hot-folder watcher dengan batch callback dan settling window
watcher = FolderWatcher(watch_dir=INBOX_DIR, batch_callback=process_batch_files, settle_delay=5.0)
watcher.start()

# Sync slots on startup if credentials are configured
if tka_client.username and tka_client.password:
    try:
        sync_portal_slots()
    except Exception as e:
        logger.debug("Initial portal sync skipped or failed: %s", e)

# Check for application updates in background on startup
try:
    update_checker.start_background_check()
except Exception as e:
    logger.debug("Failed to start background update checker: %s", e)

@app.route("/")
def index():
    return render_template("index.html", app_version=APP_VERSION, github_repo=GITHUB_REPO)

@app.route("/api/app/version")
def api_app_version():
    return jsonify({
        "version": APP_VERSION,
        "repo": GITHUB_REPO,
        "repo_url": f"https://github.com/{GITHUB_REPO}"
    })

@app.route("/api/app/update_check")
def api_app_update_check():
    force = request.args.get("force", "").lower() in ["1", "true", "yes"]
    result = update_checker.check(force=force)
    return jsonify(result)

@app.route("/api/status")
def api_status():
    scanner_stat = scanner.get_scanner_status()
    # Calculate stats
    total_slots = len(cached_slots["bap"])
    bap_uploaded = sum(1 for s in cached_slots["bap"] if s.get("filename") or "check" in s.get("status", "").lower())
    dh_uploaded = sum(1 for s in cached_slots["dh"] if s.get("filename_1") or "check" in s.get("status", "").lower())
    
    return jsonify({
        "scanner": scanner_stat,
        "portal_connected": tka_client.is_authenticated,
        "username": tka_client.username,
        "total_slots": total_slots,
        "bap_uploaded": bap_uploaded,
        "dh_uploaded": dh_uploaded,
        "queue_count": len(queue),
        "ready_to_upload": sum(1 for q in queue if q["status"] in ["READY", "FAILED"]),
        "duplicates_count": sum(1 for q in queue if q.get("status") == "DUPLICATE_SKIPPED"),
        "is_configured": bool(tka_client.username and tka_client.password)
    })

@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        settings = load_settings()
        if "scanner" in data:
            settings["scanner"].update(data["scanner"])
        if "portal" in data:
            settings["portal"].update(data["portal"])
            tka_client.username = settings["portal"]["username"]
            tka_client.password = settings["portal"]["password"]
            tka_client.base_url = settings["portal"]["base_url"]
            tka_client.is_authenticated = False
            if tka_client.username and tka_client.password:
                threading.Thread(target=sync_portal_slots, daemon=True).start()
        if "ocr_rules" in data:
            settings["ocr_rules"].update(data["ocr_rules"])
        if "upload" in data:
            settings["upload"].update(data["upload"])
        save_settings(settings)
        return jsonify({"success": True, "settings": settings})
    else:
        return jsonify({
            "settings": load_settings(),
            "available_scanners": scanner.list_devices()
        })

@app.route("/api/scanner/devices")
def api_scanner_devices():
    return jsonify({"devices": scanner.list_devices()})

@app.route("/api/portal/test", methods=["POST"])
def api_portal_test():
    data = request.get_json(silent=True) or {}
    username = data.get("username") or tka_client.username
    password = data.get("password") or tka_client.password
    base_url = data.get("base_url") or tka_client.base_url
    client = TKAClient(username=username, password=password, base_url=base_url)
    ok = client.login()
    return jsonify({"success": ok, "msg": "Koneksi portal berhasil!" if ok else "Gagal login ke portal. Periksa username dan password."})

@app.route("/api/sync", methods=["POST"])
def api_sync():
    success, msg = sync_portal_slots()
    return jsonify({
        "success": success,
        "msg": msg,
        "bap_count": len(cached_slots["bap"]),
        "dh_count": len(cached_slots["dh"])
    })

@app.route("/api/portal/slots")
def api_portal_slots():
    doc_type = request.args.get("type", "bap").lower()
    slots = cached_slots["bap"] if doc_type == "bap" else cached_slots["dh"]
    return jsonify({"slots": slots})

@app.route("/api/scan", methods=["POST"])
def api_scan():
    data = request.get_json(silent=True) or {}
    source = data.get("source", "ADF") # "ADF" or "Flatbed"
    prefix = data.get("prefix", "EpsonL5290")
    
    # 1. Jeda FolderWatcher agar tidak memproses berkas setengah jalan saat scanner masih berjalan
    watcher.pause()
    try:
        # 2. Jalankan proses pemindaian fisik sampai scanner benar-benar berhenti dan kertas habis
        res = scanner.trigger_scan(source=source, prefix=prefix)
        if res.get("success"):
            scanned_files = res.get("files", [])
            # Tandai berkas yang baru dipindai agar watcher tidak memproses ulang
            for sf in scanned_files:
                watcher.mark_processed(sf)

            # 3. Proses scanning SELESAI TOTAL dan berkas tersimpan di inbox.
            # Sekarang baru jalankan analisis OCR dan pencocokan antrean secara batch!
            processed_items = process_batch_files(scanned_files)
            ready_c = sum(1 for it in processed_items if it.get("status") == "READY")
            dup_c = sum(1 for it in processed_items if it.get("status") == "DUPLICATE_SKIPPED")
            
            return jsonify({
                "success": True,
                "count": len(processed_items),
                "ready_count": ready_c,
                "duplicates_count": dup_c,
                "items": processed_items
            })
        else:
            return jsonify({"success": False, "msg": res.get("msg")}), 400
    finally:
        # 4. Lanjutkan kembali watcher setelah batch selesai
        watcher.resume()

@app.route("/api/upload_local", methods=["POST"])
def api_upload_local():
    if "file" not in request.files:
        return jsonify({"success": False, "msg": "Tidak ada berkas yang diunggah"}), 400
    f = request.files["file"]
    if not f or f.filename == "":
        return jsonify({"success": False, "msg": "Nama berkas kosong"}), 400

    ext = Path(f.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"success": False, "msg": f"Ekstensi {ext} tidak diizinkan. Gunakan JPG/PNG."}), 400

    safe_name = secure_filename(f.filename) or f"upload_{int(time.time())}{ext}"
    dest_path = INBOX_DIR / safe_name
    f.save(str(dest_path))

    item = process_image_file(str(dest_path))
    return jsonify({"success": True, "item": item})

@app.route("/api/import_folder", methods=["POST"])
def api_import_folder():
    data = request.get_json(silent=True) or {}
    folder_path = data.get("folder_path", "DokumenTKA")
    p = (BASE_DIR / folder_path).resolve() if not Path(folder_path).is_absolute() else Path(folder_path).resolve()

    if not p.is_relative_to(BASE_DIR):
        return jsonify({"success": False, "msg": "Akses ditolak: folder di luar direktori kerja."}), 403

    if not p.exists() or not p.is_dir():
        return jsonify({"success": False, "msg": f"Folder {folder_path} tidak ditemukan"}), 404

    found_files = []
    for ext in ["*.jpg", "*.jpeg", "*.png"]:
        found_files.extend(list(p.rglob(ext)))

    results = []
    for f in found_files:
        item = process_image_file(str(f))
        if item:
            results.append(item)

    return jsonify({"success": True, "total_found": len(found_files), "imported": len(results)})

@app.route("/api/queue")
def api_queue():
    return jsonify({"queue": queue})

@app.route("/api/queue/clear", methods=["POST"])
def api_queue_clear():
    global queue
    queue = []
    return jsonify({"success": True})

@app.route("/api/queue/reprocess_all", methods=["POST"])
def api_queue_reprocess_all():
    global queue
    queue = []
    inbox_files = sorted(list(INBOX_DIR.glob("*.jpg")) + list(INBOX_DIR.glob("*.jpeg")) + list(INBOX_DIR.glob("*.png")))
    processed = []
    for f in inbox_files:
        item = process_image_file(str(f))
        if item:
            processed.append(item)
    return jsonify({
        "success": True,
        "total": len(inbox_files),
        "processed": len(processed),
        "ready": sum(1 for q in queue if q["status"] == "READY"),
        "duplicates": sum(1 for q in queue if q["status"] == "DUPLICATE_SKIPPED")
    })


@app.route("/api/queue/update_match", methods=["POST"])
def api_queue_update_match():
    data = request.get_json(silent=True) or {}
    queue_id = data.get("queue_id")
    slot_index = data.get("slot_index")
    
    target_item = next((item for item in queue if item["id"] == queue_id), None)
    if not target_item:
        return jsonify({"success": False, "msg": "Item not found"}), 404
        
    doc_type = target_item["doc_type"]
    slots = cached_slots["bap"] if doc_type == "BAP" else cached_slots["dh"]
    
    if 0 <= slot_index < len(slots):
        target_item["matched_slot"] = slots[slot_index]
        target_item["match_score"] = 100
        target_item["match_reason"] = "Dipilih secara manual oleh operator"
        target_item["status"] = "READY"
        target_item["is_duplicate"] = False
        return jsonify({"success": True, "item": target_item})
    return jsonify({"success": False, "msg": "Invalid slot index"}), 400

@app.route("/api/queue/force_ready", methods=["POST"])
def api_queue_force_ready():
    data = request.get_json(silent=True) or {}
    queue_id = data.get("queue_id")
    target_item = next((item for item in queue if item["id"] == queue_id), None)
    if not target_item:
        return jsonify({"success": False, "msg": "Berkas tidak ditemukan"}), 404
        
    target_item["status"] = "READY"
    target_item["is_duplicate"] = False
    target_item["match_reason"] = (target_item.get("match_reason", "") + " [Diaktifkan manual oleh operator]").strip()
    return jsonify({"success": True, "msg": f"{target_item['file_name']} diaktifkan untuk siap diunggah."})

@app.route("/api/upload_slot", methods=["POST"])
def api_upload_slot():
    data = request.get_json(silent=True) or {}
    queue_id = data.get("queue_id")
    item = next((q for q in queue if q["id"] == queue_id), None)
    if not item:
        return jsonify({"success": False, "msg": "Antrean berkas tidak ditemukan"}), 404
        
    if not item.get("matched_slot"):
        return jsonify({"success": False, "msg": "Berkas belum memiliki jadwal yang cocok"}), 400

    slot = item["matched_slot"]
    file_path = item["file_path"]
    doc_type = item["doc_type"]

    try:
        if doc_type == "BAP":
            res = tka_client.upload_pelaksanaan(slot, file_path)
        elif doc_type == "DH":
            res = tka_client.upload_absen(slot, file_path)
        else:
            return jsonify({"success": False, "msg": f"Tipe dokumen {doc_type} tidak didukung"}), 400

        if res.get("success"):
            item["status"] = "UPLOADED"
            item["upload_msg"] = res.get("msg", "Berhasil diunggah ke portal TKA")
            record_upload(item, status="SUKSES", portal_msg=item["upload_msg"])
            # Refresh slots
            sync_portal_slots()
            return jsonify({"success": True, "msg": item["upload_msg"]})
        else:
            item["status"] = "FAILED"
            item["upload_msg"] = res.get("msg", "Gagal diunggah")
            record_upload(item, status="GAGAL", portal_msg=item["upload_msg"])
            return jsonify({"success": False, "msg": item["upload_msg"]}), 400
    except Exception as e:
        item["status"] = "FAILED"
        item["upload_msg"] = str(e)
        record_upload(item, status="ERROR", portal_msg=str(e))
        return jsonify({"success": False, "msg": str(e)}), 500

@app.route("/api/upload/start", methods=["POST"])
@app.route("/api/upload_all", methods=["POST"])
def api_upload_start():
    if upload_state["is_running"]:
        return jsonify({"success": False, "msg": "Proses antrean unggah sedang berjalan."}), 400

    ready_items = [q for q in queue if q["status"] in ["READY", "FAILED"]]
    if not ready_items:
        return jsonify({"success": False, "msg": "Tidak ada berkas yang berstatus SIAP UNGGAH atau GAGAL untuk diulang."}), 400

    data = request.get_json(silent=True) or {}
    delay_min = float(data.get("delay_min", 3.0))
    delay_max = float(data.get("delay_max", 5.0))
    if delay_min < 1.0:
        delay_min = 1.0
    if delay_max < delay_min:
        delay_max = delay_min + 2.0

    worker_thread = threading.Thread(
        target=_run_upload_worker,
        kwargs={"delay_min": delay_min, "delay_max": delay_max},
        daemon=True
    )
    worker_thread.start()

    return jsonify({
        "success": True,
        "msg": f"Antrean unggah dimulai ({len(ready_items)} berkas, jeda anti-bot {delay_min}s - {delay_max}s)",
        "total": len(ready_items)
    })

@app.route("/api/upload/pause", methods=["POST"])
def api_upload_pause():
    if not upload_state["is_running"]:
        return jsonify({"success": False, "msg": "Tidak ada proses unggah yang sedang berjalan."}), 400
    upload_state["is_paused"] = True
    return jsonify({"success": True, "msg": "Unggahan dijeda."})

@app.route("/api/upload/resume", methods=["POST"])
def api_upload_resume():
    if not upload_state["is_running"]:
        return jsonify({"success": False, "msg": "Tidak ada proses unggah yang sedang berjalan."}), 400
    upload_state["is_paused"] = False
    return jsonify({"success": True, "msg": "Unggahan dilanjutkan."})

@app.route("/api/upload/stop", methods=["POST"])
def api_upload_stop():
    if not upload_state["is_running"]:
        return jsonify({"success": False, "msg": "Tidak ada proses unggah yang sedang berjalan."}), 400
    upload_state["should_stop"] = True
    upload_state["is_paused"] = False
    return jsonify({"success": True, "msg": "Proses unggah dihentikan."})

@app.route("/api/upload/status")
def api_upload_status():
    return jsonify(upload_state)

@app.route("/api/logs/history")
def api_logs_history():
    return jsonify({"history": get_history()})

@app.route("/download/riwayat_csv")
def download_riwayat_csv():
    if LOG_CSV_PATH.exists():
        return send_from_directory(LOG_CSV_PATH.parent, LOG_CSV_PATH.name, as_attachment=True)
    return "Log CSV belum tersedia.", 404

@app.route("/preview/<path:filepath>")
def serve_image(filepath):
    try:
        p = Path(filepath).resolve()
        if not p.is_relative_to(BASE_DIR):
            return "Akses ditolak: di luar direktori kerja.", 403
        if p.suffix.lower() not in ALLOWED_EXTENSIONS:
            return "Format berkas tidak diizinkan.", 400
        if p.exists() and p.is_file():
            return send_from_directory(p.parent, p.name)
        return "Berkas tidak ditemukan.", 404
    except Exception as e:
        return f"Error: {str(e)}", 400

if __name__ == "__main__":
    print("\n=======================================================")
    print("   SMART SCANNER & SMART UPLOAD - PORTAL TKA 2026      ")
    print(f"   Dashboard Aktif di: http://{SERVER_HOST}:{SERVER_PORT}")
    print("=======================================================\n")
    app.run(host=SERVER_HOST, port=SERVER_PORT, debug=False)

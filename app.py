import os
import json
import base64
import shutil
import asyncio
import logging
import random
import time
import threading
import re
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_from_directory, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename

from config import (
    RESOURCE_DIR,
    BASE_DIR,
    USER_DATA_DIR,
    INBOX_DIR,
    PROCESSED_DIR,
    DUPLICATES_DIR,
    UPLOAD_TEMP_DIR,
    LOG_CSV_PATH,
    LOG_JSON_PATH,
    SIGNATURES_DIR,
    STAMPS_DIR,
    GENERATED_DOCS_DIR,
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
from updater import update_checker, in_app_updater
from signature_manager import signature_manager, normalize_name, normalize_nip, extract_lab_number
from stamp_engine import stamp_engine

def find_matching_slot(slots: list, gelombang: int, hari: int, sesi: int, lab_num: int) -> dict:
    """
    Accurately matches a portal slot by Gelombang, Hari, Sesi, and true Lab/Room number.
    Extracts the true lab number from 'nm_ruang' (e.g. '01 - Lab 3' -> Lab 3).
    """
    g_target = int(gelombang or 1)
    h_target = int(hari or 1)
    s_target = int(sesi or 1)
    l_target = int(lab_num or 1)

    # 1. Exact match: gelombang, hari, sesi, lab
    for s in slots:
        g = int(s.get("gelombang") or 1)
        h = int(s.get("hari") or 1)
        ses = int(s.get("sesi") or 1)
        lab = extract_lab_number(s.get("nm_ruang", ""))
        if g == g_target and h == h_target and ses == s_target and lab == l_target:
            return s
            
    # 2. Match hari, sesi, lab (if gelombang is unassigned or single)
    for s in slots:
        h = int(s.get("hari") or 1)
        ses = int(s.get("sesi") or 1)
        lab = extract_lab_number(s.get("nm_ruang", ""))
        if h == h_target and ses == s_target and lab == l_target:
            return s

    # 3. Match hari, sesi
    for s in slots:
        h = int(s.get("hari") or 1)
        ses = int(s.get("sesi") or 1)
        if h == h_target and ses == s_target:
            return s

    return {}

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

sync_lock = threading.Lock()

def sync_portal_slots():
    with sync_lock:
        try:
            # First, check if session is still valid before attempting blind login
            if not tka_client.is_authenticated:
                if tka_client.verify_session():
                    logger.info("Session verified and active for %s", tka_client.username)
                elif tka_client.username and tka_client.password and not tka_client.require_captcha:
                    logger.info("Portal session not authenticated. Attempting auto-login for %s...", tka_client.username)
                    try:
                        tka_client.login()
                    except Exception as auth_err:
                        logger.debug("Auto-login attempt failed: %s", auth_err)

            bap = tka_client.get_pelaksanaan_slots()
            dh = tka_client.get_absen_slots()
            if not bap and not dh:
                if tka_client.require_captcha:
                    raise Exception("Sesi portal kedaluwarsa dan memerlukan kode keamanan (CAPTCHA). Silakan klik [Masuk] di pojok kiri bawah.")
                elif not tka_client.is_authenticated:
                    raise Exception("Sesi portal terputus. Silakan login kembali melalui menu Pengaturan.")
                raise Exception("Portal mengembalikan data kosong atau jadwal belum dibuat di web TKA.")
            cached_slots["bap"] = bap
            cached_slots["dh"] = dh
            cached_slots["last_sync"] = True
            
            # Sync dynamic session assignments & officers
            try:
                bap_dates_map = tka_client.get_bap_dates_map(bap)
                signature_manager.sync_from_portal_slots(bap, dh, bap_dates_map=bap_dates_map)
                ocr_engine.set_date_map(bap_dates_map)
            except Exception as se:
                logger.debug("Failed to sync assignments from slots: %s", se)

            logger.info("Synced portal slots: %d BAP, %d DH", len(bap), len(dh))
            return True, f"Berhasil sinkronisasi {len(bap)} BAP & {len(dh)} Daftar Hadir."
        except Exception as e:
            logger.error("Failed to sync portal slots: %s", str(e))
            return False, str(e)

def find_duplicate_in_queue(doc_type, hari, sesi, lab_num, kd_server, matched_slot, current_file_path, participants=None, gelombang=None):
    """
    Mendeteksi berkas rangkap 2 yang identik dalam antrean secara cerdas.
    Mengembalikan berkas utama pertama yang cocok, atau None.
    Menjamin isolasi antar Gelombang (Gelombang 2 tidak akan dianggap duplikat dari Gelombang 1).
    """
    curr_gel = str(gelombang or (matched_slot.get("gelombang") if matched_slot else 1))

    for item in queue:
        if item.get("file_path") == current_file_path:
            continue
        if item.get("doc_type") != doc_type:
            continue

        # Isolasi ketat antar gelombang: Gelombang 1 dan Gelombang 2 tidak pernah dianggap duplikat
        item_gel = str(item.get("gelombang") or (item.get("matched_slot", {}).get("gelombang") if item.get("matched_slot") else 1))
        if curr_gel != item_gel:
            continue
        
        item_hari = item.get("hari") or (item.get("matched_slot", {}).get("hari") if item.get("matched_slot") else None)
        item_sesi = item.get("sesi") or (item.get("matched_slot", {}).get("sesi") if item.get("matched_slot") else None)
        item_lab = item.get("lab_num") or (item.get("matched_slot", {}).get("lab_num") if item.get("matched_slot") else None)

        # 2. Hari, Sesi, dan Lab harus sama persis untuk dianggap duplikat (Rangkap 2)
        # Jika hari berbeda (misal Hari 1 vs Hari 2), peserta didiknya sama tapi BUKAN duplikat!
        if hari and item_hari and str(hari) != str(item_hari):
            continue
        if sesi and item_sesi and str(sesi) != str(item_sesi):
            continue
        if lab_num and item_lab and int(lab_num) != int(item_lab):
            continue

        # 3. Bandingkan slot jadwal yang dicocokkan
        if matched_slot and item.get("matched_slot"):
            s1 = matched_slot
            s2 = item.get("matched_slot")
            if s1.get("id") and s1.get("id") == s2.get("id"):
                return item
            if (str(s1.get("gelombang", 1)) == str(s2.get("gelombang", 1)) and
                str(s1.get("hari", "")) == str(s2.get("hari", "")) and
                str(s1.get("sesi", "")) == str(s2.get("sesi", "")) and
                str(s1.get("lab_num", "")) == str(s2.get("lab_num", ""))):
                return item

        # 4. Jika sesi & lab sudah cocok (atau belum pasti tapi tidak bertentangan),
        # cek overlap peserta didik:
        if participants and item.get("participants"):
            overlap = set(item.get("participants", [])) & set(participants)
            if len(overlap) >= 3:
                return item

        # 5. Metadata hari, sesi, lab cocok sempurna
        if (hari and str(item_hari) == str(hari) and
            sesi and str(item_sesi) == str(sesi)):
            if lab_num and int(item_lab) == int(lab_num):
                return item
            if not lab_num and not item_lab and kd_server and item.get("kd_server") == kd_server:
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
        detected_gel = parsed.get("detected_gelombang") or parsed.get("gelombang") or (matched_slot.get("gelombang") if matched_slot else 1)
        dup_item = find_duplicate_in_queue(
            doc_type=doc_type,
            hari=parsed.get("hari"),
            sesi=parsed.get("sesi"),
            lab_num=parsed.get("lab_num"),
            kd_server=parsed.get("kd_server"),
            matched_slot=matched_slot,
            current_file_path=abs_path,
            participants=participants,
            gelombang=detected_gel
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
            "gelombang": int(detected_gel),
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

# Sync slots on startup if credentials are configured (in background thread so UI starts immediately)
def _startup_background_sync():
    time.sleep(0.8)
    if tka_client.username and tka_client.password:
        try:
            sync_portal_slots()
        except Exception as e:
            logger.debug("Initial portal sync skipped or failed: %s", e)

threading.Thread(target=_startup_background_sync, daemon=True).start()

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

@app.route("/api/app/update_download", methods=["POST"])
def api_app_update_download():
    data = request.get_json(silent=True) or {}
    url = data.get("download_url")
    version = data.get("version")
    ok, msg = in_app_updater.start_download_and_apply(download_url=url, target_version=version)
    return jsonify({"success": ok, "msg": msg})

@app.route("/api/app/update_status")
def api_app_update_status():
    return jsonify(in_app_updater.get_status())

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
        "require_captcha": tka_client.require_captcha,
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
            old_user = (settings.get("portal", {}).get("username") or "").strip()
            old_pass = (settings.get("portal", {}).get("password") or "").strip()
            old_url = (settings.get("portal", {}).get("base_url") or "").strip()

            settings["portal"].update(data["portal"])
            new_user = (settings["portal"].get("username") or "").strip()
            new_pass = (settings["portal"].get("password") or "").strip()
            new_url = (settings["portal"].get("base_url") or "").strip()

            tka_client.username = new_user
            tka_client.password = new_pass
            tka_client.base_url = new_url
            tka_client._parse_user_kode()

            # ONLY invalidate session if credentials actually changed!
            if old_user != new_user or old_pass != new_pass or old_url != new_url:
                logger.info("Portal credentials changed in settings. Resetting authentication state.")
                tka_client.is_authenticated = False
                tka_client.csrf_token = None
            else:
                # Credentials unchanged: maintain active authenticated session
                if not tka_client.is_authenticated:
                    tka_client.verify_session()

        if "ocr_rules" in data:
            settings["ocr_rules"].update(data["ocr_rules"])
        if "upload" in data:
            settings["upload"].update(data["upload"])
        save_settings(settings)
        return jsonify({
            "success": True,
            "settings": settings,
            "portal_connected": tka_client.is_authenticated
        })
    else:
        return jsonify({
            "settings": load_settings(),
            "available_scanners": scanner.list_devices(),
            "portal_connected": tka_client.is_authenticated,
            "require_captcha": tka_client.require_captcha
        })

@app.route("/api/scanner/devices")
def api_scanner_devices():
    return jsonify({"devices": scanner.list_devices()})

@app.route("/api/portal/captcha")
def api_portal_captcha():
    img_bytes = tka_client.get_captcha_image()
    if img_bytes:
        b64 = base64.b64encode(img_bytes).decode("ascii")
        return jsonify({"success": True, "image": f"data:image/png;base64,{b64}"})
    return jsonify({"success": False, "msg": "Gagal mengambil kode keamanan dari portal."}), 500

@app.route("/api/portal/login", methods=["POST"])
def api_portal_login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or tka_client.username or "").strip()
    password = (data.get("password") or tka_client.password or "").strip()
    base_url = (data.get("base_url") or tka_client.base_url or "").rstrip("/")
    secure = (data.get("secure") or "").strip()

    tka_client.base_url = base_url
    ok = tka_client.login(username=username, password=password, secure=secure)
    if ok:
        settings = load_settings()
        settings["portal"]["username"] = username
        settings["portal"]["password"] = password
        settings["portal"]["base_url"] = base_url
        save_settings(settings)
        tka_client.is_authenticated = True
        tka_client.require_captcha = False
        tka_client.save_session()
        threading.Thread(target=sync_portal_slots, daemon=True).start()
        return jsonify({"success": True, "msg": "Berhasil terhubung ke Portal TKA!"})
    else:
        img_bytes = tka_client.get_captcha_image() if tka_client.require_captcha else b""
        b64 = base64.b64encode(img_bytes).decode("ascii") if img_bytes else ""
        return jsonify({
            "success": False,
            "require_captcha": tka_client.require_captcha,
            "image": f"data:image/png;base64,{b64}" if b64 else "",
            "msg": tka_client.last_login_msg or "Gagal login ke portal."
        })

@app.route("/api/portal/test", methods=["POST"])
def api_portal_test():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or tka_client.username or "").strip()
    password = (data.get("password") or tka_client.password or "").strip()
    base_url = (data.get("base_url") or tka_client.base_url or "").rstrip("/")
    secure = (data.get("secure") or "").strip()

    client = TKAClient(username=username, password=password, base_url=base_url)
    ok = client.login(secure=secure)
    if ok:
        # Also sync current tka_client session
        tka_client.session.cookies.update(client.session.cookies)
        tka_client.csrf_token = client.csrf_token
        tka_client.is_authenticated = True
        tka_client.save_session()
        threading.Thread(target=sync_portal_slots, daemon=True).start()
        return jsonify({"success": True, "msg": "Koneksi portal berhasil!"})
    else:
        img_bytes = client.get_captcha_image() if client.require_captcha else b""
        b64 = base64.b64encode(img_bytes).decode("ascii") if img_bytes else ""
        return jsonify({
            "success": False,
            "require_captcha": client.require_captcha,
            "image": f"data:image/png;base64,{b64}" if b64 else "",
            "msg": client.last_login_msg or "Gagal login ke portal. Periksa username dan password."
        })

@app.route("/api/sync", methods=["POST"])
def api_sync():
    success, msg = sync_portal_slots()
    return jsonify({
        "success": success,
        "msg": msg,
        "require_captcha": tka_client.require_captcha,
        "portal_connected": tka_client.is_authenticated,
        "bap_count": len(cached_slots["bap"]),
        "dh_count": len(cached_slots["dh"])
    })

@app.route("/api/portal/slots")
def api_portal_slots():
    doc_type = request.args.get("type", "bap").lower()
    slots = cached_slots["bap"] if doc_type == "bap" else cached_slots["dh"]
    return jsonify({"slots": slots})

def get_slot_photo_index() -> dict:
    """
    Scans processed/ directory and logs/riwayat_unggah.jsonl to map each slot
    (doc_type, hari, sesi, lab_num) to its actual uploaded file path, thumbnail preview,
    file size, and upload timestamp.
    """
    index = {}
    proc_dir = PROCESSED_DIR
    if proc_dir.exists():
        for p in proc_dir.glob("*.jpg"):
            m = re.match(r'(BAP|DH)_H(\d+)_S(\d+)_Lab(\d+)_', p.name, re.I)
            if m:
                dtype, h, s, lab = m.group(1).upper(), int(m.group(2)), int(m.group(3)), int(m.group(4))
                k = (dtype, h, s, lab)
                if k not in index or p.stat().st_mtime > index[k]["mtime"]:
                    index[k] = {
                        "path": str(p.resolve()),
                        "rel_path": f"processed/{p.name}",
                        "name": p.name,
                        "size_kb": round(p.stat().st_size / 1024, 1),
                        "mtime": p.stat().st_mtime,
                        "timestamp": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                    }

    if LOG_JSON_PATH.exists():
        try:
            with open(LOG_JSON_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        rec = json.loads(line)
                        dtype = (rec.get("doc_type") or "").upper()
                        m_h = re.search(r'(\d+)', str(rec.get("hari", "")))
                        m_s = re.search(r'(\d+)', str(rec.get("sesi", "")))
                        m_lab = re.search(r'(\d+)', str(rec.get("ruang", "")))
                        if dtype and m_h and m_s and m_lab:
                            h = int(m_h.group(1))
                            s = int(m_s.group(1))
                            lab = int(m_lab.group(1))
                            k = (dtype, h, s, lab)
                            fp = rec.get("file_path")
                            if fp and Path(fp).exists():
                                p = Path(fp)
                                rel = p.name
                                try:
                                    rel = str(p.relative_to(BASE_DIR)).replace("\\", "/")
                                except Exception:
                                    rel = str(p).replace("\\", "/")
                                if k not in index or p.stat().st_mtime > index[k]["mtime"]:
                                    index[k] = {
                                        "path": str(p.resolve()),
                                        "rel_path": rel,
                                        "name": rec.get("file_name", p.name),
                                        "size_kb": round(p.stat().st_size / 1024, 1),
                                        "mtime": p.stat().st_mtime,
                                        "timestamp": rec.get("timestamp") or datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                                    }
                    except Exception:
                        pass
        except Exception as e:
            logger.debug("Failed parsing LOG_JSON_PATH: %s", e)

    return index

@app.route("/api/matrix/slots_with_photos")
def api_matrix_slots_with_photos():
    photo_index = get_slot_photo_index()
    
    bap_list = []
    for s in cached_slots.get("bap", []):
        slot_copy = dict(s)
        h = int(s.get("hari") or 1)
        ses = int(s.get("sesi") or 1)
        lab = extract_lab_number(s.get("nm_ruang", ""))
        
        photo = photo_index.get(("BAP", h, ses, lab))
        if photo:
            slot_copy["photo"] = {
                "url": f"/preview/{photo['rel_path']}",
                "name": photo["name"],
                "size_kb": photo["size_kb"],
                "timestamp": photo.get("timestamp", "")
            }
        bap_list.append(slot_copy)
        
    dh_list = []
    for s in cached_slots.get("dh", []):
        slot_copy = dict(s)
        h = int(s.get("hari") or 1)
        ses = int(s.get("sesi") or 1)
        lab = extract_lab_number(s.get("nm_ruang", ""))
        
        photo = photo_index.get(("DH", h, ses, lab))
        if photo:
            slot_copy["photo"] = {
                "url": f"/preview/{photo['rel_path']}",
                "name": photo["name"],
                "size_kb": photo["size_kb"],
                "timestamp": photo.get("timestamp", "")
            }
        dh_list.append(slot_copy)
        
    return jsonify({
        "success": True,
        "bap_slots": bap_list,
        "dh_slots": dh_list
    })

# ==========================================
# E-SIGNATURES & STAMP MASTER ENDPOINTS
# ==========================================
@app.route("/api/signatures")
def api_signatures_get():
    return jsonify({
        "success": True,
        "officers": signature_manager.list_officers(),
        "stamp": signature_manager.get_stamp(),
        "school_profile": signature_manager.get_school_profile()
    })

@app.route("/api/signatures/officer", methods=["POST"])
def api_signatures_officer():
    name = request.form.get("name") or (request.get_json(silent=True) or {}).get("name")
    nip = request.form.get("nip") or (request.get_json(silent=True) or {}).get("nip") or ""
    role = request.form.get("role") or (request.get_json(silent=True) or {}).get("role") or "PENGAWAS"
    
    if not name or not name.strip():
        return jsonify({"success": False, "msg": "Nama petugas wajib diisi."}), 400
        
    image_bytes = None
    if "signature_file" in request.files:
        f = request.files["signature_file"]
        if f and f.filename:
            image_bytes = f.read()
            
    res = signature_manager.add_or_get_officer(name=name, nip=nip, role=role, image_bytes=image_bytes)
    if not res:
        return jsonify({"success": False, "msg": "Gagal menyimpan petugas."}), 400
        
    if res.get("was_skipped"):
        return jsonify({
            "success": True,
            "was_skipped": True,
            "officer": res,
            "msg": f"Nama/NIP '{name}' sudah terdaftar: otomatis menggunakan tanda tangan yang tersimpan (di-skip)."
        })
    else:
        return jsonify({
            "success": True,
            "was_skipped": False,
            "officer": res,
            "msg": f"Petugas '{name}' berhasil disimpan."
        })

@app.route("/api/signatures/delete_officer", methods=["POST"])
def api_signatures_delete_officer():
    data = request.get_json(silent=True) or {}
    off_id = data.get("id")
    if not off_id:
        return jsonify({"success": False, "msg": "ID petugas tidak valid."}), 400
    ok = signature_manager.delete_officer(off_id)
    return jsonify({"success": ok, "msg": "Petugas berhasil dihapus." if ok else "Petugas tidak ditemukan."})

@app.route("/api/signatures/stamp", methods=["POST"])
def api_signatures_stamp():
    image_bytes = None
    if "stamp_file" in request.files:
        f = request.files["stamp_file"]
        if f and f.filename:
            image_bytes = f.read()
            
    options = {}
    for k in ["scale", "opacity", "rotation_deg", "offset_x", "offset_y"]:
        val = request.form.get(k) or (request.get_json(silent=True) or {}).get(k)
        if val is not None:
            options[k] = val
            
    if image_bytes:
        stamp = signature_manager.save_stamp(image_bytes, options)
        return jsonify({"success": True, "stamp": stamp, "msg": "Berkas stempel sekolah berhasil diunggah."})
    else:
        stamp = signature_manager.update_stamp_options(options)
        return jsonify({"success": True, "stamp": stamp, "msg": "Pengaturan stempel berhasil diperbarui."})

@app.route("/api/signatures/school_profile", methods=["POST"])
def api_signatures_school_profile():
    data = request.get_json(silent=True) or request.form.to_dict() or {}
    prof = signature_manager.update_school_profile(data)
    return jsonify({"success": True, "school_profile": prof, "msg": "Profil sekolah berhasil disimpan."})

# ==========================================
# DYNAMIC ASSIGNMENTS ENDPOINTS
# ==========================================
@app.route("/api/assignments")
def api_assignments_get():
    assignments = signature_manager.get_all_assignments()
    if not assignments and cached_slots.get("bap"):
        signature_manager.sync_from_portal_slots(cached_slots["bap"], cached_slots.get("dh"))
        assignments = signature_manager.get_all_assignments()
        
    officers = {o["id"]: o for o in signature_manager.list_officers()}
    stamp = signature_manager.get_stamp()
    
    enriched = []
    for k, a in assignments.items():
        ac = dict(a)
        p_off = officers.get(a.get("proktor_id"))
        pw_off = officers.get(a.get("pengawas_id"))
        ks_off = officers.get(a.get("kepsek_id"))
        
        ac["proktor_name"] = p_off.get("name") if p_off else "-"
        ac["proktor_has_sig"] = p_off.get("has_signature", False) if p_off else False
        ac["pengawas_name"] = pw_off.get("name") if pw_off else "-"
        ac["pengawas_has_sig"] = pw_off.get("has_signature", False) if pw_off else False
        ac["kepsek_name"] = ks_off.get("name") if ks_off else signature_manager.get_school_profile().get("nama_kepsek", "-")
        ac["kepsek_has_sig"] = ks_off.get("has_signature", False) if ks_off else False
        ac["stamp_has_file"] = stamp.get("has_file", False)
        enriched.append(ac)
        
    enriched.sort(key=lambda x: (x.get("gelombang", 1), x.get("hari", 1), x.get("sesi", 1), x.get("lab_num", 1)))
    return jsonify({"success": True, "assignments": enriched})

@app.route("/api/assignments/update", methods=["POST"])
def api_assignments_update():
    data = request.get_json(silent=True) or {}
    gel = data.get("gelombang")
    hari = data.get("hari")
    sesi = data.get("sesi")
    lab = data.get("lab_num")
    if not (gel and hari and sesi and lab):
        return jsonify({"success": False, "msg": "Parameter gelombang/hari/sesi/lab_num tidak lengkap."}), 400
        
    updates = {}
    for k in ["tanggal", "jam", "proktor_id", "pengawas_id", "kepsek_id", "nm_ruang", "kd_server", "mapel"]:
        if k in data:
            updates[k] = data[k]
            
    res = signature_manager.update_assignment(gel, hari, sesi, lab, updates)
    return jsonify({"success": True, "assignment": res, "msg": "Penugasan sesi berhasil diperbarui."})

@app.route("/api/assignments/batch_update", methods=["POST"])
def api_assignments_batch_update():
    data = request.get_json(silent=True) or {}
    filter_criteria = data.get("filter", {})
    updates = data.get("updates", {})
    if not updates:
        return jsonify({"success": False, "msg": "Tidak ada data perubahan yang diberikan."}), 400
        
    count = signature_manager.batch_update_assignments(filter_criteria, updates)
    return jsonify({"success": True, "count": count, "msg": f"Berhasil memperbarui {count} sesi sekaligus."})

@app.route("/api/assignments/sync_portal", methods=["POST"])
def api_assignments_sync_portal():
    sync_portal_slots()
    bap_dates_map = tka_client.get_bap_dates_map(cached_slots["bap"])
    res = signature_manager.sync_from_portal_slots(cached_slots["bap"], cached_slots["dh"], bap_dates_map=bap_dates_map)
    ocr_engine.set_date_map(bap_dates_map)
    return jsonify({
        "success": True,
        "result": res,
        "msg": f"Berhasil sinkronisasi penugasan: {res['total']} sesi dipetakan ({res['new_officers']} petugas baru)."
    })

# ==========================================
# DIGITAL STAMPING & DIRECT UPLOAD/PRINT
# ==========================================
@app.route("/api/document/generate", methods=["POST"])
def api_document_generate():
    data = request.get_json(silent=True) or {}
    doc_type = (data.get("doc_type") or "BAP").upper()
    gel = int(data.get("gelombang") or 1)
    hari = int(data.get("hari") or 1)
    sesi = int(data.get("sesi") or 1)
    lab = int(data.get("lab_num") or 1)
    
    ass = signature_manager.get_assignment(gel, hari, sesi, lab) or {
        "gelombang": gel, "hari": hari, "sesi": sesi, "lab_num": lab
    }
    
    slots = cached_slots["bap"] if doc_type == "BAP" else cached_slots["dh"]
    slot_match = find_matching_slot(slots, gel, hari, sesi, lab)
    
    try:
        if doc_type == "BAP":
            img, file_path = stamp_engine.stamp_bap(slot_match, ass)
        else:
            img, file_path = stamp_engine.stamp_dh(slot_match, ass)
            
        p = Path(file_path)
        rel_url = f"/preview/DokumenTKA/generated/{p.name}"
        
        if data.get("add_to_queue", True):
            q_item = {
                "id": f"gen_{int(time.time()*1000)}",
                "file_path": str(p.resolve()),
                "file_name": p.name,
                "doc_type": doc_type,
                "doc_type_label": "Berita Acara (BAP)" if doc_type == "BAP" else "Daftar Hadir (DH)",
                "hari": hari,
                "sesi": sesi,
                "lab_num": lab,
                "ruang": ass.get("nm_ruang", f"Lab {lab}"),
                "kd_server": ass.get("kd_server", slot_match.get("kd_server", "-")),
                "mapel": ass.get("mapel", slot_match.get("keterangan", "-")),
                "matched_slot": slot_match or {
                    "gelombang": gel, "hari": hari, "sesi": sesi, "nm_ruang": ass.get("nm_ruang", f"Lab {lab}")
                },
                "match_score": 100,
                "match_reason": "Dihasilkan secara digital lengkap dengan TTD & Stempel resmi",
                "status": "READY",
                "upload_msg": "",
                "created_at": time.time()
            }
            for existing in list(queue):
                if existing.get("file_name") == p.name:
                    queue.remove(existing)
            queue.append(q_item)
            
        return jsonify({
            "success": True,
            "file_path": str(p.resolve()),
            "preview_url": rel_url,
            "filename": p.name,
            "msg": f"Dokumen {doc_type} berhasil ditempeli TTD & Stempel resmi!"
        })
    except Exception as e:
        logger.error("Error generating stamped document: %s", e)
        return jsonify({"success": False, "msg": str(e)}), 500

@app.route("/api/document/direct_upload", methods=["POST"])
def api_document_direct_upload():
    data = request.get_json(silent=True) or {}
    doc_type = (data.get("doc_type") or "BAP").upper()
    if doc_type != "BAP":
        return jsonify({
            "success": False,
            "msg": "Injeksi tanda tangan & stempel digital hanya diizinkan untuk Berita Acara (BAP). Daftar Hadir (DH) harus menggunakan dokumen fisik bertanda tangan asli peserta ujian."
        }), 400

    gel = int(data.get("gelombang") or 1)
    hari = int(data.get("hari") or 1)
    sesi = int(data.get("sesi") or 1)
    lab = int(data.get("lab_num") or 1)
    
    ass = signature_manager.get_assignment(gel, hari, sesi, lab) or {
        "gelombang": gel, "hari": hari, "sesi": sesi, "lab_num": lab
    }
    slots = cached_slots["bap"]
    slot_match = find_matching_slot(slots, gel, hari, sesi, lab)
    if not slot_match:
        return jsonify({
            "success": False,
            "msg": f"Jadwal slot pada portal TKA tidak ditemukan untuk Gelombang {gel}, Hari {hari}, Sesi {sesi}, Lab {lab}."
        }), 400
        
    try:
        img, file_path = stamp_engine.stamp_bap(slot_match, ass)
        res = tka_client.upload_pelaksanaan(slot_match, file_path)
            
        if res.get("success"):
            record_upload({
                "doc_type": doc_type,
                "hari": hari,
                "sesi": sesi,
                "lab_num": lab,
                "ruang": ass.get("nm_ruang", f"Lab {lab}"),
                "kd_server": slot_match.get("kd_server", "-"),
                "mapel": slot_match.get("keterangan", "-"),
                "file_name": Path(file_path).name,
                "file_path": file_path,
                "matched_slot": slot_match
            }, status="SUKSES", portal_msg=res.get("msg", "Berhasil diunggah ke portal TKA"))
            
            skip_sync = bool(data.get("skip_sync", False))
            if not skip_sync:
                sync_portal_slots()
            return jsonify({"success": True, "msg": f"Dokumen {doc_type} berhasil diunggah langsung ke portal TKA!"})
        else:
            return jsonify({"success": False, "msg": res.get("msg", "Gagal unggah ke server portal TKA.")}), 400
    except Exception as e:
        logger.error("Direct upload failed: %s", e)
        return jsonify({"success": False, "msg": str(e)}), 500


@app.route("/api/document/batch_direct_upload", methods=["POST"])
def api_document_batch_direct_upload():
    data = request.get_json(silent=True) or {}
    doc_type = (data.get("doc_type") or "BAP").upper()
    if doc_type != "BAP":
        return jsonify({
            "success": False,
            "msg": "Injeksi tanda tangan & stempel digital hanya diizinkan untuk Berita Acara (BAP)."
        }), 400

    target_gel = data.get("gelombang")
    skip_uploaded = bool(data.get("skip_uploaded", False))
    
    all_ass = signature_manager.get_all_assignments()
    officers = {o["id"]: o for o in signature_manager.list_officers()}
    slots = cached_slots["bap"]
    
    ready_items = []
    for k, ass in all_ass.items():
        if target_gel and str(target_gel) != "ALL" and str(ass.get("gelombang")) != str(target_gel):
            continue
            
        p_off = officers.get(ass.get("proktor_id"))
        pw_off = officers.get(ass.get("pengawas_id"))
        proktor_has_sig = p_off.get("has_signature", False) if p_off else False
        pengawas_has_sig = pw_off.get("has_signature", False) if pw_off else False
        
        if not (proktor_has_sig and pengawas_has_sig):
            continue
            
        g = int(ass.get("gelombang") or 1)
        h = int(ass.get("hari") or 1)
        s = int(ass.get("sesi") or 1)
        l = int(ass.get("lab_num") or 1)
        
        slot_match = find_matching_slot(slots, g, h, s, l)
        if not slot_match:
            continue
            
        if skip_uploaded and str(slot_match.get("ada")) == "1":
            continue
            
        ready_items.append({
            "gelombang": g,
            "hari": h,
            "sesi": s,
            "lab_num": l,
            "nm_ruang": ass.get("nm_ruang", f"Lab {l}"),
            "pengawas_name": pw_off.get("name") if pw_off else "-",
            "proktor_name": p_off.get("name") if p_off else "-"
        })
        
    return jsonify({
        "success": True,
        "count": len(ready_items),
        "items": ready_items
    })

@app.route("/document/print/<doc_type>/<int:gelombang>/<int:hari>/<int:sesi>/<int:lab_num>")
def document_print_view(doc_type, gelombang, hari, sesi, lab_num):
    doc_type = doc_type.upper()
    ass = signature_manager.get_assignment(gelombang, hari, sesi, lab_num) or {
        "gelombang": gelombang, "hari": hari, "sesi": sesi, "lab_num": lab_num
    }
    slots = cached_slots["bap"] if doc_type == "BAP" else cached_slots["dh"]
    slot_match = find_matching_slot(slots, gelombang, hari, sesi, lab_num)
    
    try:
        if doc_type == "BAP":
            return stamp_engine.render_bap_html(slot_match, ass, for_print=True, autoprint=True)
        else:
            return stamp_engine.render_dh_html(slot_match, ass, for_print=True, autoprint=True)
    except Exception as e:
        logger.error("Failed preparing print view: %s", e)
        return f"<h3>Gagal menyiapkan cetak: {str(e)}</h3>", 500

@app.route("/document/pdf/<doc_type>/<int:gelombang>/<int:hari>/<int:sesi>/<int:lab_num>")
def document_pdf_view(doc_type, gelombang, hari, sesi, lab_num):
    doc_type = doc_type.upper()
    ass = signature_manager.get_assignment(gelombang, hari, sesi, lab_num) or {
        "gelombang": gelombang, "hari": hari, "sesi": sesi, "lab_num": lab_num
    }
    slots = cached_slots["bap"] if doc_type == "BAP" else cached_slots["dh"]
    slot_match = find_matching_slot(slots, gelombang, hari, sesi, lab_num)

    try:
        pdf_path = stamp_engine.render_pdf(doc_type, slot_match, ass)
        if pdf_path and pdf_path.exists():
            return send_file(pdf_path, as_attachment=False, mimetype="application/pdf")
        return "<h3>PDF tidak dapat dihasilkan</h3>", 500
    except Exception as e:
        logger.error("Failed generating PDF: %s", e)
        return f"<h3>Gagal membuat PDF: {str(e)}</h3>", 500

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

def is_safe_inbox_file(file_path: str) -> bool:
    """Security check: ensures path is strictly inside INBOX_DIR and is a regular file"""
    try:
        p = Path(file_path).resolve()
        return p.is_relative_to(INBOX_DIR.resolve()) and p.is_file()
    except Exception:
        return False

@app.route("/api/queue")
def api_queue():
    return jsonify({"queue": queue})

@app.route("/api/queue/clear", methods=["POST"])
def api_queue_clear():
    global queue
    data = request.get_json(silent=True) or {}
    delete_mode = data.get("delete_files", "none") # "uploaded_only", "all", "none"
    
    deleted_count = 0
    if delete_mode == "uploaded_only":
        new_queue = []
        for item in queue:
            if item.get("status") == "UPLOADED":
                fp = item.get("file_path")
                if fp and is_safe_inbox_file(fp):
                    try:
                        Path(fp).unlink(missing_ok=True)
                        deleted_count += 1
                        logger.info("Physical scan file deleted (Uploaded): %s", Path(fp).name)
                    except Exception as e:
                        logger.error("Failed to delete %s: %s", fp, e)
            else:
                new_queue.append(item)
        queue = new_queue
        msg = f"Berhasil menghapus {deleted_count} berkas scan yang sudah terunggah dari folder inbox."
    elif delete_mode == "all":
        for item in queue:
            fp = item.get("file_path")
            if fp and is_safe_inbox_file(fp):
                try:
                    Path(fp).unlink(missing_ok=True)
                    deleted_count += 1
                    logger.info("Physical scan file deleted (All): %s", Path(fp).name)
                except Exception as e:
                    logger.error("Failed to delete %s: %s", fp, e)
        # Also clean any loose scanned images directly in INBOX_DIR
        for ext in ["*.jpg", "*.jpeg", "*.png"]:
            for fp in INBOX_DIR.glob(ext):
                if fp.is_file() and fp.name != ".gitkeep":
                    try:
                        fp.unlink(missing_ok=True)
                        deleted_count += 1
                    except Exception:
                        pass
        queue = []
        msg = f"Seluruh berkas scan di folder inbox ({deleted_count} berkas) telah dihapus dan antrean dikosongkan."
    else: # "none"
        queue = []
        msg = "Antrean di layar berhasil dikosongkan (berkas fisik scan tetap tersimpan di folder inbox)."

    return jsonify({
        "success": True,
        "delete_mode": delete_mode,
        "deleted_count": deleted_count,
        "remaining_count": len(queue),
        "msg": msg
    })

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

    if not tka_client.is_authenticated and not tka_client.verify_session():
        return jsonify({
            "success": False,
            "require_captcha": True,
            "msg": "Sesi portal belum terhubung atau memerlukan kode keamanan (CAPTCHA). Silakan periksa status koneksi di pengaturan."
        }), 400

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
        clean_p = filepath.replace("\\", "/").strip("/")
        target_candidates = []
        
        if clean_p.startswith("signatures/") or clean_p.startswith("stamps/"):
            fname = clean_p.split("/", 1)[1]
            target_candidates.extend([
                SIGNATURES_DIR / fname,
                STAMPS_DIR / fname,
                BASE_DIR / "static" / "signatures" / fname,
                BASE_DIR / "static" / "stamps" / fname
            ])
            
        target_candidates.extend([
            (BASE_DIR / clean_p).resolve(),
            (USER_DATA_DIR / clean_p).resolve(),
            Path(filepath).resolve()
        ])
        
        for cand in target_candidates:
            if cand.exists() and cand.is_file():
                if (cand.is_relative_to(BASE_DIR) or cand.is_relative_to(USER_DATA_DIR) or 
                    cand.is_relative_to(SIGNATURES_DIR) or cand.is_relative_to(STAMPS_DIR)):
                    if cand.suffix.lower() in ALLOWED_EXTENSIONS:
                        return send_from_directory(cand.parent, cand.name)
                        
        return "Berkas tidak ditemukan.", 404
    except Exception as e:
        return f"Error: {str(e)}", 400

if __name__ == "__main__":
    print("\n=======================================================")
    print("   SMART SCANNER & SMART UPLOAD - PORTAL TKA 2026      ")
    print(f"   Dashboard Aktif di: http://{SERVER_HOST}:{SERVER_PORT}")
    print("=======================================================\n")
    app.run(host=SERVER_HOST, port=SERVER_PORT, debug=False)

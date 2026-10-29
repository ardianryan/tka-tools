import sys
import os
import re
import asyncio
import logging
from pathlib import Path
from PIL import Image, ImageEnhance
from settings_manager import load_settings

logger = logging.getLogger("OCREngine")

HAS_WINOCR = False
if sys.platform.startswith("win"):
    try:
        import winocr
        HAS_WINOCR = True
    except Exception as e:
        logger.info("winocr not available: %s", str(e))

HAS_PYTESSERACT = False
try:
    import pytesseract
    HAS_PYTESSERACT = True
except Exception:
    pass

HARI_MAP = {
    "senin": 1, "senln": 1, "semn": 1,
    "selasa": 2, "seiasa": 2, "selaza": 2,
    "rabu": 3, "rabv": 3,
    "kamis": 4, "kamls": 4,
    "jumat": 5, "jum'at": 5,
    "sabtu": 6
}

TANGGAL_HARI_MAP = {
    "26": 1,
    "27": 2,
    "28": 3,
    "29": 4,
    "30": 5
}

def clean_ocr_text(text: str) -> str:
    return re.sub(r'[ \t]+', ' ', text)

def get_line_text(l) -> str:
    if isinstance(l, str):
        return l
    if hasattr(l, "text"):
        return getattr(l, "text", "")
    return str(l)

def parse_tka_document(ocr_lines: list, full_text: str, header_lines: list = None, header_text: str = None) -> dict:
    combined_header = " ".join([get_line_text(l) for l in (header_lines or [])]) + " " + (header_text or "")
    text = clean_ocr_text(combined_header + " " + full_text)
    rules = load_settings().get("ocr_rules", {})
    day_name_map = rules.get("day_name_map", HARI_MAP)
    date_day_map = rules.get("date_day_map", TANGGAL_HARI_MAP)
    room_patterns = rules.get("room_regex", [r'Lab\s*([1-9])', r'Ruang\s*([0-9]+)'])
    server_prefix = rules.get("server_prefix", "")

    doc = {
        "doc_type": "UNKNOWN",
        "hari": None,
        "tanggal": None,
        "sesi": None,
        "ruang": None,
        "lab_num": None,
        "kd_server": None,
        "mapel": None,
        "jam": None,
        "participants": [],
        "raw_text": full_text
    }

    # 1. Document Type Detection
    upper_text = text.upper()
    if any(k in upper_text for k in ["BERITA ACARA", "BENITA ACARA", "ACARA PELAKSANAAN"]):
        doc["doc_type"] = "BAP"
    elif any(k in upper_text for k in ["DAFTAR HADIR", "HADIR PESERTA", "DAFTAR NADIR", "NADIR PESERTA"]):
        doc["doc_type"] = "DH"

    # 2. Ruang / Lab Detection
    for r_pat in room_patterns:
        m_lab = re.search(r_pat, text, re.I)
        if m_lab:
            try:
                doc["lab_num"] = int(m_lab.group(1))
            except ValueError:
                doc["lab_num"] = 1
            doc["ruang"] = f"Lab {doc['lab_num']}"
            break
        for line in (header_lines or ocr_lines):
            m = re.search(r_pat, get_line_text(line), re.I)
            if m:
                try:
                    doc["lab_num"] = int(m.group(1))
                except ValueError:
                    doc["lab_num"] = 1
                doc["ruang"] = f"Lab {doc['lab_num']}"
                break
        if doc["lab_num"]:
            break
    if not doc["lab_num"]:
        m_lab_alt = re.search(r'\b\d\s+Lab\s*([1-9])', text, re.I)
        if m_lab_alt:
            doc["lab_num"] = int(m_lab_alt.group(1))
            doc["ruang"] = f"Lab {doc['lab_num']}"

    # 3. Server ID Detection
    if server_prefix:
        m_srv = re.search(rf'({re.escape(server_prefix)}-[A-Z0-9]+)', text)
        if m_srv:
            doc["kd_server"] = m_srv.group(1).strip()
    if not doc["kd_server"]:
        m_srv = re.search(r'([A-Z0-9]{8,10}-[A-Z0-9]+)', text)
        if m_srv:
            doc["kd_server"] = m_srv.group(1).strip()
    # Fallback server deduction based on detected Lab
    if not doc["kd_server"] and server_prefix and doc["lab_num"]:
        if doc["lab_num"] in [1, 2]:
            doc["kd_server"] = f"{server_prefix}-AZ5U"
        elif doc["lab_num"] in [3, 4]:
            doc["kd_server"] = f"{server_prefix}-BC7U"

    # 4. Hari & Tanggal Detection
    for day_name, day_num in day_name_map.items():
        if re.search(rf'\b{day_name}\b', text, re.I):
            doc["hari"] = day_num
            break

    m_tgl = re.search(r'(\d{1,2})\s+(?:Januari|Februari|Maret|April|Mei|Juni|Juli|Agustus|September|Oktober|November|Desember)', text, re.I)
    if m_tgl:
        tgl_day = m_tgl.group(1)
        doc["tanggal"] = m_tgl.group(0)
        if not doc["hari"] and str(tgl_day) in date_day_map:
            doc["hari"] = int(date_day_map[str(tgl_day)])
    elif not doc["hari"]:
        for tgl_k, day_v in date_day_map.items():
            if re.search(rf'\b{tgl_k}\b', text):
                doc["hari"] = int(day_v)
                doc["tanggal"] = f"{tgl_k} (Terdeteksi)"
                break

    # 5. Sesi & Jam Detection
    # Extract Jam Pelaksanaan (pukul HH:MM)
    m_jam = re.search(r'(?:pukul|jam)\s*(\d{1,2})[:.](\d{2})', text, re.I)
    if not m_jam:
        m_jam = re.search(r'(\d{1,2})[:.](\d{2})\s*(?:sampai|s\.d|sd|-)', text, re.I)

    jam_str = None
    sesi_from_jam = None
    if m_jam:
        h = int(m_jam.group(1))
        m = int(m_jam.group(2))
        mins = h * 60 + m
        jam_str = f"{h:02d}:{m:02d}"
        doc["jam"] = jam_str
        # Precise session boundaries based on standard school exam schedules (TKA / ANBK):
        # Sesi 1: 06:30 - 08:45 (390..525 mins, e.g. 07:00, 07:30, 08:00)
        # Sesi 2: 08:46 - 10:45 (526..645 mins, e.g. 09:00, 09:05, 10:00, 10:30)
        # Sesi 3: >= 10:46 (>= 646 mins, e.g. 11:00, 11:10, 12:30, 13:00, 13:30)
        if mins <= 525:
            sesi_from_jam = 1
        elif mins <= 645:
            sesi_from_jam = 2
        else:
            sesi_from_jam = 3

    if doc["doc_type"] == "BAP":
        # Comprehensive BAP Sesi Extraction:
        sesi_table = None

        # 5.A Direct inline table row: "Sesi : 3" or "Sesi. 3" (exclude notes/catatan)
        for line in ocr_lines:
            l_text = get_line_text(line)
            if any(k in l_text.lower() for k in ["pelaksanaan", "catatan", "berjalan"]):
                continue
            m = re.search(r'\bSesi\s*[:.\s\-_·*]+\s*([1-3])\b', l_text, re.I)
            if m:
                sesi_table = int(m.group(1))
                break

        # 5.B Two-column table alignment: value row after ID Server (e.g. U05120005-AZ5U)
        if not sesi_table:
            for i, line in enumerate(ocr_lines):
                l_text = get_line_text(line)
                if re.search(r'[A-Z0-9]{8,10}-[A-Z0-9]+', l_text):
                    for next_l in ocr_lines[i+1:min(len(ocr_lines), i+7)]:
                        nl_text = get_line_text(next_l).strip()
                        if any(k in nl_text.lower() for k in ["pelaksanaan", "catatan", "berjalan"]):
                            continue
                        m_val = re.search(r'^[.:\s\-_·*]*([1-3])(?:\s+|$)', nl_text)
                        if m_val:
                            # Skip if it is participant count (e.g. 20, 25, 30)
                            if re.match(r'^[.:\s]*[1-4][0-9]\b', nl_text):
                                continue
                            sesi_table = int(m_val.group(1))
                            break
                    if sesi_table:
                        break

        # 5.C Proctor Catatan fallback
        sesi_catatan = None
        for line in ocr_lines:
            l_text = get_line_text(line)
            m_cat = re.search(r'Pelaksanaan\s+TKA\s+Sesi\s*([1-3])', l_text, re.I)
            if m_cat:
                sesi_catatan = int(m_cat.group(1))
                break

        # Synthesis & Cross-Corroboration for BAP:
        if sesi_table and sesi_from_jam:
            if sesi_table == sesi_from_jam:
                doc["sesi"] = sesi_table
            else:
                # If table and time conflict, exam start time (e.g. 11:10) is authoritative ground truth
                doc["sesi"] = sesi_from_jam
        elif sesi_from_jam:
            doc["sesi"] = sesi_from_jam
        elif sesi_table:
            doc["sesi"] = sesi_table
        elif sesi_catatan:
            doc["sesi"] = sesi_catatan

    elif doc["doc_type"] == "DH":
        # Comprehensive DH Sesi Extraction:
        # A. Header table column pattern: 0005 followed by 1, 2, or 3
        m_sesi_hdr = re.search(r'\b0005\s+([1-3])\b', combined_header or text)
        if m_sesi_hdr:
            doc["sesi"] = int(m_sesi_hdr.group(1))

        # B. Header row search for SESI
        if not doc["sesi"]:
            search_lines = (header_lines or []) + ocr_lines
            for i, line in enumerate(search_lines):
                l_text = get_line_text(line)
                if "SESI" in l_text.upper():
                    nums = re.findall(r'\b([1-3])\b', l_text)
                    if nums:
                        doc["sesi"] = int(nums[-1])
                        break
                    for next_l in search_lines[i+1:i+6]:
                        nl_text = get_line_text(next_l).strip()
                        if nl_text in ["1", "2", "3"]:
                            doc["sesi"] = int(nl_text)
                            break
                    if doc["sesi"]:
                        break

        # C. Direct Sesi keyword search
        if not doc["sesi"]:
            m_sesi = re.search(r'\bSesi\s*[:\s]*([1-3])\b', text, re.I)
            if m_sesi:
                doc["sesi"] = int(m_sesi.group(1))

        # D. Jam fallback for DH if available
        if not doc["sesi"] and sesi_from_jam:
            doc["sesi"] = sesi_from_jam

        # E. Extract Student Participants Fingerprint & Sesi Range Verification (DH only)
        pats = sorted(list(set(re.findall(r'0005\d{4,5}', full_text))))
        doc["participants"] = pats
        if pats and not doc["sesi"]:
            first_num = re.search(r'0005(\d{4})', pats[0])
            if first_num:
                idx = int(first_num.group(1))
                if 1 <= idx <= 80:
                    doc["sesi"] = 1
                elif 81 <= idx <= 160:
                    doc["sesi"] = 2
                elif 161 <= idx <= 240:
                    doc["sesi"] = 3
    else:
        # Unknown document type fallback
        if sesi_from_jam:
            doc["sesi"] = sesi_from_jam
        else:
            m_sesi = re.search(r'\bSesi\s*[:\s]*([1-3])\b', text, re.I)
            if m_sesi:
                doc["sesi"] = int(m_sesi.group(1))

    # 7. Mapel determination (from Hari or text)
    if "Bahasa Indonesia" in text:
        doc["mapel"] = "Bahasa Indonesia"
    elif "Bahasa Inggris" in text:
        doc["mapel"] = "Bahasa Inggris"
    elif "Matematika" in text:
        doc["mapel"] = "Matematika"
    elif doc["hari"] == 1:
        doc["mapel"] = "Bahasa Indonesia"
    elif doc["hari"] == 2:
        doc["mapel"] = "Bahasa Inggris"
    elif doc["hari"] == 3:
        doc["mapel"] = "Matematika"
    elif doc["hari"] == 4:
        doc["mapel"] = "Mapel Pilihan"

    return doc

class OCREngine:
    def __init__(self, lang="en-US"):
        self.lang = lang

    async def scan_and_parse_image(self, file_path: str) -> dict:
        img = Image.open(file_path)
        w, h = img.size

        # ZONE 1: Enhanced Header Region (Top 30% of document)
        header_crop = img.crop((0, 0, w, int(h * 0.30)))
        enhancer = ImageEnhance.Contrast(header_crop)
        header_enh = enhancer.enhance(2.0)
        enhancer = ImageEnhance.Sharpness(header_enh)
        header_enh = enhancer.enhance(1.5)

        header_lines = []
        header_text = ""
        ocr_lines = []
        full_text = ""

        # 1. Recognize Header with high contrast
        if HAS_WINOCR:
            try:
                r_h = await winocr.recognize_pil(header_enh, lang=self.lang)
                if r_h:
                    header_lines = [line.text for line in getattr(r_h, "lines", [])]
                    header_text = getattr(r_h, "text", "")
            except Exception as e:
                logger.warning("Header WinOCR failed: %s", str(e))

            # 2. Recognize Full Document (for student IDs and body text)
            try:
                r_full = await winocr.recognize_pil(img, lang=self.lang)
                if r_full:
                    ocr_lines = [line.text for line in getattr(r_full, "lines", [])]
                    full_text = getattr(r_full, "text", "")
            except Exception as e:
                logger.warning("Full WinOCR failed: %s", str(e))

        # Pytesseract fallback for non-Windows or if empty
        if not full_text and HAS_PYTESSERACT:
            try:
                loop = asyncio.get_event_loop()
                full_text = await loop.run_in_executor(None, lambda: pytesseract.image_to_string(img))
                ocr_lines = [l.strip() for l in full_text.splitlines() if l.strip()]
            except Exception as e:
                logger.warning("Pytesseract failed: %s", str(e))

        parsed = parse_tka_document(ocr_lines, full_text, header_lines, header_text)
        parsed["file_path"] = str(Path(file_path).resolve())
        parsed["file_name"] = Path(file_path).name
        return parsed


    def match_slot(self, parsed: dict, portal_slots: list) -> tuple:
        """
        Finds best matching slot from the portal rows.
        Returns (best_slot, score, explanation)
        """
        best_slot = None
        best_score = 0
        best_reasons = []

        target_hari = str(parsed.get("hari")) if parsed.get("hari") else None
        target_sesi = str(parsed.get("sesi")) if parsed.get("sesi") else None
        target_lab = parsed.get("lab_num")
        target_server = parsed.get("kd_server")

        for slot in portal_slots:
            score = 0
            reasons = []

            # 1. Hari match (Weight 30)
            if target_hari and str(slot.get("hari")) == target_hari:
                score += 30
                reasons.append(f"Hari {target_hari} cocok")

            # 2. Sesi match (Weight 35)
            if target_sesi and str(slot.get("sesi")) == target_sesi:
                score += 35
                reasons.append(f"Sesi {target_sesi} cocok")

            # 3. Ruang / Lab match (Weight 25)
            slot_ruang = slot.get("nm_ruang", "")
            if target_lab and f"Lab {target_lab}" in slot_ruang:
                score += 25
                reasons.append(f"Lab {target_lab} cocok ({slot_ruang})")

            # 4. Server match (Weight 10)
            if target_server and slot.get("kd_server") == target_server:
                score += 10
                reasons.append(f"Server {target_server} cocok")

            # Gelombang default = 1
            if str(slot.get("gelombang")) == "1":
                score += 5

            if score > best_score:
                best_score = score
                best_slot = slot
                best_reasons = reasons

        explanation = ", ".join(best_reasons) if best_reasons else "Tidak ada kecocokan yang memadai"
        return best_slot, best_score, explanation

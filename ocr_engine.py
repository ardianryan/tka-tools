import sys
import os
import re
import asyncio
import logging
from pathlib import Path
from PIL import Image
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
    "senin": 1,
    "selasa": 2,
    "rabu": 3,
    "kamis": 4,
    "jumat": 5,
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

def parse_tka_document(ocr_lines: list, full_text: str) -> dict:
    text = clean_ocr_text(full_text)
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
        "raw_text": full_text
    }

    # 1. Document Type Detection
    upper_text = text.upper()
    if "BERITA ACARA" in upper_text or "BENITA ACARA" in upper_text or "ACARA PELAKSANAAN" in upper_text:
        doc["doc_type"] = "BAP"
    elif "DAFTAR HADIR" in upper_text or "HADIR PESERTA" in upper_text:
        doc["doc_type"] = "DH"

    # 2. Server ID Detection
    if server_prefix:
        m_srv = re.search(rf'({re.escape(server_prefix)}-[A-Z0-9]+)', text)
        if m_srv:
            doc["kd_server"] = m_srv.group(1).strip()
    if not doc["kd_server"]:
        m_srv = re.search(r'([A-Z0-9]{8,10}-[A-Z0-9]+)', text)
        if m_srv:
            doc["kd_server"] = m_srv.group(1).strip()

    # 3. Ruang / Lab Detection
    for r_pat in room_patterns:
        m_lab = re.search(r_pat, text, re.I)
        if m_lab:
            try:
                doc["lab_num"] = int(m_lab.group(1))
            except ValueError:
                doc["lab_num"] = 1
            doc["ruang"] = f"Lab {doc['lab_num']}"
            break
        for line in ocr_lines:
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

    # 4. Hari & Tanggal Detection
    for day_name, day_num in day_name_map.items():
        if re.search(rf'\b{day_name}\b', text, re.I):
            doc["hari"] = day_num
            break

    # Check date numbers from configured mapping
    m_tgl = re.search(r'(\d{1,2})\s+(?:Januari|Februari|Maret|April|Mei|Juni|Juli|Agustus|September|Oktober|November|Desember)', text, re.I)
    if m_tgl:
        tgl_day = m_tgl.group(1)
        doc["tanggal"] = m_tgl.group(0)
        if not doc["hari"] and str(tgl_day) in date_day_map:
            doc["hari"] = int(date_day_map[str(tgl_day)])
    elif not doc["hari"]:
        # Fallback date check
        for tgl_k, day_v in date_day_map.items():
            if re.search(rf'\b{tgl_k}\b', text):
                doc["hari"] = int(day_v)
                doc["tanggal"] = f"{tgl_k} (Terdeteksi)"
                break

    # 5. Jam / Sesi Detection
    # Jam: 07:00 / 07.00 -> Sesi 1; 10:00 -> Sesi 2; 13:00 -> Sesi 3
    m_jam = re.search(r'(\d{2}[:.]\d{2})\s*(?:sampai|s\.d|sd|-)', text, re.I)
    if m_jam:
        jam_str = m_jam.group(1).replace(".", ":")
        doc["jam"] = jam_str
        if jam_str.startswith("07") or jam_str.startswith("08"):
            doc["sesi"] = 1
        elif jam_str.startswith("10") or jam_str.startswith("11"):
            doc["sesi"] = 2
        elif jam_str.startswith("13") or jam_str.startswith("14"):
            doc["sesi"] = 3

    # Direct Sesi keyword search
    if not doc["sesi"]:
        m_sesi = re.search(r'\bSesi\s*[:\s]*([1-3])\b', text, re.I)
        if m_sesi:
            doc["sesi"] = int(m_sesi.group(1))

    # In BAP, table structure:
    # L10: Sesi, L20: 1
    if not doc["sesi"] and doc["doc_type"] == "BAP":
        for i, line in enumerate(ocr_lines):
            l_text = get_line_text(line)
            if "Sesi" in l_text:
                # look ahead for a solitary number 1, 2, or 3
                for next_l in ocr_lines[i+1:i+15]:
                    nl_text = get_line_text(next_l).strip()
                    if nl_text in ["1", "2", "3"]:
                        doc["sesi"] = int(nl_text)
                        break
                if doc["sesi"]:
                    break

    # In DH, header row often has: "SESI ... 1" or "SESI ... 2"
    if not doc["sesi"] and doc["doc_type"] == "DH":
        for i, line in enumerate(ocr_lines):
            l_text = get_line_text(line)
            if "SESI" in l_text.upper():
                # check if there's digit 1, 2, 3 in same line or next line
                nums = re.findall(r'\b([1-3])\b', l_text)
                if nums:
                    doc["sesi"] = int(nums[-1])
                    break
                for next_l in ocr_lines[i+1:i+8]:
                    nl_text = get_line_text(next_l).strip()
                    if nl_text in ["1", "2", "3"]:
                        doc["sesi"] = int(nl_text)
                        break
                if doc["sesi"]:
                    break

    # 6. Mapel determination (from Hari or text)
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
        ocr_lines = []
        full_text = ""

        # 1. Try Windows Media OCR (fastest on Windows 10/11)
        if HAS_WINOCR:
            try:
                ocr_res = await winocr.recognize_pil(img, lang=self.lang)
                if ocr_res:
                    ocr_lines = [line.text for line in getattr(ocr_res, "lines", [])]
                    full_text = getattr(ocr_res, "text", "")
            except Exception as e:
                logger.warning("WinOCR failed, trying fallback: %s", str(e))

        # 2. Try pytesseract if WinOCR wasn't available or returned empty (Mac/Linux/Windows fallback)
        if not full_text and HAS_PYTESSERACT:
            try:
                loop = asyncio.get_event_loop()
                full_text = await loop.run_in_executor(None, lambda: pytesseract.image_to_string(img))
                ocr_lines = [l.strip() for l in full_text.splitlines() if l.strip()]
            except Exception as e:
                logger.warning("Pytesseract failed: %s", str(e))

        parsed = parse_tka_document(ocr_lines, full_text)
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

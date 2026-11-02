import json
import logging
import re
import shutil
import time
from datetime import datetime
from pathlib import Path
from PIL import Image

from config import USER_DATA_DIR, BASE_DIR, SIGNATURES_DIR, STAMPS_DIR

logger = logging.getLogger("SignatureManager")

PRIMARY_DATA_FILE = USER_DATA_DIR / "signatures_data.json"
BASE_DATA_FILE = BASE_DIR / "signatures_data.json"

TITLE_REGEX = re.compile(
    r'\b(S\.?Pd|S\.?Kom|S\.?T|S\.?Si|S\.?Sos|S\.?Ag|M\.?Pd|M\.?Mpd|M\.?T|M\.?Si|M\.?Kom|Drs|Dra|Dr|H\.|Hj\.)\b',
    re.IGNORECASE
)

def normalize_name(name: str) -> str:
    """Normalizes officer name by removing academic titles, punctuation, and extra whitespace."""
    if not name:
        return ""
    cleaned = TITLE_REGEX.sub('', name)
    cleaned = re.sub(r'[,.\-_/\\()\'"]', ' ', cleaned)
    return " ".join(cleaned.lower().split())

def normalize_nip(nip: str) -> str:
    """Cleans NIP by extracting digits only."""
    if not nip:
        return ""
    digits = re.sub(r'\D', '', str(nip))
    return digits if len(digits) >= 8 else ""

DEFAULT_DATA = {
    "officers": [],
    "stamp": {
        "file_name": "",
        "scale": 1.0,
        "opacity": 0.88,
        "rotation_deg": -3.5,
        "offset_x": -30,
        "offset_y": -15
    },
    "school_profile": {
        "nama_sekolah": "SMAN 1 GEDEG",
        "npsn": "20502721",
        "nama_kepsek": "Li'ati, S.Pd., M.Mpd",
        "nip_kepsek": "137011022007012010",
        "kepsek_signature_id": ""
    },
    "assignments": {}
}

class SignatureManager:
    def __init__(self):
        self.data_file = PRIMARY_DATA_FILE
        self.data = self._load()
        # Seed default kepala sekolah & proktor if empty
        self._ensure_defaults()

    def _ensure_defaults(self):
        """Ensures directories exist and provides initial seed officers if needed."""
        SIGNATURES_DIR.mkdir(parents=True, exist_ok=True)
        STAMPS_DIR.mkdir(parents=True, exist_ok=True)
        
        # If no officers yet, initialize initial school officers based on school data
        if not self.data.get("officers"):
            # Sample default officers from BAP
            self.add_or_get_officer(
                name="Abdurrohim, S.Kom",
                nip="197804222024211001",
                role="PROKTOR"
            )
            self.add_or_get_officer(
                name="Wika Ayu Rohmah",
                nip="9134775676230133",
                role="PENGAWAS"
            )
            kepsek = self.add_or_get_officer(
                name="Li'ati, S.Pd., M.Mpd",
                nip="137011022007012010",
                role="KEPALA_SEKOLAH"
            )
            if kepsek and not self.data["school_profile"].get("kepsek_signature_id"):
                self.data["school_profile"]["kepsek_signature_id"] = kepsek.get("id", "")
                self._save()

    def _load(self) -> dict:
        target = None
        if PRIMARY_DATA_FILE.exists():
            target = PRIMARY_DATA_FILE
        elif BASE_DATA_FILE.exists():
            target = BASE_DATA_FILE
            
        if target:
            try:
                with open(target, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    # Merge with default structure
                    merged = DEFAULT_DATA.copy()
                    merged.update(loaded)
                    return merged
            except Exception as e:
                logger.error("Failed loading signatures data: %s", e)
        return DEFAULT_DATA.copy()

    def _save(self):
        try:
            USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(PRIMARY_DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            
            # Mirror to BASE_DIR if distinct
            try:
                if BASE_DATA_FILE.resolve() != PRIMARY_DATA_FILE.resolve():
                    with open(BASE_DATA_FILE, "w", encoding="utf-8") as f:
                        json.dump(self.data, f, indent=2, ensure_ascii=False)
            except Exception:
                pass
        except Exception as e:
            logger.error("Failed saving signatures data: %s", e)

    # ==========================
    # OFFICERS & DEDUPLICATION
    # ==========================
    def find_officer(self, name: str, nip: str = None):
        """Finds an existing officer by NIP or normalized name."""
        norm_nip = normalize_nip(nip)
        norm_name = normalize_name(name)

        for off in self.data.get("officers", []):
            if norm_nip and normalize_nip(off.get("nip")) == norm_nip:
                return off
            if norm_name and normalize_name(off.get("name")) == norm_name:
                return off
        return None

    def add_or_get_officer(self, name: str, nip: str = "", role: str = "PENGAWAS", image_bytes: bytes = None, filename: str = None) -> dict:
        """
        Adds a new officer or re-uses existing one if Name/NIP already matches.
        If Name/NIP exists and image_bytes is provided, updates signature image.
        Returns dict with officer details and 'was_skipped' flag.
        """
        name = (name or "").strip()
        nip = (nip or "").strip()
        if not name:
            return None

        existing = self.find_officer(name, nip)
        if existing:
            # Update signature image if provided
            if image_bytes:
                sig_fn = f"{existing['id']}.png"
                sig_path = SIGNATURES_DIR / sig_fn
                with open(sig_path, "wb") as f:
                    f.write(image_bytes)
                existing["signature_filename"] = sig_fn
                existing["has_signature"] = True
                self._save()
                return {**existing, "was_skipped": False, "updated": True}
            
            # Re-used existing without upload
            return {**existing, "was_skipped": True}

        # Create new officer
        off_id = f"off_{int(time.time() * 1000)}_{len(self.data.get('officers', [])) + 1}"
        sig_fn = ""
        has_sig = False
        if image_bytes:
            sig_fn = f"{off_id}.png"
            sig_path = SIGNATURES_DIR / sig_fn
            with open(sig_path, "wb") as f:
                f.write(image_bytes)
            has_sig = True

        new_off = {
            "id": off_id,
            "name": name,
            "nip": nip,
            "role": role.upper() if role else "PENGAWAS",
            "signature_filename": sig_fn,
            "has_signature": has_sig,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        self.data.setdefault("officers", []).append(new_off)
        self._save()
        return {**new_off, "was_skipped": False}

    def delete_officer(self, officer_id: str) -> bool:
        officers = self.data.get("officers", [])
        idx = next((i for i, o in enumerate(officers) if o.get("id") == officer_id), None)
        if idx is not None:
            off = officers.pop(idx)
            if off.get("signature_filename"):
                sig_p = SIGNATURES_DIR / off["signature_filename"]
                if sig_p.exists():
                    try:
                        sig_p.unlink()
                    except Exception:
                        pass
            self._save()
            return True
        return False

    def list_officers(self) -> list:
        # Check actual file existence for each signature
        for off in self.data.get("officers", []):
            fn = off.get("signature_filename")
            off["has_signature"] = bool(fn and (SIGNATURES_DIR / fn).exists())
        return self.data.get("officers", [])

    # ==========================
    # SCHOOL STAMP
    # ==========================
    def save_stamp(self, image_bytes: bytes, options: dict = None) -> dict:
        fn = "school_stamp.png"
        stamp_path = STAMPS_DIR / fn
        with open(stamp_path, "wb") as f:
            f.write(image_bytes)
            
        current = self.data.get("stamp", {})
        current["file_name"] = fn
        if options:
            if "scale" in options:
                current["scale"] = float(options["scale"])
            if "opacity" in options:
                current["opacity"] = float(options["opacity"])
            if "rotation_deg" in options:
                current["rotation_deg"] = float(options["rotation_deg"])
            if "offset_x" in options:
                current["offset_x"] = int(options["offset_x"])
            if "offset_y" in options:
                current["offset_y"] = int(options["offset_y"])
                
        self.data["stamp"] = current
        self._save()
        return current

    def update_stamp_options(self, options: dict) -> dict:
        current = self.data.get("stamp", {})
        for k in ["scale", "opacity", "rotation_deg", "offset_x", "offset_y"]:
            if k in options:
                current[k] = type(current.get(k, 1.0))(options[k])
        self.data["stamp"] = current
        self._save()
        return current

    def get_stamp(self) -> dict:
        stamp = self.data.get("stamp", {})
        fn = stamp.get("file_name")
        stamp["has_file"] = bool(fn and (STAMPS_DIR / fn).exists())
        return stamp

    # ==========================
    # SCHOOL PROFILE
    # ==========================
    def update_school_profile(self, profile: dict) -> dict:
        curr = self.data.get("school_profile", {})
        curr.update(profile)
        self.data["school_profile"] = curr
        
        # Ensure Kepsek exists in officers list
        if curr.get("nama_kepsek"):
            kepsek_off = self.add_or_get_officer(
                name=curr["nama_kepsek"],
                nip=curr.get("nip_kepsek", ""),
                role="KEPALA_SEKOLAH"
            )
            if kepsek_off:
                curr["kepsek_signature_id"] = kepsek_off.get("id")
                
        self._save()
        return curr

    def get_school_profile(self) -> dict:
        return self.data.get("school_profile", {})

    # ============================================
    # DYNAMIC ASSIGNMENTS & AUTO-SYNC FROM PORTAL
    # ============================================
    def get_assignment_key(self, gelombang, hari, sesi, lab_num) -> str:
        return f"{gelombang}_{hari}_{sesi}_{lab_num}"

    def get_all_assignments(self) -> dict:
        return self.data.get("assignments", {})

    def get_assignment(self, gelombang, hari, sesi, lab_num) -> dict:
        k = self.get_assignment_key(gelombang, hari, sesi, lab_num)
        return self.data.get("assignments", {}).get(k)

    def update_assignment(self, gelombang, hari, sesi, lab_num, update_dict: dict) -> dict:
        k = self.get_assignment_key(gelombang, hari, sesi, lab_num)
        current = self.data.setdefault("assignments", {}).get(k, {})
        current.update({
            "gelombang": int(gelombang),
            "hari": int(hari),
            "sesi": int(sesi),
            "lab_num": int(lab_num)
        })
        current.update(update_dict)
        self.data["assignments"][k] = current
        self._save()
        return current

    def batch_update_assignments(self, filter_criteria: dict, update_dict: dict) -> int:
        """
        Batch updates multiple sessions.
        filter_criteria can match: gelombang, hari, sesi, lab_num.
        """
        count = 0
        assignments = self.data.setdefault("assignments", {})
        for k, a in assignments.items():
            match = True
            for fk, fv in filter_criteria.items():
                if fv is not None and str(a.get(fk)) != str(fv):
                    match = False
                    break
            if match:
                a.update(update_dict)
                count += 1
        self._save()
        return count

    def sync_from_portal_slots(self, bap_slots: list, dh_slots: list = None) -> dict:
        """
        Automatically pulls session slots, dates, rooms, servers, and officer names
        from the portal BAP/DH slots, populating dynamic assignments and auto-registering officers.
        """
        created_count = 0
        updated_count = 0
        officers_registered = 0

        # Standard default exam dates map
        default_dates = {
            1: "26 Oktober 2026",
            2: "27 Oktober 2026",
            3: "28 Oktober 2026",
            4: "29 Oktober 2026"
        }
        default_times = {
            1: "07:30 - 09:30",
            2: "10:30 - 12:30",
            3: "13:30 - 15:30"
        }

        # Find or use default proktor and kepsek
        default_proktor = next((o for o in self.data.get("officers", []) if o.get("role") == "PROKTOR"), None)
        default_kepsek = next((o for o in self.data.get("officers", []) if o.get("role") == "KEPALA_SEKOLAH"), None)

        slots = bap_slots or []
        for s in slots:
            try:
                gel = int(s.get("gelombang") or 1)
                hari = int(s.get("hari") or 1)
                sesi = int(s.get("sesi") or 1)
                ruang_str = s.get("nm_ruang", "")
                
                # Extract Lab number
                m_lab = re.search(r'(\d+)', ruang_str)
                lab_num = int(m_lab.group(1)) if m_lab else 1
                
                k = self.get_assignment_key(gel, hari, sesi, lab_num)
                existing = self.data.setdefault("assignments", {}).get(k, {})

                # 1. Pull dynamic date and time from portal or fallback
                jam_range = ""
                if s.get("jam_mulai") and s.get("jam_selesai"):
                    jam_range = f"{s['jam_mulai']} - {s['jam_selesai']}"

                tgl = s.get("tgl_pelaksanaan") or s.get("tanggal") or existing.get("tanggal") or default_dates.get(hari, "26 Oktober 2026")
                jam = jam_range or s.get("jam") or existing.get("jam") or default_times.get(sesi, "07:30 - 09:30")
                mapel = s.get("keterangan") or s.get("mp") or existing.get("mapel", "-")
                server = s.get("kd_server") or existing.get("kd_server", "-")

                # 2. Pull Proktor if present in slot (portal uses p2_nama, p2_nip)
                proktor_id = existing.get("proktor_id")
                proktor_nama = s.get("p2_nama") or s.get("nm_proktor")
                proktor_nip = s.get("p2_nip") or s.get("nip_proktor") or ""
                if proktor_nama:
                    p_off = self.add_or_get_officer(
                        name=proktor_nama,
                        nip=proktor_nip,
                        role="PROKTOR"
                    )
                    if p_off:
                        proktor_id = p_off.get("id")
                        if not p_off.get("was_skipped"):
                            officers_registered += 1
                elif not proktor_id and default_proktor:
                    proktor_id = default_proktor.get("id")

                # 3. Pull Pengawas if present in slot (portal uses p3_nama, p3_nip)
                pengawas_id = existing.get("pengawas_id")
                pengawas_nama = s.get("p3_nama") or s.get("nm_pengawas")
                pengawas_nip = s.get("p3_nip") or s.get("nip_pengawas") or ""
                if pengawas_nama:
                    pw_off = self.add_or_get_officer(
                        name=pengawas_nama,
                        nip=pengawas_nip,
                        role="PENGAWAS"
                    )
                    if pw_off:
                        pengawas_id = pw_off.get("id")
                        if not pw_off.get("was_skipped"):
                            officers_registered += 1

                # 4. Pull Kepsek if present (portal uses p1_nama, p1_nip)
                kepsek_id = existing.get("kepsek_id") or (default_kepsek.get("id") if default_kepsek else "")
                kepsek_nama = s.get("p1_nama") or s.get("nm_kepsek")
                kepsek_nip = s.get("p1_nip") or s.get("nip_kepsek") or ""
                if kepsek_nama:
                    ks_off = self.add_or_get_officer(
                        name=kepsek_nama,
                        nip=kepsek_nip,
                        role="KEPALA_SEKOLAH"
                    )
                    if ks_off:
                        kepsek_id = ks_off.get("id")
                        if not self.data.get("school_profile", {}).get("kepsek_signature_id"):
                            self.data["school_profile"]["kepsek_signature_id"] = kepsek_id
                        self.data["school_profile"]["nama_kepsek"] = kepsek_nama
                        if kepsek_nip:
                            self.data["school_profile"]["nip_kepsek"] = kepsek_nip

                assignment_data = {
                    "gelombang": gel,
                    "hari": hari,
                    "sesi": sesi,
                    "lab_num": lab_num,
                    "nm_ruang": ruang_str or f"Lab {lab_num}",
                    "kd_server": server,
                    "mapel": mapel,
                    "tanggal": tgl,
                    "jam": jam,
                    "proktor_id": proktor_id or "",
                    "pengawas_id": pengawas_id or "",
                    "kepsek_id": kepsek_id or "",
                    "portal_filename": s.get("filename") or s.get("filename_1") or "",
                    "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }

                if k in self.data["assignments"]:
                    # Preserve user edits if any, update slot fields
                    self.data["assignments"][k].update(assignment_data)
                    updated_count += 1
                else:
                    self.data["assignments"][k] = assignment_data
                    created_count += 1

            except Exception as e:
                logger.error("Error syncing slot to assignment: %s", e)

        self._save()
        return {
            "created": created_count,
            "updated": updated_count,
            "total": len(self.data.get("assignments", {})),
            "new_officers": officers_registered
        }

signature_manager = SignatureManager()

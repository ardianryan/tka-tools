import base64
import io
import logging
import math
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageEnhance

from config import (
    BASE_DIR, RESOURCE_DIR, USER_DATA_DIR, SIGNATURES_DIR, STAMPS_DIR, GENERATED_DOCS_DIR
)
from signature_manager import signature_manager, extract_lab_number

logger = logging.getLogger("StampEngine")

def find_browser_executable() -> str:
    """Finds installed Microsoft Edge or Google Chrome executable on Windows."""
    candidates = [
        os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)") + r"\Microsoft\Edge\Application\msedge.exe",
        os.environ.get("PROGRAMFILES", r"C:\Program Files") + r"\Microsoft\Edge\Application\msedge.exe",
        os.environ.get("LOCALAPPDATA", "") + r"\Microsoft\Edge\Application\msedge.exe",
        os.environ.get("PROGRAMFILES", r"C:\Program Files") + r"\Google\Chrome\Application\chrome.exe",
        os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)") + r"\Google\Chrome\Application\chrome.exe",
        os.environ.get("LOCALAPPDATA", "") + r"\Google\Chrome\Application\chrome.exe",
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return ""

def make_transparent(img: Image.Image, threshold: int = 225) -> Image.Image:
    """Converts white or near-white background to transparent."""
    img = img.convert("RGBA")
    datas = img.getdata()
    new_data = []
    for item in datas:
        if item[0] > threshold and item[1] > threshold and item[2] > threshold:
            new_data.append((255, 255, 255, 0))
        else:
            new_data.append(item)
    img.putdata(new_data)
    return img

def image_to_base64_data_uri(img: Image.Image) -> str:
    """Converts PIL Image to base64 PNG data URI."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64}"

class StampEngine:
    def __init__(self):
        GENERATED_DOCS_DIR.mkdir(parents=True, exist_ok=True)
        self.browser_exe = find_browser_executable()
        if not self.browser_exe:
            logger.warning("No Edge/Chrome executable found. PDF/screenshot generation will fallback.")

    def _get_tutwuri_b64(self) -> str:
        """Loads tutwuri.jpg as Base64 data URI so it never fails or breaks in headless mode."""
        candidates = [
            BASE_DIR / "static" / "tka_assets" / "tutwuri.jpg",
            Path(__file__).parent / "static" / "tka_assets" / "tutwuri.jpg",
            BASE_DIR / "_internal" / "static" / "tka_assets" / "tutwuri.jpg",
        ]
        for c in candidates:
            if c.exists():
                try:
                    with open(c, "rb") as f:
                        data = base64.b64encode(f.read()).decode("ascii")
                        return f"data:image/jpeg;base64,{data}"
                except Exception:
                    pass
        return "/static/tka_assets/tutwuri.jpg"

    def _prepare_signature_b64(self, sig_path: Path) -> str:
        """Prepares transparent signature image as base64 data URI."""
        if not sig_path or not sig_path.exists():
            if sig_path and (BASE_DIR / "static" / "signatures" / sig_path.name).exists():
                sig_path = BASE_DIR / "static" / "signatures" / sig_path.name
            else:
                return ""
        try:
            sig = Image.open(sig_path).convert("RGBA")
            sig = make_transparent(sig)
            return image_to_base64_data_uri(sig)
        except Exception as e:
            logger.error("Failed loading signature image: %s", e)
            return ""

    def _prepare_stamp_b64(self, stamp_path: Path, scale: float = 1.0, opacity: float = 0.88, rotation: float = -3.5) -> dict:
        """Prepares transparent school stamp as base64 data URI with styling metadata."""
        if not stamp_path or not stamp_path.exists():
            if stamp_path and (BASE_DIR / "static" / "stamps" / stamp_path.name).exists():
                stamp_path = BASE_DIR / "static" / "stamps" / stamp_path.name
            else:
                return {"uri": "", "scale": 1.0, "opacity": 0.88, "rotation": -3.5}
        try:
            stamp = Image.open(stamp_path).convert("RGBA")
            stamp = make_transparent(stamp)
            return {
                "uri": image_to_base64_data_uri(stamp),
                "scale": float(scale or 1.0),
                "opacity": float(opacity or 0.88),
                "rotation": float(rotation or -3.5)
            }
        except Exception as e:
            logger.error("Failed loading stamp image: %s", e)
            return {"uri": "", "scale": 1.0, "opacity": 0.88, "rotation": -3.5}

    def render_bap_html(self, slot_data: dict, assignment: dict = None, for_print: bool = False, autoprint: bool = False) -> str:
        """
        Renders 100% authentic BAP HTML report with injected signatures & stamp.
        """
        template_path = RESOURCE_DIR / "static" / "templates" / "official_bap.html"
        if not template_path.exists():
            template_path = BASE_DIR / "static" / "templates" / "official_bap.html"

        html = template_path.read_text(encoding="utf-8")

        # Resolve asset URLs
        css_file = BASE_DIR / "static" / "tka_assets" / "cetak.min.css"
        tutwuri_file = BASE_DIR / "static" / "tka_assets" / "tutwuri.jpg"

        css_url = css_file.resolve().as_uri() if css_file.exists() else "/static/tka_assets/cetak.min.css"
        tutwuri_url = self._get_tutwuri_b64()

        ass = assignment or {}
        prof = signature_manager.get_school_profile()
        school_name = prof.get("nama_sekolah") or "SMAN 1 GEDEG"

        hari_num = ass.get("hari") or slot_data.get("hari") or 1
        sesi_num = ass.get("sesi") or slot_data.get("sesi") or 1
        tgl_str = ass.get("tanggal") or slot_data.get("tgl_pelaksanaan") or "26 Oktober 2026"
        jam_str = ass.get("jam") or "07:00 - 08:45"
        server_code = ass.get("kd_server") or slot_data.get("kd_server") or "U05120005-AZ5U"
        raw_ruang = ass.get("nm_ruang") or slot_data.get("nm_ruang") or f"Lab {ass.get('lab_num', 1)}"
        lab_num_clean = extract_lab_number(raw_ruang) or ass.get("lab_num") or slot_data.get("lab_num")
        ruang_name = f"Lab {lab_num_clean}" if (lab_num_clean and "lab" in str(raw_ruang).lower()) else str(raw_ruang)

        # Parse date parts
        day_names = {1: "Senin", 2: "Selasa", 3: "Rabu", 4: "Kamis", 5: "Jumat", 6: "Sabtu"}
        nama_hari = day_names.get(int(hari_num), "Senin")

        # Parse tgl_str like "26 Oktober 2026"
        parts = tgl_str.split()
        tanggal_hari = parts[0] if len(parts) > 0 else "26"
        bulan_nama = parts[1] if len(parts) > 1 else "Oktober"
        tahun = parts[2] if len(parts) > 2 else "2026"

        # Split jam_mulai and jam_selesai
        jam_mulai = "07:00"
        jam_selesai = "08:45"
        if "-" in jam_str:
            j_parts = [p.strip() for p in jam_str.split("-")]
            jam_mulai = j_parts[0]
            jam_selesai = j_parts[1]

        # Resolve Officers
        officers = signature_manager.list_officers()
        
        # Proktor
        proktor_off = None
        p_id = ass.get("proktor_id")
        if p_id:
            proktor_off = next((o for o in officers if o["id"] == p_id), None)
        if not proktor_off:
            proktor_off = next((o for o in officers if o.get("role") == "PROKTOR"), None)

        # Pengawas
        pengawas_off = None
        pw_id = ass.get("pengawas_id")
        if pw_id:
            pengawas_off = next((o for o in officers if o["id"] == pw_id), None)
        if not pengawas_off:
            pengawas_off = next((o for o in officers if o.get("role") == "PENGAWAS"), None)

        # Kepala Sekolah
        kepsek_off = None
        ks_id = ass.get("kepsek_id") or prof.get("kepsek_signature_id")
        if ks_id:
            kepsek_off = next((o for o in officers if o["id"] == ks_id), None)
        if not kepsek_off:
            kepsek_off = next((o for o in officers if o.get("role") == "KEPALA_SEKOLAH"), None)

        p_name = proktor_off.get("name") if proktor_off else (ass.get("proktor_name") or "Abdurrohim, S.Kom")
        p_nip = proktor_off.get("nip") if proktor_off else "197804222024211001"
        pw_name = pengawas_off.get("name") if pengawas_off else (ass.get("pengawas_name") or "Wika Ayu Rohmah")
        pw_nip = pengawas_off.get("nip") if pengawas_off else "9134775676230133"
        ks_name = (prof.get("nama_kepsek") or (kepsek_off.get("name") if kepsek_off else None)) or "Li'ati, S.Pd., M.Mpd"
        raw_ks_nip = prof.get("nip_kepsek") or (kepsek_off.get("nip") if kepsek_off else "")
        if not raw_ks_nip or raw_ks_nip == "137011022007012010":
            raw_ks_nip = "197011022007012010"
        ks_nip = raw_ks_nip

        # Prepare Signatures & Stamp
        p_sig_tag = ""
        if proktor_off and proktor_off.get("signature_filename"):
            sig_p = SIGNATURES_DIR / proktor_off["signature_filename"]
            b64 = self._prepare_signature_b64(sig_p)
            if b64:
                p_sig_tag = f'<img src="{b64}" class="sig-img" alt="TTD Proktor">'

        pw_sig_tag = ""
        if pengawas_off and pengawas_off.get("signature_filename"):
            sig_p = SIGNATURES_DIR / pengawas_off["signature_filename"]
            b64 = self._prepare_signature_b64(sig_p)
            if b64:
                pw_sig_tag = f'<img src="{b64}" class="sig-img" alt="TTD Pengawas">'

        ks_sig_tag = ""
        if kepsek_off and kepsek_off.get("signature_filename"):
            sig_p = SIGNATURES_DIR / kepsek_off["signature_filename"]
            b64 = self._prepare_signature_b64(sig_p)
            if b64:
                ks_sig_tag = f'<img src="{b64}" class="sig-img" alt="TTD Kepsek">'

        # School stamp
        stamp_info = signature_manager.get_stamp()
        stamp_tag = ""
        if stamp_info.get("has_file") and stamp_info.get("file_name"):
            stamp_p = STAMPS_DIR / stamp_info["file_name"]
            st_data = self._prepare_stamp_b64(
                stamp_p,
                scale=stamp_info.get("scale", 1.0),
                opacity=stamp_info.get("opacity", 0.88),
                rotation=stamp_info.get("rotation_deg", -3.5)
            )
            if st_data.get("uri"):
                w = int(115 * st_data["scale"])
                h = int(115 * st_data["scale"])
                rot = st_data["rotation"]
                op = st_data["opacity"]
                stamp_tag = f'<img src="{st_data["uri"]}" class="stamp-img" style="width:{w}px;height:{h}px;opacity:{op};transform:rotate({rot}deg);" alt="Cap">'

        def clean_officer_nip(val) -> str:
            if not val:
                return "-"
            s = str(val).strip()
            s = re.sub(r'^(?:NIP\.?|NIP:?)\s*', '', s, flags=re.I).strip()
            return s if s else "-"

        # Replacements
        replacements = {
            "{{ css_url }}": css_url,
            "{{ tutwuri_url }}": tutwuri_url,
            "{{ nama_hari }}": nama_hari,
            "{{ tanggal_hari }}": tanggal_hari,
            "{{ bulan_nama }}": bulan_nama,
            "{{ tahun }}": tahun,
            "{{ nama_sekolah }}": school_name,
            "{{ jam_mulai }}": jam_mulai,
            "{{ jam_selesai }}": jam_selesai,
            "{{ username }}": slot_data.get("username") or os.environ.get("TKA_USERNAME") or "U05120005",
            "{{ kd_server }}": server_code,
            "{{ nm_ruang }}": ruang_name,
            "{{ sesi }}": str(sesi_num),
            "{{ jm_seharusnya }}": str(slot_data.get("jm_client") or slot_data.get("jm_seharusnya") or "20"),
            "{{ jm_hadir }}": str(slot_data.get("jm_hadir") or "20"),
            "{{ jm_tidak_mengerjakan }}": str(slot_data.get("jm_absen") or slot_data.get("jm_tidak_mengerjakan") or "0"),
            "{{ user_tidak_mengerjakan }}": "",
            "{{ catatan_tes }}": slot_data.get("catatan") or "Laancar",
            "{{ proktor_nama }}": p_name or "-",
            "{{ proktor_nip }}": clean_officer_nip(p_nip),
            "{{ proktor_sig_tag }}": p_sig_tag,
            "{{ pengawas_nama }}": pw_name or "-",
            "{{ pengawas_nip }}": clean_officer_nip(pw_nip),
            "{{ pengawas_sig_tag }}": pw_sig_tag,
            "{{ kepsek_nama }}": ks_name or "-",
            "{{ kepsek_nip }}": clean_officer_nip(ks_nip),
            "{{ kepsek_sig_tag }}": ks_sig_tag,
            "{{ stamp_sig_tag }}": stamp_tag
        }

        for k, v in replacements.items():
            html = html.replace(k, str(v))

        if autoprint:
            html = html.replace('</body>', '<script>window.addEventListener("load", () => { setTimeout(() => window.print(), 350); });</script></body>')

        return html

    def render_dh_html(self, slot_data: dict, assignment: dict = None, for_print: bool = False, autoprint: bool = False) -> str:
        """
        Renders 100% authentic Daftar Hadir (DH) HTML report with injected signatures & stamp.
        """
        template_path = RESOURCE_DIR / "static" / "templates" / "official_dh.html"
        if not template_path.exists():
            template_path = BASE_DIR / "static" / "templates" / "official_dh.html"

        html = template_path.read_text(encoding="utf-8")

        css_file = BASE_DIR / "static" / "tka_assets" / "cetak.min.css"
        tutwuri_file = BASE_DIR / "static" / "tka_assets" / "tutwuri.jpg"

        css_url = css_file.resolve().as_uri() if css_file.exists() else "/static/tka_assets/cetak.min.css"
        tutwuri_url = self._get_tutwuri_b64()

        ass = assignment or {}
        prof = signature_manager.get_school_profile()
        school_name = prof.get("nama_sekolah") or "SMAN 1 GEDEG"

        hari_num = ass.get("hari") or slot_data.get("hari") or 1
        sesi_num = ass.get("sesi") or slot_data.get("sesi") or 1
        tgl_str = ass.get("tanggal") or slot_data.get("tgl_pelaksanaan") or "26 Oktober 2026"
        jam_str = ass.get("jam") or "07:00 - 08:45"
        server_code = ass.get("kd_server") or slot_data.get("kd_server") or "U05120005-AZ5U"
        raw_ruang = ass.get("nm_ruang") or slot_data.get("nm_ruang") or f"Lab {ass.get('lab_num', 1)}"
        lab_num_clean = extract_lab_number(raw_ruang) or ass.get("lab_num") or slot_data.get("lab_num")
        ruang_name = f"Lab {lab_num_clean}" if (lab_num_clean and "lab" in str(raw_ruang).lower()) else str(raw_ruang)

        day_names = {1: "Senin", 2: "Selasa", 3: "Rabu", 4: "Kamis", 5: "Jumat", 6: "Sabtu"}
        nama_hari = day_names.get(int(hari_num), "Senin")

        # Resolve Officers
        officers = signature_manager.list_officers()
        
        # Proktor
        proktor_off = None
        p_id = ass.get("proktor_id")
        if p_id:
            proktor_off = next((o for o in officers if o["id"] == p_id), None)
        if not proktor_off:
            proktor_off = next((o for o in officers if o.get("role") == "PROKTOR"), None)

        # Pengawas
        pengawas_off = None
        pw_id = ass.get("pengawas_id")
        if pw_id:
            pengawas_off = next((o for o in officers if o["id"] == pw_id), None)
        if not pengawas_off:
            pengawas_off = next((o for o in officers if o.get("role") == "PENGAWAS"), None)

        p_name = proktor_off.get("name") if proktor_off else (ass.get("proktor_name") or "Abdurrohim, S.Kom")
        p_nip = proktor_off.get("nip") if proktor_off else "197804222024211001"
        pw_name = pengawas_off.get("name") if pengawas_off else (ass.get("pengawas_name") or "Wika Ayu Rohmah")
        pw_nip = pengawas_off.get("nip") if pengawas_off else "9134775676230133"

        # Signatures
        p_sig_tag = ""
        if proktor_off and proktor_off.get("signature_filename"):
            sig_p = SIGNATURES_DIR / proktor_off["signature_filename"]
            b64 = self._prepare_signature_b64(sig_p)
            if b64:
                p_sig_tag = f'<img src="{b64}" class="sig-img" alt="TTD">'

        pw_sig_tag = ""
        if pengawas_off and pengawas_off.get("signature_filename"):
            sig_p = SIGNATURES_DIR / pengawas_off["signature_filename"]
            b64 = self._prepare_signature_b64(sig_p)
            if b64:
                pw_sig_tag = f'<img src="{b64}" class="sig-img" alt="TTD">'

        # Stamp
        stamp_info = signature_manager.get_stamp()
        stamp_tag = ""
        if stamp_info.get("has_file") and stamp_info.get("file_name"):
            stamp_p = STAMPS_DIR / stamp_info["file_name"]
            st_data = self._prepare_stamp_b64(
                stamp_p,
                scale=stamp_info.get("scale", 1.0),
                opacity=stamp_info.get("opacity", 0.88),
                rotation=stamp_info.get("rotation_deg", -3.5)
            )
            if st_data.get("uri"):
                w = int(110 * st_data["scale"])
                h = int(110 * st_data["scale"])
                rot = st_data["rotation"]
                op = st_data["opacity"]
                stamp_tag = f'<img src="{st_data["uri"]}" class="stamp-img" style="width:{w}px;height:{h}px;opacity:{op};transform:rotate({rot}deg);" alt="Cap">'

        # Generate sample participant rows if needed
        rows_html = ""
        for i in range(1, 21):
            rows_html += f"""
            <tr style="height:26px">
                <td align="center">{i}</td>
                <td align="center">U05120005{i:04d}</td>
                <td>PESERTA UJIAN #{i:02d}</td>
                <td align="{'left' if i % 2 != 0 else 'center'}">{i}. .........................</td>
                <td align="center"><span style="width:50px;">-</span></td>
            </tr>"""

        participants_table = f"""
        <table class="it-grid it-cetak" width="100%">
            <tr style="height:30px">
                <th>No.</th>
                <th>Username</th>
                <th>Nama Peserta</th>
                <th>Tanda Tangan</th>
                <th>Keterangan</th>
            </tr>
            {rows_html}
        </table>"""

        replacements = {
            "{{ css_url }}": css_url,
            "{{ tutwuri_url }}": tutwuri_url,
            "{{ nama_kota }}": "KAB. MOJOKERTO",
            "{{ kd_kota }}": "12",
            "{{ nama_sekolah }}": school_name,
            "{{ kd_sek }}": prof.get("npsn", "0005"),
            "{{ kd_server }}": server_code,
            "{{ nm_ruang }}": ruang_name,
            "{{ sesi }}": str(sesi_num),
            "{{ nama_hari }}": nama_hari,
            "{{ tanggal_pelaksanaan }}": tgl_str,
            "{{ jam }}": jam_str,
            "{{ participants_table }}": participants_table,
            "{{ jm_seharusnya }}": str(slot_data.get("jm_client") or "20"),
            "{{ jm_tidak_hadir }}": "0",
            "{{ jm_hadir }}": str(slot_data.get("jm_client") or "20"),
            "{{ proktor_nama }}": p_name,
            "{{ proktor_nip }}": p_nip or "-",
            "{{ proktor_sig_tag }}": p_sig_tag,
            "{{ pengawas_nama }}": pw_name,
            "{{ pengawas_nip }}": pw_nip or "-",
            "{{ pengawas_sig_tag }}": pw_sig_tag,
            "{{ stamp_sig_tag }}": stamp_tag
        }

        for k, v in replacements.items():
            html = html.replace(k, str(v))

        if autoprint:
            html = html.replace('</body>', '<script>window.addEventListener("load", () => { setTimeout(() => window.print(), 350); });</script></body>')

        return html

    def render_pdf(self, doc_type: str, slot_data: dict, assignment: dict = None, output_path: Path = None) -> Path:
        """
        Generates authentic official PDF using Microsoft Edge / Chrome Headless.
        """
        doc_type = doc_type.upper()
        if not output_path:
            gel = assignment.get("gelombang", 1) if assignment else 1
            hari = assignment.get("hari", 1) if assignment else 1
            sesi = assignment.get("sesi", 1) if assignment else 1
            lab = assignment.get("lab_num", 1) if assignment else 1
            output_path = GENERATED_DOCS_DIR / f"{doc_type}_G{gel}_H{hari}_S{sesi}_Lab{lab}.pdf"

        # Generate HTML
        if doc_type == "BAP":
            html_content = self.render_bap_html(slot_data, assignment, for_print=True)
        else:
            html_content = self.render_dh_html(slot_data, assignment, for_print=True)

        temp_html = GENERATED_DOCS_DIR / f"temp_{doc_type}_{os.getpid()}.html"
        temp_html.write_text(html_content, encoding="utf-8")

        if self.browser_exe:
            cmd = [
                self.browser_exe,
                "--headless=new",
                "--disable-gpu",
                "--no-pdf-header-footer",
                f"--print-to-pdf={output_path.resolve()}",
                f"file:///{temp_html.resolve()}"
            ]
            try:
                subprocess.run(cmd, timeout=30, capture_output=True)
            except Exception as e:
                logger.error("Browser headless PDF generation failed: %s", e)
        
        try:
            temp_html.unlink()
        except Exception:
            pass

        return output_path

    def render_jpg(self, doc_type: str, slot_data: dict, assignment: dict = None, output_path: Path = None) -> Path:
        """
        Renders authentic official document as high-resolution JPEG (150-200 DPI A4) ready for TKA portal upload.
        Uses Edge/Chrome headless --print-to-pdf to generate authentic vector A4, then converts via pypdfium2.
        """
        doc_type = doc_type.upper()
        if not output_path:
            gel = assignment.get("gelombang", 1) if assignment else 1
            hari = assignment.get("hari", 1) if assignment else 1
            sesi = assignment.get("sesi", 1) if assignment else 1
            lab = assignment.get("lab_num", 1) if assignment else 1
            output_path = GENERATED_DOCS_DIR / f"{doc_type}_G{gel}_H{hari}_S{sesi}_Lab{lab}.jpg"

        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 1. Generate clean vector A4 PDF first
        pdf_path = self.render_pdf(doc_type, slot_data, assignment)

        # 2. Convert PDF directly to crisp JPEG via pypdfium2
        if pdf_path and pdf_path.exists():
            try:
                import pypdfium2 as pdfium
                pdf = pdfium.PdfDocument(str(pdf_path))
                page = pdf[0]
                # Scale 2.0833 produces exact 150 DPI A4 (1240 x 1754 px), completely clean full-bleed
                pil_img = page.render(scale=2.0833).to_pil()
                pil_img.save(output_path, "JPEG", quality=95)
                logger.info("Successfully converted vector PDF to clean A4 JPEG: %s (size: %s)", output_path, pil_img.size)
                return output_path
            except Exception as e:
                logger.error("pypdfium2 PDF-to-JPEG conversion failed, falling back to browser screenshot: %s", e)

        # Fallback to browser screenshot if PDF conversion fails
        temp_html = GENERATED_DOCS_DIR / f"temp_{doc_type}_{os.getpid()}.html"
        temp_png = GENERATED_DOCS_DIR / f"temp_{doc_type}_{os.getpid()}.png"
        if doc_type == "BAP":
            html_content = self.render_bap_html(slot_data, assignment, for_print=True)
        else:
            html_content = self.render_dh_html(slot_data, assignment, for_print=True)
        temp_html.write_text(html_content, encoding="utf-8")

        if self.browser_exe:
            cmd = [
                self.browser_exe,
                "--headless=new",
                "--disable-gpu",
                "--hide-scrollbars",
                "--window-size=1240,1754",
                f"--screenshot={temp_png.resolve()}",
                f"file:///{temp_html.resolve()}"
            ]
            try:
                subprocess.run(cmd, timeout=30, capture_output=True)
            except Exception as e:
                logger.error("Browser headless screenshot failed: %s", e)

        # Convert temp PNG to clean JPEG
        if temp_png.exists():
            try:
                img = Image.open(temp_png).convert("RGB")
                img.save(output_path, "JPEG", quality=92, dpi=(150, 150))
                temp_png.unlink()
            except Exception as e:
                logger.error("Failed converting screenshot to JPEG: %s", e)

        try:
            temp_html.unlink()
        except Exception:
            pass

        return output_path

    # ==========================================
    # BACKWARD COMPATIBLE STAMP METHODS
    # ==========================================
    def stamp_bap(self, slot_data: dict, assignment: dict = None, output_filename: str = None) -> tuple[Image.Image, str]:
        """Backward compatible stamp_bap method using authentic renderer."""
        gel = assignment.get("gelombang", 1) if assignment else (slot_data.get("gelombang") or 1)
        hari = assignment.get("hari", 1) if assignment else (slot_data.get("hari") or 1)
        sesi = assignment.get("sesi", 1) if assignment else (slot_data.get("sesi") or 1)
        lab = assignment.get("lab_num", 1) if assignment else 1

        fn = output_filename or f"BAP_G{gel}_H{hari}_S{sesi}_Lab{lab}.jpg"
        target_path = GENERATED_DOCS_DIR / fn

        # Render authentic JPG
        self.render_jpg("BAP", slot_data, assignment, target_path)

        if target_path.exists():
            img = Image.open(target_path)
            return img, str(target_path)
        else:
            # Fallback blank image
            img = Image.new("RGB", (1240, 1754), color=(255, 255, 255))
            img.save(target_path, "JPEG", quality=90)
            return img, str(target_path)

    def stamp_dh(self, slot_data: dict, assignment: dict = None, output_filename: str = None) -> tuple[Image.Image, str]:
        """Backward compatible stamp_dh method using authentic renderer."""
        gel = assignment.get("gelombang", 1) if assignment else (slot_data.get("gelombang") or 1)
        hari = assignment.get("hari", 1) if assignment else (slot_data.get("hari") or 1)
        sesi = assignment.get("sesi", 1) if assignment else (slot_data.get("sesi") or 1)
        lab = assignment.get("lab_num", 1) if assignment else 1

        fn = output_filename or f"DH_G{gel}_H{hari}_S{sesi}_Lab{lab}.jpg"
        target_path = GENERATED_DOCS_DIR / fn

        self.render_jpg("DH", slot_data, assignment, target_path)

        if target_path.exists():
            img = Image.open(target_path)
            return img, str(target_path)
        else:
            img = Image.new("RGB", (1240, 1754), color=(255, 255, 255))
            img.save(target_path, "JPEG", quality=90)
            return img, str(target_path)

stamp_engine = StampEngine()

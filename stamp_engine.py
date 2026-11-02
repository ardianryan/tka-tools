import io
import logging
import math
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

from config import (
    BASE_DIR, RESOURCE_DIR, USER_DATA_DIR, SIGNATURES_DIR, STAMPS_DIR, GENERATED_DOCS_DIR
)
from signature_manager import signature_manager

logger = logging.getLogger("StampEngine")

# Standard A4 at 200 DPI
A4_WIDTH = 1654
A4_HEIGHT = 2337

def get_font(size: int, bold: bool = False):
    """Loads Arial or fallback font."""
    font_names = ["arialbd.ttf" if bold else "arial.ttf", "calibrib.ttf" if bold else "calibri.ttf", "tahomabd.ttf" if bold else "tahoma.ttf"]
    for fn in font_names:
        try:
            return ImageFont.truetype(fn, size)
        except Exception:
            pass
    try:
        return ImageFont.load_default()
    except Exception:
        return None

def make_transparent(img: Image.Image, threshold: int = 225) -> Image.Image:
    """Converts white or near-white background to transparent."""
    img = img.convert("RGBA")
    datas = img.getdata()
    new_data = []
    for item in datas:
        # If pixel is close to white (R,G,B all > threshold)
        if item[0] > threshold and item[1] > threshold and item[2] > threshold:
            new_data.append((255, 255, 255, 0))
        else:
            new_data.append(item)
    img.putdata(new_data)
    return img

class StampEngine:
    def __init__(self):
        GENERATED_DOCS_DIR.mkdir(parents=True, exist_ok=True)

    def find_base_template(self, doc_type: str = "BAP") -> Path:
        """Finds candidate base document to use as template."""
        if doc_type.upper() == "BAP":
            candidates = [
                RESOURCE_DIR / "static" / "templates" / "bap_master.jpg",
                BASE_DIR / "static" / "templates" / "bap_master.jpg",
                BASE_DIR / "DokumenTKA" / "BAP" / "Image_20261026_0001.jpg",
                BASE_DIR / "DokumenTKA" / "BAP" / "Image_20261026_0002.jpg",
                *list((BASE_DIR / "DokumenTKA" / "BAP").glob("*.jpg")),
                *list((BASE_DIR / "processed").glob("BAP_*.jpg"))
            ]
        else:
            candidates = [
                RESOURCE_DIR / "static" / "templates" / "dh_master.jpg",
                BASE_DIR / "static" / "templates" / "dh_master.jpg",
                BASE_DIR / "DokumenTKA" / "H1S1" / "DH" / "Image_20261026_0001.jpg",
                *list((BASE_DIR / "DokumenTKA").glob("**/DH/*.jpg")),
                *list((BASE_DIR / "processed").glob("DH_*.jpg"))
            ]

        for c in candidates:
            if c.exists() and c.is_file() and c.stat().st_size > 50000:
                return c
        return None

    def _prepare_signature_image(self, sig_path: Path, max_w: int = 240, max_h: int = 110) -> Image.Image:
        """Loads and prepares signature image with transparency and size bounds."""
        if not sig_path.exists():
            return None
        try:
            sig = Image.open(sig_path).convert("RGBA")
            sig = make_transparent(sig)
            # Maintain aspect ratio
            sig.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
            return sig
        except Exception as e:
            logger.error("Failed loading signature %s: %s", sig_path, e)
            return None

    def _prepare_stamp_image(self, stamp_path: Path, scale: float = 1.0, opacity: float = 0.88, rotation: float = -3.5, target_w: int = 230) -> Image.Image:
        """Loads and prepares school stamp with natural angle and ink opacity."""
        if not stamp_path.exists():
            return None
        try:
            stamp = Image.open(stamp_path).convert("RGBA")
            stamp = make_transparent(stamp)
            
            # Scale
            w = int(target_w * (scale or 1.0))
            h = int(stamp.height * (w / stamp.width))
            stamp = stamp.resize((w, h), Image.Resampling.LANCZOS)

            # Rotate
            if rotation:
                stamp = stamp.rotate(rotation, resample=Image.Resampling.BICUBIC, expand=True)

            # Adjust opacity
            if opacity and opacity < 1.0:
                alpha = stamp.split()[3]
                alpha = ImageEnhance.Brightness(alpha).enhance(opacity)
                stamp.putalpha(alpha)

            return stamp
        except Exception as e:
            logger.error("Failed loading stamp %s: %s", stamp_path, e)
            return None

    def stamp_bap(self, slot_data: dict, assignment: dict = None, output_filename: str = None) -> tuple[Image.Image, str]:
        """
        Overlays dynamic date, school metadata, officer names & NIPs, signatures,
        and official school stamp onto Berita Acara Pelaksanaan (BAP).
        Returns (PIL.Image, full_saved_path).
        """
        base_path = self.find_base_template("BAP")
        if not base_path or not base_path.exists():
            raise FileNotFoundError("Berkas template BAP dasar tidak ditemukan.")

        # Load base image and ensure RGB mode
        img = Image.open(base_path).convert("RGBA")
        draw = ImageDraw.Draw(img)

        f_normal = get_font(22, bold=False)
        f_bold = get_font(23, bold=True)
        f_title = get_font(25, bold=True)
        f_small = get_font(20, bold=False)

        # 1. Clean & Whiten dynamic areas
        # A. Header date and school line: Y=265 to Y=345
        draw.rectangle([(55, 265), (1550, 345)], fill=(255, 255, 255, 255))
        # B. Metadata table (Ruang, Server, Sesi, Mapel): Y=460 to Y=550
        draw.rectangle([(530, 460), (1450, 550)], fill=(255, 255, 255, 255))
        # C. Officer Names & NIPs: Y=1280 to Y=1615, X=430 to X=860
        draw.rectangle([(430, 1280), (860, 1615)], fill=(255, 255, 255, 255))
        # D. TTD signature boxes: Y=1270 to Y=1615, X=870 to X=1550
        draw.rectangle([(870, 1270), (1550, 1615)], fill=(255, 255, 255, 255))

        # Re-draw clean table horizontal lines between rows
        draw.line([(55, 1395), (1550, 1395)], fill=(20, 20, 20, 255), width=2)
        draw.line([(55, 1505), (1550, 1505)], fill=(20, 20, 20, 255), width=2)
        draw.line([(55, 1615), (1550, 1615)], fill=(20, 20, 20, 255), width=2)

        # 2. Extract dynamic values
        ass = assignment or {}
        school_prof = signature_manager.get_school_profile()
        school_name = school_prof.get("nama_sekolah", "SMAN 1 GEDEG")
        
        hari_num = ass.get("hari") or slot_data.get("hari") or 1
        sesi_num = ass.get("sesi") or slot_data.get("sesi") or 1
        tgl_str = ass.get("tanggal") or slot_data.get("tgl_pelaksanaan") or "26 Oktober 2026"
        jam_str = ass.get("jam") or "07:30 sampai dengan pukul 09:30"
        server_code = ass.get("kd_server") or slot_data.get("kd_server") or "U05120005-AZ5U"
        ruang_name = ass.get("nm_ruang") or slot_data.get("nm_ruang") or f"Lab {ass.get('lab_num', 1)}"

        day_names = {1: "Senin", 2: "Selasa", 3: "Rabu", 4: "Kamis", 5: "Jumat", 6: "Sabtu"}
        day_str = day_names.get(int(hari_num), "Senin")

        # 3. Write dynamic header lines
        line1 = f"Pada hari ini {day_str} tanggal {tgl_str}, di {school_name} telah diselenggarakan TES KEMAMPUAN"
        line2 = f"AKADEMIK SMA/MA, dari pukul {jam_str}"
        draw.text((62, 272), line1, fill=(10, 10, 10, 255), font=f_normal)
        draw.text((62, 310), line2, fill=(10, 10, 10, 255), font=f_normal)

        # Write dynamic Server & Ruang & Sesi
        draw.text((534, 473), f"{server_code} Ruang : {ruang_name}", fill=(10, 10, 10, 255), font=f_normal)
        draw.text((534, 528), str(sesi_num), fill=(10, 10, 10, 255), font=f_normal)

        # 4. Resolve Officers
        proktor_off = None
        pengawas_off = None
        kepsek_off = None

        officers = signature_manager.list_officers()
        
        # Proktor
        p_id = ass.get("proktor_id")
        if p_id:
            proktor_off = next((o for o in officers if o["id"] == p_id), None)
        if not proktor_off:
            proktor_off = next((o for o in officers if o.get("role") == "PROKTOR"), None)

        # Pengawas
        pw_id = ass.get("pengawas_id")
        if pw_id:
            pengawas_off = next((o for o in officers if o["id"] == pw_id), None)
        if not pengawas_off:
            pengawas_off = next((o for o in officers if o.get("role") == "PENGAWAS"), None)

        # Kepala Sekolah
        ks_id = ass.get("kepsek_id") or school_prof.get("kepsek_signature_id")
        if ks_id:
            kepsek_off = next((o for o in officers if o["id"] == ks_id), None)
        if not kepsek_off:
            kepsek_off = next((o for o in officers if o.get("role") == "KEPALA_SEKOLAH"), None)
            
        # Fallback names from profile if officer not found
        p_name = proktor_off.get("name") if proktor_off else "Abdurrohim, S.Kom"
        p_nip = proktor_off.get("nip") if proktor_off else "197804222024211001"
        pw_name = pengawas_off.get("name") if pengawas_off else "Wika Ayu Rohmah"
        pw_nip = pengawas_off.get("nip") if pengawas_off else "9134775676230133"
        ks_name = kepsek_off.get("name") if kepsek_off else school_prof.get("nama_kepsek", "Li'ati, S.Pd., M.Mpd")
        ks_nip = kepsek_off.get("nip") if kepsek_off else school_prof.get("nip_kepsek", "137011022007012010")

        # 5. Write Officer Names & NIPs
        # Row 1: Proktor (Y=1298, Y=1352)
        draw.text((450, 1298), p_name, fill=(10, 10, 10, 255), font=f_bold)
        draw.text((450, 1352), f"NIP. {p_nip}" if p_nip else "-", fill=(40, 40, 40, 255), font=f_small)

        # Row 2: Pengawas (Y=1408, Y=1460)
        draw.text((450, 1408), pw_name, fill=(10, 10, 10, 255), font=f_bold)
        draw.text((450, 1460), f"NIP. {pw_nip}" if pw_nip else "-", fill=(40, 40, 40, 255), font=f_small)

        # Row 3: Penanggung Jawab (Kepsek) (Y=1518, Y=1568)
        draw.text((450, 1518), ks_name, fill=(10, 10, 10, 255), font=f_bold)
        draw.text((450, 1568), f"NIP. {ks_nip}" if ks_nip else "-", fill=(40, 40, 40, 255), font=f_small)

        # 6. Overlay Signatures
        # Proktor TTD Box: X=980, Y=1280
        if proktor_off and proktor_off.get("signature_filename"):
            sig_img = self._prepare_signature_image(SIGNATURES_DIR / proktor_off["signature_filename"])
            if sig_img:
                img.alpha_composite(sig_img, dest=(1020, 1285))

        # Pengawas TTD Box: X=980, Y=1390
        if pengawas_off and pengawas_off.get("signature_filename"):
            sig_img = self._prepare_signature_image(SIGNATURES_DIR / pengawas_off["signature_filename"])
            if sig_img:
                img.alpha_composite(sig_img, dest=(1020, 1395))

        # Kepsek TTD Box: X=980, Y=1505
        if kepsek_off and kepsek_off.get("signature_filename"):
            sig_img = self._prepare_signature_image(SIGNATURES_DIR / kepsek_off["signature_filename"])
            if sig_img:
                img.alpha_composite(sig_img, dest=(1020, 1505))

        # 7. Overlay School Stamp on Kepala Sekolah Box
        stamp_info = signature_manager.get_stamp()
        if stamp_info.get("file_name"):
            stamp_p = STAMPS_DIR / stamp_info["file_name"]
            if stamp_p.exists():
                stamp_img = self._prepare_stamp_image(
                    stamp_p,
                    scale=stamp_info.get("scale", 1.0),
                    opacity=stamp_info.get("opacity", 0.88),
                    rotation=stamp_info.get("rotation_deg", -3.5)
                )
                if stamp_img:
                    # Place stamp overlapping left of Kepsek signature box
                    base_x = 910 + stamp_info.get("offset_x", -30)
                    base_y = 1450 + stamp_info.get("offset_y", -15)
                    img.alpha_composite(stamp_img, dest=(base_x, base_y))

        # 8. Save as standard RGB JPEG
        final_img = img.convert("RGB")
        if not output_filename:
            lab_str = f"Lab{ass.get('lab_num', 1)}"
            output_filename = f"BAP_G{ass.get('gelombang', 1)}_H{hari_num}_S{sesi_num}_{lab_str}.jpg"

        out_path = GENERATED_DOCS_DIR / output_filename
        final_img.save(out_path, "JPEG", quality=88, dpi=(200, 200), optimize=True)
        logger.info("Generated stamped BAP at %s (Size: %d KB)", out_path.name, out_path.stat().st_size // 1024)
        return final_img, str(out_path)

    def stamp_dh(self, slot_data: dict, assignment: dict = None, output_filename: str = None) -> tuple[Image.Image, str]:
        """
        Overlays signatures of Proktor and Pengawas onto Daftar Hadir (DH).
        Returns (PIL.Image, full_saved_path).
        """
        base_path = self.find_base_template("DH")
        if not base_path or not base_path.exists():
            raise FileNotFoundError("Berkas template Daftar Hadir dasar tidak ditemukan.")

        img = Image.open(base_path).convert("RGBA")
        draw = ImageDraw.Draw(img)

        f_bold = get_font(21, bold=True)
        f_small = get_font(19, bold=False)

        # 1. Clean signature area at bottom
        # Proktor & Pengawas boxes: X=880 to 1580, Y=1780 to 1980
        draw.rectangle([(880, 1780), (1580, 1980)], fill=(255, 255, 255, 255))

        ass = assignment or {}
        officers = signature_manager.list_officers()

        # Proktor
        p_id = ass.get("proktor_id")
        proktor_off = next((o for o in officers if o["id"] == p_id), None) if p_id else None
        if not proktor_off:
            proktor_off = next((o for o in officers if o.get("role") == "PROKTOR"), None)

        # Pengawas
        pw_id = ass.get("pengawas_id")
        pengawas_off = next((o for o in officers if o["id"] == pw_id), None) if pw_id else None
        if not pengawas_off:
            pengawas_off = next((o for o in officers if o.get("role") == "PENGAWAS"), None)

        # Overlay Proktor TTD & Name
        p_name = proktor_off.get("name") if proktor_off else "Abdurrohim, S.Kom"
        p_nip = proktor_off.get("nip") if proktor_off else "197804222024211001"
        if proktor_off and proktor_off.get("signature_filename"):
            sig = self._prepare_signature_image(SIGNATURES_DIR / proktor_off["signature_filename"])
            if sig:
                img.alpha_composite(sig, dest=(930, 1790))
        draw.text((910, 1910), p_name, fill=(10, 10, 10, 255), font=f_bold)
        draw.text((910, 1940), f"NIP. {p_nip}" if p_nip else "-", fill=(40, 40, 40, 255), font=f_small)

        # Overlay Pengawas TTD & Name
        pw_name = pengawas_off.get("name") if pengawas_off else "Wika Ayu Rohmah"
        pw_nip = pengawas_off.get("nip") if pengawas_off else "9134775676230133"
        if pengawas_off and pengawas_off.get("signature_filename"):
            sig = self._prepare_signature_image(SIGNATURES_DIR / pengawas_off["signature_filename"])
            if sig:
                img.alpha_composite(sig, dest=(1310, 1790))
        draw.text((1280, 1910), pw_name, fill=(10, 10, 10, 255), font=f_bold)
        draw.text((1280, 1940), f"NIP. {pw_nip}" if pw_nip else "-", fill=(40, 40, 40, 255), font=f_small)

        # Save as standard RGB JPEG
        final_img = img.convert("RGB")
        hari_num = ass.get("hari") or slot_data.get("hari") or 1
        sesi_num = ass.get("sesi") or slot_data.get("sesi") or 1
        if not output_filename:
            lab_str = f"Lab{ass.get('lab_num', 1)}"
            output_filename = f"DH_G{ass.get('gelombang', 1)}_H{hari_num}_S{sesi_num}_{lab_str}.jpg"

        out_path = GENERATED_DOCS_DIR / output_filename
        final_img.save(out_path, "JPEG", quality=88, dpi=(200, 200), optimize=True)
        logger.info("Generated stamped DH at %s (Size: %d KB)", out_path.name, out_path.stat().st_size // 1024)
        return final_img, str(out_path)

stamp_engine = StampEngine()

import os
import json
import shutil
from PIL import Image, ImageFilter

def extract_and_sync():
    os.makedirs('static/signatures', exist_ok=True)
    os.makedirs('static/stamps', exist_ok=True)

    appdata = os.environ.get('APPDATA')
    appdata_dir = os.path.join(appdata, 'SmartTKAScanner')
    appdata_sigs = os.path.join(appdata_dir, 'signatures')
    appdata_stamps = os.path.join(appdata_dir, 'stamps')
    os.makedirs(appdata_sigs, exist_ok=True)
    os.makedirs(appdata_stamps, exist_ok=True)

    # 1. Clean Purple Stamp
    def clean_stamp(src_path, out_path):
        im = Image.open(src_path).convert('RGB')
        crop = im.crop((580, 1130, 980, 1530))
        w, h = crop.size
        out = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        
        for y in range(h):
            for x in range(w):
                r, g, b = crop.getpixel((x, y))
                purple_diff = (r + b) / 2.0 - g
                darkness = 255.0 - ((r + g + b) / 3.0)
                
                if purple_diff > 10 and darkness > 18:
                    alpha = int(min(255, max(50, darkness * 1.8 + purple_diff * 2.2)))
                    ink_r = max(60, min(130, int(r * 0.82)))
                    ink_g = max(15, min(65, int(g * 0.72)))
                    ink_b = max(120, min(205, int(b * 0.92)))
                    out.putpixel((x, y), (ink_r, ink_g, ink_b, alpha))
                elif darkness > 40 and (r < 195 or b < 195):
                    alpha = int(min(255, darkness * 1.4))
                    out.putpixel((x, y), (100, 40, 155, alpha))
                else:
                    out.putpixel((x, y), (0, 0, 0, 0))
                    
        alpha = out.split()[3]
        bbox = alpha.getbbox()
        if bbox:
            pad = 8
            bbox = (max(0, bbox[0]-pad), max(0, bbox[1]-pad), min(w, bbox[2]+pad), min(h, bbox[3]+pad))
            out = out.crop(bbox)
        out.save(out_path, 'PNG')
        print(f'[+] Stamp saved: {out_path}, size {out.size}')

    # 2. Clean Blue Pen Signature
    def clean_blue_sig(src_path, out_path, bbox):
        im = Image.open(src_path).convert('RGB')
        crop = im.crop(bbox)
        w, h = crop.size
        out = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        
        for y in range(h):
            for x in range(w):
                r, g, b = crop.getpixel((x, y))
                is_blue = (b > r + 15) or (b > g + 10 and b > 65)
                darkness = 255.0 - ((r + g + b) / 3.0)
                
                if is_blue and darkness > 20:
                    alpha = int(min(255, max(60, darkness * 1.95)))
                    ink_r = max(0, min(30, int(r * 0.7)))
                    ink_g = max(35, min(95, int(g * 0.85)))
                    ink_b = max(150, min(235, int(b * 1.05)))
                    out.putpixel((x, y), (ink_r, ink_g, ink_b, alpha))
                else:
                    out.putpixel((x, y), (0, 0, 0, 0))
                    
        alpha = out.split()[3]
        bbox_crop = alpha.getbbox()
        if bbox_crop:
            pad = 6
            bbox_crop = (max(0, bbox_crop[0]-pad), max(0, bbox_crop[1]-pad), min(w, bbox_crop[2]+pad), min(h, bbox_crop[3]+pad))
            out = out.crop(bbox_crop)
        out.save(out_path, 'PNG')
        print(f'[+] Blue sig saved: {out_path}, size {out.size}')

    # 3. Clean Black/Dark Ink Signature
    def clean_black_sig(src_path, out_path, bbox, color_mode='black'):
        im = Image.open(src_path).convert('RGB')
        crop = im.crop(bbox)
        w, h = crop.size
        out = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        
        paper_lums = []
        for y in [2, 3, h-4, h-3]:
            for x in range(10, w-10, 10):
                r, g, b = crop.getpixel((x, y))
                paper_lums.append((r + g + b)/3.0)
        avg_paper = sum(paper_lums) / len(paper_lums) if paper_lums else 240.0
        thresh = avg_paper - 35.0
        
        for y in range(h):
            if y < 4 or y > h - 5:
                continue
            for x in range(w):
                r, g, b = crop.getpixel((x, y))
                lum = (r + g + b) / 3.0
                purple_diff = (r + b)/2.0 - g
                is_blue = (b > r + 15 and b > g + 10)
                
                if lum < thresh:
                    darkness = avg_paper - lum
                    alpha = int(min(255, max(60, darkness * 2.2)))
                    if color_mode == 'blue' or is_blue:
                        out.putpixel((x, y), (15, 50, 180, alpha))
                    elif color_mode == 'purple' or purple_diff > 15:
                        out.putpixel((x, y), (105, 35, 160, alpha))
                    else:
                        ink_val = int(max(10, min(50, lum * 0.3)))
                        out.putpixel((x, y), (ink_val, ink_val, ink_val, alpha))
                else:
                    out.putpixel((x, y), (0, 0, 0, 0))
                    
        alpha = out.split()[3]
        bbox_crop = alpha.getbbox()
        if bbox_crop:
            pad = 6
            bbox_crop = (max(0, bbox_crop[0]-pad), max(0, bbox_crop[1]-pad), min(w, bbox_crop[2]+pad), min(h, bbox_crop[3]+pad))
            out = out.crop(bbox_crop)
        out.save(out_path, 'PNG')
        print(f'[+] Sig saved: {out_path}, size {out.size}')

    print('--- Extracting Real Authentic Signatures and Stamp ---')
    clean_stamp('inbox/Image_20261030_0017.jpg', 'static/stamps/school_stamp.png')
    clean_blue_sig('inbox/Image_20261102_0009.jpg', 'static/signatures/sig_liati.png', (860, 1480, 1260, 1630))
    clean_black_sig('DokumenTKA/BAP/Image_20261026_0001.jpg', 'static/signatures/sig_abdurrohim.png', (860, 1260, 1260, 1390))
    clean_black_sig('inbox/Image_20261102_0009.jpg', 'static/signatures/sig_agus_siswanto.png', (860, 1260, 1260, 1390))
    clean_black_sig('DokumenTKA/BAP/Image_20261026_0001.jpg', 'static/signatures/sig_wika_ayu.png', (860, 1370, 1260, 1500), color_mode='purple')
    clean_black_sig('inbox/Image_20261102_0009.jpg', 'static/signatures/sig_idam_setiyawan.png', (860, 1370, 1260, 1500))
    clean_black_sig('inbox/Image_20261102_0005.jpg', 'static/signatures/sig_rosyidatul_ummah.png', (860, 1370, 1260, 1500))
    clean_black_sig('inbox/Image_20261030_0009.jpg', 'static/signatures/sig_agustina_budiarti.png', (860, 1320, 1260, 1460), color_mode='blue')
    clean_black_sig('DokumenTKA/BAP/Image_20261026_0007.jpg', 'static/signatures/sig_dimagha_eldina.png', (860, 1370, 1260, 1500))

    # Copy files to APPDATA
    print('--- Mirroring assets to APPDATA ---')
    for f in os.listdir('static/signatures'):
        src = os.path.join('static/signatures', f)
        dst = os.path.join(appdata_sigs, f)
        shutil.copy2(src, dst)

    for f in os.listdir('static/stamps'):
        src = os.path.join('static/stamps', f)
        dst = os.path.join(appdata_stamps, f)
        shutil.copy2(src, dst)

    sig_map = {
        "li'ati": "sig_liati.png",
        "abdurrohim": "sig_abdurrohim.png",
        "agus siswanto": "sig_agus_siswanto.png",
        "wika ayu": "sig_wika_ayu.png",
        "idam setiyawan": "sig_idam_setiyawan.png",
        "rosyidatul": "sig_rosyidatul_ummah.png",
        "agustina": "sig_agustina_budiarti.png",
        "dimagha": "sig_dimagha_eldina.png",
    }

    # Ensure all real officers are in the master list
    base_officers = [
        {"id": "off_liati", "name": "Li'ati, S.Pd., M.Mpd", "nip": "137011022007012010", "role": "KEPALA_SEKOLAH", "has_signature": True, "signature_filename": "sig_liati.png"},
        {"id": "off_abdurrohim", "name": "Abdurrohim, S.Kom", "nip": "197804222024211001", "role": "PROKTOR", "has_signature": True, "signature_filename": "sig_abdurrohim.png"},
        {"id": "off_agus", "name": "Agus Siswanto, S.Kom.", "nip": "198308162024211005", "role": "PROKTOR", "has_signature": True, "signature_filename": "sig_agus_siswanto.png"},
        {"id": "off_wika", "name": "Wika Ayu Rohmah", "nip": "9134775676230133", "role": "PENGAWAS", "has_signature": True, "signature_filename": "sig_wika_ayu.png"},
        {"id": "off_idam", "name": "Idam Setiyawan", "nip": "1937766667130292", "role": "PENGAWAS", "has_signature": True, "signature_filename": "sig_idam_setiyawan.png"},
        {"id": "off_rosyidatul", "name": "Rosyidatul Ummah", "nip": "5534752654300013", "role": "PENGAWAS", "has_signature": True, "signature_filename": "sig_rosyidatul_ummah.png"},
        {"id": "off_agustina", "name": "Agustina Budiarti", "nip": "1156760661210113", "role": "PENGAWAS", "has_signature": True, "signature_filename": "sig_agustina_budiarti.png"},
        {"id": "off_dimagha", "name": "DIMAGHA ELDINA", "nip": "", "role": "PENGAWAS", "has_signature": True, "signature_filename": "sig_dimagha_eldina.png"},
    ]

    payload = {
        "school": {
            "name": "SMAN 1 GEDEG",
            "npsn": "20502721",
            "headmaster_name": "Li'ati, S.Pd., M.Mpd",
            "headmaster_nip": "137011022007012010"
        },
        "officers": base_officers,
        "stamp": {
            "file_name": "school_stamp.png",
            "scale": 1.0,
            "opacity": 0.88,
            "rotation_deg": -3.5,
            "offset_x": -30,
            "offset_y": -15,
            "has_file": True
        }
    }

    for target in ['signatures_data.json', os.path.join(appdata_dir, 'signatures_data.json')]:
        with open(target, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        print(f'[+] Synchronized {target}')

if __name__ == '__main__':
    extract_and_sync()

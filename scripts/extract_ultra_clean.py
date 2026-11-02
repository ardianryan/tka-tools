import os
import math
import shutil
from PIL import Image

def run_extraction():
    print("=== Deployed Perfect Ultra-Clean Signatures & Stamp ===")
    
    dirs_to_update = [
        "static/signatures",
        "static/stamps",
        "dist/SmartTKAScanner/signatures",
        "dist/SmartTKAScanner/stamps",
        r"C:\Program Files (x86)\Smart TKA Scanner\signatures",
        r"C:\Program Files (x86)\Smart TKA Scanner\stamps"
    ]
    
    appdata = os.environ.get("APPDATA")
    if appdata:
        dirs_to_update.extend([
            os.path.join(appdata, "SmartTKAScanner", "signatures"),
            os.path.join(appdata, "SmartTKAScanner", "stamps")
        ])
        
    for d in dirs_to_update:
        os.makedirs(d, exist_ok=True)

    # 1. School Stamp (Circular purple stamp, transparent background)
    def clean_stamp_ultra(src_path):
        im = Image.open(src_path).convert('RGB')
        cx, cy = 780, 1330
        radius = 185
        crop = im.crop((cx - radius, cy - radius, cx + radius, cy + radius))
        w, h = crop.size
        center_local = (radius, radius)
        
        out = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        for y in range(h):
            for x in range(w):
                dist = math.hypot(x - center_local[0], y - center_local[1])
                if dist > radius:
                    continue
                    
                r, g, b = crop.getpixel((x, y))
                purple_diff = (r + b) / 2.0 - g
                darkness = 255.0 - ((r + g + b) / 3.0)
                
                if purple_diff > 10 and darkness > 18:
                    alpha = int(min(255, max(50, darkness * 1.85 + purple_diff * 2.2)))
                    ink_r = max(60, min(130, int(r * 0.82)))
                    ink_g = max(15, min(65, int(g * 0.72)))
                    ink_b = max(120, min(205, int(b * 0.92)))
                    out.putpixel((x, y), (ink_r, ink_g, ink_b, alpha))
                elif darkness > 42 and (r < 195 or b < 195):
                    alpha = int(min(255, darkness * 1.4))
                    out.putpixel((x, y), (100, 40, 155, alpha))
                    
        alpha = out.split()[3]
        bbox = alpha.getbbox()
        if bbox:
            pad = 6
            bbox = (max(0, bbox[0]-pad), max(0, bbox[1]-pad), min(w, bbox[2]+pad), min(h, bbox[3]+pad))
            out = out.crop(bbox)
        return out

    # 2. Kepala Sekolah (Li'ati) - Full rich vibrant blue ink, zero stamp, zero lines
    def clean_liati(src_path):
        im = Image.open(src_path).convert('RGB')
        # Tight box avoiding Row 2 bottom line and avoiding stamp on right
        crop = im.crop((880, 1488, 1150, 1585))
        w, h = crop.size
        out = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        paper_lum = 245.0
        
        for y in range(h):
            if y < 3 or y > h - 4: continue
            for x in range(w):
                if x < 3 or x > w - 4: continue
                r, g, b = crop.getpixel((x, y))
                lum = (r + g + b) / 3.0
                
                is_blue = (b > r + 15 and b > g + 5) or (b > r + 25) or (b > 105 and b > r + 10)
                is_dark_stroke = (lum < 155 and b >= r - 5 and b >= g - 10)
                
                if (is_blue or is_dark_stroke) and lum < 220:
                    darkness = paper_lum - lum
                    alpha = int(min(255, max(85, darkness * 2.5)))
                    ink_r = max(0, min(30, int(r * 0.35)))
                    ink_g = max(20, min(75, int(g * 0.55)))
                    ink_b = max(135, min(235, int(b * 1.18)))
                    out.putpixel((x, y), (ink_r, ink_g, ink_b, alpha))

        alpha = out.split()[3]
        bbox = alpha.getbbox()
        if bbox:
            pad = 6
            bbox = (max(0, bbox[0]-pad), max(0, bbox[1]-pad), min(w, bbox[2]+pad), min(h, bbox[3]+pad))
            out = out.crop(bbox)
        return out

    # 3. Proktor & Pengawas - Pure black ink, zero TTD text, zero border lines, zero stamp
    def clean_black(src_path, y1, y2, x1=880, x2=1240):
        im = Image.open(src_path).convert('RGB')
        crop = im.crop((x1, y1, x2, y2))
        w, h = crop.size
        out = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        paper_lum = 245.0
        
        for y in range(h):
            if y < 3 or y > h - 4: continue
            for x in range(w):
                if x < 3 or x > w - 4: continue
                r, g, b = crop.getpixel((x, y))
                lum = (r + g + b) / 3.0
                p_diff = (r + b) / 2.0 - g
                
                # Strict stamp rejection: no purple ink allowed
                if p_diff > 12 and r > 100:
                    continue
                    
                if lum < 175:
                    darkness = paper_lum - lum
                    alpha = int(min(255, max(75, darkness * 2.3)))
                    ink_val = int(max(10, min(35, lum * 0.22)))
                    out.putpixel((x, y), (ink_val, ink_val, ink_val, alpha))
                    
        alpha = out.split()[3]
        bbox = alpha.getbbox()
        if bbox:
            pad = 6
            bbox = (max(0, bbox[0]-pad), max(0, bbox[1]-pad), min(w, bbox[2]+pad), min(h, bbox[3]+pad))
            out = out.crop(bbox)
        return out

    items = {}
    print("1. School Stamp...")
    items['school_stamp.png'] = ('stamp', clean_stamp_ultra('inbox/Image_20261030_0017.jpg'))
    
    print("2. Kepala Sekolah (Li'ati, S.Pd., M.Mpd) - Full Vibrant Blue Ink...")
    items['sig_liati.png'] = ('sig', clean_liati('inbox/Image_20261102_0009.jpg'))
    
    print("3. Proktor (Abdurrohim) - Pure Black Ink, No TTD Text...")
    items['sig_abdurrohim.png'] = ('sig', clean_black('inbox/Image_20261102_0001.jpg', 1282, 1362))
    
    print("4. Proktor (Agus Siswanto) - Pure Black Ink, No TTD Text...")
    items['sig_agus_siswanto.png'] = ('sig', clean_black('inbox/Image_20261102_0009.jpg', 1282, 1362))
    
    print("5. Pengawas (Wika Ayu Rohmah) - Pure Black Ink, Zero Stamp...")
    items['sig_wika_ayu.png'] = ('sig', clean_black('inbox/Image_20261102_0001.jpg', 1378, 1470))
    
    print("6. Pengawas (Idam Setiyawan) - Pure Black Ink, Zero Stamp...")
    items['sig_idam_setiyawan.png'] = ('sig', clean_black('DokumenTKA/BAP/Image_20261026_0005.jpg', 1378, 1470))
    
    print("7. Pengawas (Rosyidatul Ummah) - Pure Black Ink, Zero Stamp...")
    items['sig_rosyidatul_ummah.png'] = ('sig', clean_black('inbox/Image_20261102_0005.jpg', 1378, 1470))
    
    print("8. Pengawas (Agustina Budiarti) - Pure Black Ink, Zero Stamp...")
    items['sig_agustina_budiarti.png'] = ('sig', clean_black('DokumenTKA/BAP/Image_20261026_0020.jpg', 1378, 1470))
    
    print("9. Pengawas (DIMAGHA ELDINA) - Pure Black Ink, Zero Stamp...")
    items['sig_dimagha_eldina.png'] = ('sig', clean_black('DokumenTKA/BAP/Image_20261026_0008.jpg', 1378, 1470))

    # Deploy
    for fn, (kind, img) in items.items():
        print(f"  [+] {fn:24}: {img.size}")
        for d in dirs_to_update:
            if kind == 'stamp':
                if 'stamps' in d or 'signatures' in d:
                    img.save(os.path.join(d, fn), 'PNG')
            else:
                if 'signatures' in d:
                    img.save(os.path.join(d, fn), 'PNG')

    print("=== Successfully Deployed Perfect Signatures & Stamp ===")

if __name__ == '__main__':
    run_extraction()

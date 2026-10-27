# Smart TKA Scanner & Auto-Uploader (`tka-tools`)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Build Status](https://github.com/ardianryan/tka-tools/actions/workflows/build.yml/badge.svg)](https://github.com/ardianryan/tka-tools/actions/workflows/build.yml)
[![Version](https://img.shields.io/badge/Version-1.0.0-emerald.svg)](CHANGELOG.md)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)](https://github.com/ardianryan/tka-tools/releases)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

Aplikasi desktop dan otomasi lokal sumber terbuka (*open-source*) untuk mempermudah proktor dan teknisi sekolah dalam memindai berkas fisik ujian TKA (Berita Acara Pelaksanaan & Daftar Hadir), mengekstrak data menggunakan OCR offline berkecepatan tinggi, mencocokkan jadwal sesi/lab secara otomatis, dan mengunggahnya ke portal web TKA.

---

> [!WARNING]
> ### ⚠️ PERINGATAN PENTING & SANGGAHAN (DISCLAIMER) — DWYOR
>
> 1. **BUKAN APLIKASI RESMI (UNOFFICIAL HELPER TOOL):**
>    Perangkat lunak ini adalah proyek independen berbasis komunitas dan **TIDAK RESMI**. Perangkat lunak ini **TIDAK terafiliasi, didukung, disponsori, atau disetujui secara resmi** oleh **Pusat Penilaian Pendidikan (Puspendik)**, **Pusat Asesmen Pendidikan**, **Badan Standar, Kurikulum, dan Asesmen Pendidikan (BSKAP)**, maupun **Kementerian Pendidikan Dasar dan Menengah (Kemendikdasmen) Republik Indonesia**.
>
> 2. **HAK KEKAYAAN INTELEKTUAL & MEREK:**
>    Seluruh nama layanan, istilah ujian, alamat situs, dan hak cipta portal resmi yang dirujuk dalam utilitas ini adalah hak milik dari pemilik hak cipta dan instansi pemerintah terkait. Penggunaan nama atau tautan dalam proyek ini murni untuk tujuan interoperabilitas teknis dan kemudahan operasional proktor di lapangan.
>
> 3. **DO WITH YOUR OWN RISK (DWYOR):**
>    Aplikasi ini disediakan **"SEBAGAIMANA ADANYA" (*AS IS*)** tanpa jaminan apa pun dalam bentuk apa pun (tersirat maupun tersurat), sebagaimana termaktub dalam [Lisensi MIT](LICENSE). 
>    Pengembang dan kontributor **tidak bertanggung jawab** atas segala bentuk kegagalan koneksi, keterlambatan unggah, ketidaksesuaian berkas, sanksi administratif, atau kerugian materiil maupun immateriil yang timbul dari penggunaan alat ini. 
>    **Pengguna wajib memeriksa dan memverifikasi ulang keabsahan dan kesesuaian berkas yang telah diunggah langsung pada portal web resmi pemerintah.**

---

## 🌟 Fitur Utama

1. **Dukungan Multi-Brand Scanner Universal (WIA Native)**
   - Mendukung semua merek pemindai (Epson EcoTank/L-series, Canon LiDE & imageFORMULA, Brother, HP ScanJet, Fujitsu, dll.) melalui protokol WIA native Windows.
   - **Mode ADF (Auto Document Feeder)**: Memindai puluhan lembar berkas secara kontinu dalam satu klik.
   - **Mode Flatbed**: Pemindaian satu per satu lewat kaca datar dengan auto-fallback.
   - **Hot-Folder Watcher (`inbox/`)**: Otomatis mendeteksi file baru jika pemindaian dilakukan lewat tombol fisik atau software vendor scanner.

2. **OCR Cerdas & Ekstraksi Metadata Offline**
   - Berjalan **100% lokal dan offline** (Windows Media OCR di Windows 10/11 atau Tesseract OCR di macOS/Linux) tanpa mengirim citra dokumen ke server cloud pihak ketiga.
   - Kecepatan ekstraksi rata-rata ~0.2 detik per lembar.
   - Mengenali otomatis: Jenis Dokumen (BAP vs Daftar Hadir), Hari pelaksanaan, Sesi ujian, Ruang/Laboratorium, Kode Server, dan Mata Pelajaran.

3. **Pencocokan Cerdas ke 96 Slot Jadwal Ujian**
   - Menghitung skor probabilitas kecocokan (*scoring match*) dan secara otomatis memetakan berkas ke target slot jadwal ujian sekolah yang tepat.
   - Menyediakan dialog rotasi citra (90°, 180°, 270°) dan penyesuaian manual jika stempel/tulisan tangan kurang terbaca.

4. **Antrean Unggah Cerdas & Proteksi Duplikasi (Smart Deduplication)**
   - **Deteksi Rangkap 2 Otomatis**: Mendeteksi secara cerdas jika lembar rangkap 1 dan rangkap 2 dipindai bersamaan di ADF. Sistem otomatis menandai rangkap 2 sebagai `[RANGKAP 2 (DILEWATI)]` sehingga tidak terunggah ganda ke portal, mengarsipkannya ke folder `processed/duplicates/`, dan menyediakan tombol manual *Pakai Ini* jika lembar kedua lebih jelas.
   - **Jeda Acak Manusiawi (Human-like Random Delay)**: Dilengkapi jeda waktu acak (default 3 s/d 5 detik) di setiap berkas yang selesai diunggah agar request terlihat wajar seperti operator manusia dan aman dari proteksi bot/WAF.
   - **Loading Progress Bar Interaktif**: Menampilkan animasi progress bar realtime, persentase berkas, nama berkas & sesi/lab yang sedang diunggah, serta hitung mundur waktu jeda.
   - **Kontrol Penuh**: Tersedia tombol **Jeda (Pause)**, **Lanjutkan (Resume)**, dan **Hentikan (Stop)** kapan saja selama proses unggah berlangsung.

5. **Pencatatan Audit & Pengarsipan Otomatis**
   - Mencatat seluruh riwayat unggahan ke format spreadsheet CSV (`logs/riwayat_unggah.csv`) dan JSONL.
   - Otomatis membuat salinan arsip digital dengan format nama terstruktur di folder `processed/` (misal: `BAP_H1_S1_Lab1_TIMESTAMP.jpg`).

---

## 🚀 Cara Menjalankan

### Cara 1: Menggunakan Desktop Executable (Rilis Siap Pakai)
Unduh bundel rilis dari tab [**GitHub Releases**](https://github.com/ardianryan/tka-tools/releases):
* **Windows (x64):** Ekstrak `SmartTKAScanner-Windows-x64.zip` dan jalankan `SmartTKAScanner.exe`.
* **macOS:** Ekstrak `SmartTKAScanner-macOS.zip` dan buka `SmartTKAScanner.app`.
* **Linux:** Ekstrak `SmartTKAScanner-Linux-x64.tar.gz` dan jalankan binari `SmartTKAScanner`.

### Cara 2: Menjalankan dari Source Code (Python)
1. **Clone repositori:**
   ```bash
   git clone https://github.com/ardianryan/tka-tools.git
   cd tka-tools
   ```
2. **Pasang dependensi:**
   ```bash
   pip install -r requirements.txt
   ```
3. **Salin template pengaturan:**
   ```bash
   cp settings.example.json settings.json
   ```
4. **Jalankan aplikasi:**
   * Mode Desktop Window: `python desktop_app.py`
   * Mode Web Server Standar: `python app.py` atau klik ganda `run_dashboard.bat` (di Windows)

Dashboard dapat diakses melalui browser di alamat:
👉 **[http://127.0.0.1:5000](http://127.0.0.1:5000)**

---

## 📁 Struktur Berkas

```text
├── .github/workflows/build.yml   # Workflow GitHub Actions Multi-Platform CI/CD
├── desktop_app.py                # Launcher aplikasi native desktop (pywebview)
├── app.py                        # Server backend Flask & REST API
├── tka_client.py                 # Klien HTTP login & sinkronisasi jadwal portal
├── ocr_engine.py                 # Mesin ekstraksi OCR offline & algoritma pencocokan
├── scanner_wia.py                # Wrapper controller scanner WIA
├── wia_scan.ps1                  # Skrip PowerShell pemindaian ADF/Flatbed Windows
├── folder_watcher.py             # Pemantau folder inbox otomatis
├── upload_logger.py              # Pencatat audit log CSV dan pengarsipan berkas
├── settings_manager.py           # Manajer konfigurasi dinamis aplikasi
├── settings.example.json         # Template aman pengaturan scanner & OCR
├── requirements.txt              # Daftar pustaka Python
├── SmartTKAScanner.spec           # Spesifikasi packaging PyInstaller
├── create_desktop_shortcut.ps1   # Utilitas pembuat shortcut Desktop Windows
├── templates/index.html          # Antarmuka Web Dashboard responsif
├── static/                       # Aset visual & icon aplikasi (ICO, PNG, Favicon)
├── CHANGELOG.md                  # Catatan riwayat versi rilis
├── CONTRIBUTING.md               # Panduan kontribusi komunitas
├── CODE_OF_CONDUCT.md            # Standar kode etik komunitas
├── SECURITY.md                   # Kebijakan pelaporan celah keamanan & privasi data
└── LICENSE                       # Lisensi resmi (MIT License)
```

---

## 🔒 Keamanan & Privasi Data

Proyek ini sangat mengutamakan keamanan dan privasi data sekolah:
* **Zero-Cloud Processing:** Seluruh pembacaan OCR berjalan 100% di komputer lokal Anda.
* **Perlindungan Berkas:** Berkas pindaian fisik di folder `DokumenTKA/`, `inbox/`, `processed/`, serta log `logs/*.csv` secara ketat diabaikan oleh `.gitignore`.
* Untuk detail kebijakan pelaporan kerentanan atau privasi, silakan baca [SECURITY.md](SECURITY.md).

---

## 🤝 Kontribusi

Kontribusi dari komunitas sangat disambut dengan tangan terbuka! Baik berupa pelaporan bug, penyempurnaan regex stempel ujian daerah, atau penambahan protokol scanner baru.
Silakan baca panduan lengkap di [CONTRIBUTING.md](CONTRIBUTING.md) dan pastikan mengikuti [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

---

## 📜 Lisensi

Proyek ini dilisensikan di bawah **[MIT License](LICENSE)** — bebas digunakan, dimodifikasi, dan didistribusikan oleh siapa saja untuk tujuan baik.

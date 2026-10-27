# Changelog

Semua perubahan penting pada proyek **Smart TKA Scanner & Auto-Uploader (`tka-tools`)** akan dicatat dalam berkas ini.

Format berkas ini mengacu pada [Keep a Changelog](https://keepachangelog.com/id/1.0.0/), dan proyek ini menganut [Semantic Versioning (SemVer)](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] - 2026-10-27

### Ditambahkan (Added)
- **Integrasi Scanner Universal (WIA Native)**:
  - Pemindaian otomatis tumpukan dokumen via ADF (Auto Document Feeder) dan kaca Flatbed.
  - Skrip PowerShell `wia_scan.ps1` yang mendukung berbagai merek scanner (Epson, Canon, Brother, HP, Fujitsu).
  - Pemantauan otomatis folder `inbox/` secara real-time via `folder_watcher.py`.
- **Mesin OCR & Pencocokan Jadwal Cerdas**:
  - Dukungan Windows Media OCR berkecepatan tinggi (~0.2 detik per lembar) untuk Windows 10/11.
  - Fallback otomatis ke Tesseract OCR (`pytesseract`) untuk lingkungan macOS dan Linux.
  - Ekstraksi otomatis tipe dokumen (BAP vs Daftar Hadir), Hari pelaksanaan, Sesi ujian (1-3), Ruang/Lab (1-4), Kode Server, dan Mata Pelajaran.
  - Algoritma pencocokan berbobot otomatis ke 96 slot jadwal ujian resmi sekolah.
- **Antarmuka Web Dashboard Modern & Profesional**:
  - Desain antarmuka admin enterprise berbasis Bootstrap 5 & JetBrains Mono (anti-slop, tabular numbers, high-density layout).
  - Modal Pengaturan interaktif dengan 3 tab: Pengaturan Scanner, Akun & Jeda Unggah, serta Parameter OCR Regex.
  - Dialog pratinjau dokumen scan resolusi tinggi dengan kemampuan rotasi (90°, 180°, 270°) dan penyesuaian manual.
- **Antrean Unggah Cerdas & Aman (Safe Queue)**:
  - **Smart Deduplication (Deteksi Rangkap 2 Otomatis)**: Mendeteksi dokumen rangkap/ganda yang dipindai bersamaan di ADF, secara cerdas menandai status sebagai `DUPLICATE_SKIPPED` agar tidak diunggah 2x ke portal, mengarsipkan salinan ke `processed/duplicates/`, dan menyediakan tombol *Pakai Ini* untuk menukar berkas secara manual.
  - Eksekusi unggahan berkas berurutan dengan jeda acak manusiawi (human-like delay 3–5 detik) untuk mencegah kecurigaan sistem portal.
  - Indikator progres realtime dengan hitung mundur jeda dan kontrol Jeda (Pause) / Lanjutkan (Resume).
  - Sinkronisasi sesi portal otomatis dan re-autentikasi berkala.
- **Pencatatan Riwayat & Audit Log**:
  - Pencatatan otomatis riwayat unggahan ke format CSV (`logs/riwayat_unggah.csv`) dan JSONL.
  - Pengarsipan otomatis salinan berkas fisik ke direktori `processed/` dengan tata nama standar.
  - Tombol ekspor laporan CSV langsung dari web dashboard.
- **Dukungan Aplikasi Desktop Native & CI/CD**:
  - Wrapper aplikasi desktop native `desktop_app.py` menggunakan `pywebview` (jendela native mandiri tanpa terminal).
  - Konfigurasi workflow GitHub Actions multi-platform matrix (`.github/workflows/build.yml`) untuk build otomatis Windows (`.exe`), macOS (`.app`/`.dmg`), dan Linux (`.tar.gz`).
  - Icon aplikasi resmi multi-resolusi (`app_icon.ico`, `app_icon.png`, favicon).
  - Skrip pembuatan shortcut Windows Desktop otomatis (`create_desktop_shortcut.ps1`).

### Keamanan (Security)
- Konfigurasi isolasi server default pada `127.0.0.1:5000` (loopback only).
- Konfigurasi `.gitignore` ketat untuk memblokir berkas fisik ujian peserta, log nama siswa, dan file kredensial lokal dari riwayat Git.
- Pemisahan file konfigurasi menjadi `settings.example.json` (publik) dan `settings.json` (lokal).
- Penambahan kebijakan keamanan [SECURITY.md](SECURITY.md) dan panduan pelaporan kerentanan privat.

### Lisensi & Tata Kelola
- Lisensi resmi proyek menggunakan **MIT License** yang terbuka dan fleksibel untuk komunitas pengembang.
- Penambahan panduan kontribusi [CONTRIBUTING.md](CONTRIBUTING.md) dan [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

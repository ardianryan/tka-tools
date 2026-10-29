# Changelog

Semua perubahan penting pada proyek **Smart TKA Scanner & Auto-Uploader (`tka-tools`)** akan dicatat dalam berkas ini.

Format berkas ini mengacu pada [Keep a Changelog](https://keepachangelog.com/id/1.0.0/), dan proyek ini menganut [Semantic Versioning (SemVer)](https://semver.org/spec/v2.0.0.html).

---

## [1.0.5] - 2026-10-29

### Diperbaiki (Fixed)
- **Persistensi Konfigurasi & Smart Detection Akun Proktor (Zero Re-Login Guarantee)**:
  - Mengatasi masalah popup modal *"Panduan Setup Awal Proktor"* yang terus muncul setiap kali aplikasi ditutup-buka atau diperbarui/ditimpa dengan instalasi baru.
  - Memindahkan penyimpanan permanen berkas konfigurasi (`settings.json`) dan sesi login aktif (`.tka_session.json`) ke direktori profil pengguna standar Windows (`%APPDATA%\SmartTKAScanner`), bebas dari proteksi izin sistem `C:\Program Files (x86)`.
  - Mengimplementasikan *Smart Migration*: secara otomatis mendeteksi dan memigrasikan akun proktor serta pengaturan yang sudah ada sebelumnya dari direktori lama tanpa perlu mengetik ulang username atau password.
  - Penambahan *Auto-Login & Auto-Sync* di latar belakang saat aplikasi dibuka, menjaga sesi portal tetap aktif dan terverifikasi secara mulus (*seamless*).
  - Memberikan hak izin penuh pengguna (`Permissions: users-full`) pada seluruh folder instalasi aplikasi di *Inno Setup* untuk mencegah kendala hak akses Windows (*Access is Denied*).

---

## [1.0.4] - 2026-10-29

### Diperbaiki (Fixed)
- **Perbaikan Komprehensif Scanner WIA (Mengatasi [WinError 2] The system cannot find the file specified)**:
  - Menyelesaikan kegagalan pemanggilan PowerShell akibat variabel `PATH` sistem pengguna yang tidak menyertakan direktori `C:\Windows\System32\WindowsPowerShell\v1.0`.
  - Implementasi resolver mutlak cerdas `get_powershell_exe()` yang melacak jalur resmi Windows PowerShell, SysWOW64, dan PowerShell 7 (pwsh).
  - Scanner terhubung (seperti EPSON L5290 Series) kini langsung terdeteksi **Online: True** tanpa gagal eksekusi.
  - Skrip pemindaian `wia_scan.ps1` dilacak secara dinamis di seluruh kemungkinan direktori bundel aplikasi.

### Ditambahkan (Added)
- **Bundling Penuh Visual C++ Runtime (Zero-Dependency Guarantee)**:
  - Menyertakan seluruh pustaka biner Visual C++ 2015-2022 Redistributable (`msvcp140.dll`, `msvcp140_1.dll`, `msvcp140_2.dll`, `msvcp140_atomic_wait.dll`, `msvcp140_codecvt_ids.dll`, `vcruntime140.dll`, `vcruntime140_1.dll`) langsung di dalam folder aplikasi (`_internal`).
  - Menghilangkan kebutuhan instalasi terpisah bagi komputer proktor/sekolah; aplikasi siap jalan langsung di Windows bersih tanpa perlu mengunduh komponen VC++.

---

## [1.0.3] - 2026-10-29

### Diperbaiki (Fixed)
- **Pembacaan Komprehensif Berita Acara Pelaksanaan (BAP)**:
  - Mengatasi kesalahan inferensi Sesi pada jam pelaksanaan ujian: jam `11:10 sampai dengan 12:30` kini secara akurat dipetakan ke **Sesi 3** (sebelumnya salah terbaca sebagai Sesi 2 akibat pengelompokan jam `11:xx` ke sesi 2).
  - Mengimplementasikan pemetaan waktu berbasis total menit presisi:
    - Sesi 1: Mulai $\le$ 08:45 (misal 07:00, 07:30, 08:00)
    - Sesi 2: Mulai 08:46 - 10:45 (misal 09:00, 09:05, 10:00, 10:30)
    - Sesi 3: Mulai $\ge$ 10:46 (misal 11:00, 11:10, 12:30, 13:00)
  - Ekstraksi langsung nilai Sesi dari tabel metadata dokumen BAP (termasuk artefak scan seperti `.3`, `: 3`, `- 3`, ` 3`).
  - Menghilangkan *false positive duplicate* ("Rangkap 2 Terdeteksi") pada Berita Acara Sesi 3 yang sebelumnya salah diabaikan karena bentrok dengan berkas Sesi 2.
  - Peningkatan ketahanan validasi sesi portal TKA: penanganan respons HTTP 200 dengan status *"Anda tidak memiliki akses"* dan auto re-authentication.
- **Perbaikan Hak Akses Auto-Updater Windows (Mengatasi [WinError 5] Access is Denied)**:
  - Mengalihkan direktori unduhan sementara (`temp_update`) dari folder instalasi terproteksi (`C:\Program Files (x86)\...`) ke direktori pengguna yang aman (`%LOCALAPPDATA%\SmartTKAScanner\updates`), sehingga proses unduh dan ekstraksi tidak pernah ditolak izinnya oleh Windows.
  - Menambahkan dukungan eksekusi otomatis dengan eskalasi hak administrator (*UAC Elevation* via `-Verb RunAs`) khusus saat aplikasi terpasang di folder sistem `Program Files`.
  - Menghentikan proses aplikasi lama secara tuntas (*clean shutdown*) sebelum menyalin berkas pembaruan untuk mencegah penguncian berkas (*file locked*).

---

## [1.0.2] - 2026-10-28

### Diperbaiki (Fixed)
- **Perbaikan Tuntas Unggah Berkas Portal TKA**:
  - Mengembalikan nama field multipart file menjadi `absen1_file` (untuk Daftar Hadir) dan `gambar_file` (untuk Berita Acara Pelaksanaan/BAP) disertai parameter teks `absen1` dan `gambar` sesuai spesifikasi backend CodeIgniter portal TKA Kemendikdasmen.
  - Mengatasi galat `"Upload Gagal !"` (100% berkas terunggah sukses dan terverifikasi di portal).
- **Penanganan Verifikasi Keamanan Interaktif (CAPTCHA Challenge)**:
  - Deteksi otomatis saat portal mengaktifkan verifikasi CAPTCHA (`showSecure: true` / `"Kode keamanan tidak sesuai"`).
  - Penambahan form visual CAPTCHA di Pengaturan Portal dan Panduan Setup Awal lengkap dengan gambar kode dan tombol muat ulang (*Refresh*).
  - Endpoint baru `/api/portal/captcha` dan `/api/portal/login` yang mendukung transmisi kode keamanan langsung dari UI.

### Ditambahkan (Added)
- **Penyelarasan Tema Scrollbar Modern (Sleek Theme Scrollbars)**:
  - Menggantikan scrollbar default Windows abu-abu terang yang kaku dengan scrollbar ramping (*thin* 5-6px), sudut melengkung halus, dan transparansi adaptif.
  - Sidebar dan terminal log gelap (`#uploadLogTerminal`, `.bg-dark`) kini menggunakan scrollbar putih transparan semi-matte yang senada dengan latar navy gelap.
  - Tabel antrean, riwayat unggah, dan modal preview menggunakan scrollbar slate halus yang menyatu dengan tema terang aplikasi.
- **Penghapusan Aman Berkas Scan Saat Kosongkan Antrean**:
  - Dialog konfirmasi cerdas saat mengosongkan antrean: memeriksa status berkas dan membedakan antara berkas yang sudah terunggah (`UPLOADED`) vs berkas tertunda (`READY`, `FAILED`, `NEEDS_REVIEW`).
  - Peringatan eksplisit risiko kehilangan berkas asli jika scanner menyimpan hasil pemindaian langsung ke direktori `inbox/`.
  - Pilihan tindakan yang aman: opsi hapus berkas fisik yang sudah sukses saja, simpan berkas fisik (hanya bersihkan tampilan), atau hapus semua dengan konfirmasi ganda.
  - Proteksi keamanan backend terhadap *path traversal* (`is_safe_inbox_file`) yang menjamin tidak ada berkas di luar `inbox/` yang dapat terhapus.
- **Penyederhanaan Navigasi & Menu Pengaturan Terpadu**:
  - Mengubah menu samping menjadi **"Pengaturan"** (`fa-gear`) yang mencakup semua kontrol scanner, portal, OCR, dan pembaruan.
  - Menghapus tombol menu *"Panduan Setup Awal"* yang redundan dari sidebar; modal setup otomatis berjalan saat aplikasi pertama kali dijalankan (belum terkonfigurasi).
- **Pemulihan Sesi Persisten (Zero-Friction Session Restore)**:
  - Menyimpan cookie sesi terautentikasi dan token CSRF secara lokal (`.tka_session.json`) dengan pengamanan `.gitignore`.
  - Aplikasi langsung mengenali sesi aktif saat dibuka kembali tanpa perlu login ulang atau memicu CAPTCHA berulang kali.
  - Verifikasi otomatis koneksi portal sebelum menjalankan antrean unggah batch.

---

## [1.0.1] - 2026-10-28

### Diperbaiki (Fixed)
- **Sinkronisasi Jadwal & Proteksi CSRF/Anti-Replay**:
  - Penangkapan token CSRF aktif secara bersih dari navigasi browser `/user/home`.
  - Injeksi dinamis header unik `X-REQUEST-ID` dan `X-CSRF-TOKEN` untuk mencegah penolakan server (HTTP 403).
  - Penguraian otomatis kode sekolah (`kd_jenjang`, `kd_prop`, `kd_kota`, `kd_sek`) dari username proktor.
- **Tampilan Ikon Aplikasi Windows (Taskbar & Start Menu)**:
  - Pembuatan favicon dan ikon aplikasi multi-resolusi (16x16, 24x24, 32x32, 48x48, 64x64, 128x128, 256x256).
  - Registrasi `SetCurrentProcessExplicitAppUserModelID` di `desktop_app.py` agar icon taskbar Windows tidak revert ke dokumen putih kosong.
  - Perbaikan jalur shortcut installer Inno Setup ke `{app}\favicon.ico`.

### Ditambahkan (Added)
- **Pembaruan Otomatis In-App (Zero-Data-Loss In-App Auto-Updater)**:
  - Mekanisme pembaruan aplikasi 1-klik di dalam antarmuka (seperti Antigravity / VS Code) tanpa perlu instalasi ulang manual.
  - Perlindungan mutlak data pengguna: tidak pernah menimpa `settings.json`, `inbox/`, `processed/`, atau `logs/`.
  - Fallback otomatis ke public web scraper saat GitHub unauthenticated API terkena rate limit (HTTP 403).
  - Tombol *Cek Update* di navbar atas dan sidebar dengan indikator download progresif.

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

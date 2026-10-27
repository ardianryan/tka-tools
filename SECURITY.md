# Security Policy

## 1. Supported Versions

Kami berkomitmen untuk menjaga keamanan utilitas ini. Hanya versi rilis terbaru yang secara aktif menerima pembaruan keamanan dan perbaikan bug:

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0.0 | :x:                |

---

## 2. Pelaporan Kerentanan (Reporting a Vulnerability)

Jika Anda menemukan potensi celah keamanan (vulnerability) atau kebocoran data pada proyek ini:

1. **JANGAN** membuat laporan publik melalui GitHub Issues.
2. Silakan laporkan secara privat melalui fitur **[GitHub Private Vulnerability Reporting](https://github.com/ardianryan/tka-tools/security/advisories/new)** atau hubungi pengelola repositori melalui kontak GitHub [@ardianryan](https://github.com/ardianryan).
3. Sertakan informasi berikut dalam laporan Anda:
   - Deskripsi rinci mengenai celah keamanan.
   - Langkah-langkah untuk mereproduksi masalah (Proof of Concept).
   - Dampak potensial terhadap sistem atau data lokal.
4. Tim kami akan meninjau laporan Anda dalam waktu **1 x 24 jam** dan memberikan update status perbaikan.

---

## 3. Kebijakan Keamanan & Privasi Data Lokal

Aplikasi ini dirancang dengan prinsip **Local-First & Zero-Telemetry**:

1. **Pemrosesan 100% Offline**:
   * Seluruh proses OCR (Optical Character Recognition) dan pencocokan teks berkas ujian dijalankan secara lokal di komputer pengguna (menggunakan Windows Media OCR / Tesseract).
   * Berkas citra scan **TIDAK PERNAH** dikirim ke server AI cloud pihak ketiga mana pun.

2. **Perlindungan Dokumen Ujian & Data Siswa**:
   * Repositori ini telah mengonfigurasi `.gitignore` ketat untuk memblokir folder `DokumenTKA/`, `inbox/`, `processed/`, dan `logs/` agar berkas scan fisik peserta ujian tidak sengaja terunggah ke repositori publik.

3. **Isolasi Jaringan Lokal (Localhost Binding)**:
   * Secara default, server dashboard internal terikat ketat pada alamat loopback `127.0.0.1` port `5000` dan tidak membuka akses ke jaringan publik luar tanpa konfigurasi manual dari pengguna.

4. **Kredensial & Rahasia Akun**:
   * Jangan pernah mengunggah atau membagikan file `settings.json` atau file `.env` yang memuat username dan kata sandi akun sekolah Anda.
   * Gunakan template `settings.example.json` untuk keperluan pengujian dan pengembangan bersama.

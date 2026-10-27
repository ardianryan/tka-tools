# Panduan Kontribusi (Contributing Guidelines)

Terima kasih telah meluangkan waktu untuk berkontribusi pada **Smart TKA Scanner & Auto-Uploader (`tka-tools`)**! Proyek ini terbuka bagi siapa saja yang ingin membantu mempermudah pekerjaan para proktor dan teknisi sekolah di seluruh Indonesia.

---

## 1. Kode Etik (Code of Conduct)

Dengan berpartisipasi dalam proyek ini, Anda setuju untuk mematuhi [Kode Etik (CODE_OF_CONDUCT.md)](CODE_OF_CONDUCT.md) kami. Harap selalu berkomunikasi secara sopan, konstruktif, dan saling menghargai.

---

## 2. Cara Berkontribusi

### A. Melaporkan Bug (Reporting Bugs)
1. Periksa tab [Issues](https://github.com/ardianryan/tka-tools/issues) untuk memastikan bug tersebut belum pernah dilaporkan.
2. Buat Issue baru dengan menyertakan:
   * Versi aplikasi dan sistem operasi (Windows 10/11, macOS, atau distro Linux).
   * Merek dan tipe scanner yang digunakan (misal: Epson L5290, Canon LiDE 300, dsb.).
   * Langkah-langkah reproduksi masalah.
   * Pesan error atau cuplikan log terminal (pastikan tidak memuat kata sandi atau data pribadi siswa).

### B. Mengusulkan Fitur Baru
* Ingin menambahkan dukungan protokol pemindai baru (seperti SANE / eSCL)?
* Ingin menyempurnakan akurasi OCR untuk format stempel / tulisan tangan tertentu?
* Silakan buka Issue baru dengan label `enhancement` dan jelaskan use-case serta usulan solusinya.

### C. Mengajukan Pull Request (PR)
1. **Fork** repositori ini ke akun GitHub Anda.
2. Buat branch baru untuk fitur Anda:
   ```bash
   git checkout -b feature/nama-fitur-baru
   ```
3. Lakukan perubahan kode secara rapi dan modular.
4. Pastikan aplikasi berjalan normal tanpa error:
   ```bash
   python -m unittest discover -s tests  # jika tersedia unit tests
   python desktop_app.py --headless       # uji server lokal
   ```
5. Commit perubahan dengan pesan yang jelas dan deskriptif:
   ```bash
   git commit -m "feat(ocr): improve regex pattern for regional room stamps"
   ```
6. Push ke branch Anda di GitHub:
   ```bash
   git push origin feature/nama-fitur-baru
   ```
7. Buka **Pull Request** ke branch `main` repositori utama dan jelaskan perubahan yang Anda buat.

---

## 3. Menyiapkan Lingkungan Pengembangan Lokal

1. **Clone Repositori:**
   ```bash
   git clone https://github.com/ardianryan/tka-tools.git
   cd tka-tools
   ```

2. **Buat Virtual Environment:**
   ```bash
   python -m venv venv
   # Di Windows:
   venv\Scripts\activate
   # Di macOS / Linux:
   source venv/bin/activate
   ```

3. **Install Dependensi:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Konfigurasi Lingkungan:**
   Salin `settings.example.json` menjadi `settings.json`:
   ```bash
   cp settings.example.json settings.json
   ```
   *(Ingat: `settings.json` sudah diabaikan oleh `.gitignore` sehingga tidak akan sengaja ter-commit).*

5. **Jalankan Aplikasi:**
   ```bash
   python desktop_app.py
   ```

---

## 4. Standar Kode & Kualitas

* **Gaya Penulisan Kode**: Ikuti standar PEP 8 untuk kode Python. Gunakan penamaan variabel dan fungsi yang jelas dan bermakna.
* **Anti-Slop**: Hindari komentar kode generik atau boilerplate berlebihan. Fokus pada kejelasan logika dan arsitektur modular.
* **Keamanan & Privasi**: Dilarang keras menyertakan berkas scan fisik peserta ujian atau kredensial akun sungguhan ke dalam commit atau pull request.

---

## 5. Lisensi Kontribusi

Seluruh kontribusi yang Anda kirimkan ke repositori ini akan dilisensikan di bawah ketentuan [MIT License](LICENSE).

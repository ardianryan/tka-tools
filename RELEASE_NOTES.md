# Release Notes — Smart TKA Scanner v1.1.0

🎉 **Smart TKA Scanner v1.1.0** menghadirkan pembaruan besar (*major feature release*) yang berfokus pada autentisitas dokumen resmi, mesin penempelan tanda tangan & stempel digital khusus Berita Acara (BAP), fitur unggah massal BAP sekali klik (*Batch Direct Upload*), visualisasi thumbnail foto matriks jadwal, serta peningkatan antarmuka yang bersih dan rapi.

---

## 🌟 Sorotan Fitur Utama (Highlights)

### 1. Unggah Massal Berita Acara yang Sudah Siap (*Batch Direct Upload BAP*)
* **Satu Klik untuk Puluhan Sesi**: Cukup klik tombol hijau **"Unggah Semua yang Siap"** di toolbar *Penugasan Dinamis*, sistem akan otomatis menempelkan tanda tangan dan stempel resmi lalu mengunggahnya secara berurutan ke portal TKA Kemendikdasmen.
* **Filter Kesiapan Cerdas**: Mendeteksi secara instan semua sesi yang status TTD-nya sudah **Lengkap** (proktor & pengawas ruang sudah memiliki berkas TTD aktif).
* **Modal Progres Real-Time**: Tampilan progress bar animasi dengan persentase penyelesaian, label sesi/petugas aktif, dan log detail per slot.
* **Opsi Fleksibel**: Pilihan filter berdasarkan gelombang tertentu serta opsi *"Lewati sesi yang sudah terunggah di portal"*.
* **Kontrol Pembatalan**: Tombol *Hentikan* kapan saja untuk menghentikan proses tanpa merusak berkas yang sudah berhasil terunggah.

### 2. Mesin Tanda Tangan & Stempel Otentik Format Resmi Portal
* **Format Vektor Asli**: Mengadopsi 100% tata letak dan stylesheet resmi cetak portal TKA (`cetak.min.css`), menghasilkan dokumen dengan ketajaman teks vektor sempurna tanpa kotak putih atau timpaan kasar.
* **Garis Bawah & Garis Dasar TTD Alami**: Nama dan NIP petugas dilengkapi garis bawah otentik, serta garis dasar tanda tangan permanen di mana citra TTD menempel tepat di atas garis seperti goresan pena di atas kertas.
* **Stempel Basah Transparan (*Multiply Blending*)**: Penempelan cap stempel sekolah transparan dengan pengaturan ukuran, kepekatan, dan rotasi alami yang tumpang tindih secara wajar di atas tanda tangan Kepala Sekolah.
* **Smart Deduplication TTD**: Tanda tangan cukup diunggah 1x per nama/NIP petugas; jika ada kesamaan nama/NIP di sesi lain, sistem otomatis menggunakannya kembali tanpa perlu unggah ulang.
* **Ekspor PDF & Direct Print**: Dokumen BAP dapat dicetak langsung ke printer fisik atau diunduh sebagai berkas PDF vektor berkualitas tinggi.

### 3. Kepatuhan Ketat Tanda Tangan Fisik Daftar Hadir (DH Compliance)
* **Keamanan & Integritas Dokumen**: Injeksi tanda tangan & stempel digital **secara ketat hanya berlaku untuk Berita Acara Pelaksanaan (BAP)**.
* **Daftar Hadir (DH)** tetap wajib menggunakan lembar fisik hasil pemindaian scanner ADF/Flatbed karena memerlukan tanda tangan basah asli dari para peserta ujian. Backend memvalidasi dan menolak injeksi digital pada berkas selain BAP.

### 4. Matriks Jadwal Sesi dengan Thumbnail Foto Berkas & Interactive Lightbox
* Kolom Berita Acara dan Daftar Hadir pada tabel 96 Sesi kini menampilkan **thumbnail foto fisik berkas nyata** yang telah diunggah.
* Klik pada foto untuk membuka **Interactive Lightbox Modal** resolusi tinggi dengan kemampuan zoom, rotasi citra (90°, 180°, 270°), inspeksi metadata, dan unduh/cetak ulang.

### 5. Presisi Layout & Pembersihan Antarmuka (*UI Hygiene*)
* **Perataan Baris ID Server & Ruang**: ID Server dan Ruang kini sejajar sempurna pada baris yang sama tanpa teks nomor lab merosot ke bawah.
* **Anti-Margin Clipping**: Penataan margin simetris A4 (15mm) dan `box-sizing: border-box` mencegah margin kanan terpotong pada hasil cetak printer maupun render JPG.
* **Pembersihan Redundansi NIP**: Regex sanitizer membersihkan duplikasi teks awalan `"NIP."`, memastikan format NIP tercetak rapi.
* **Anti-Oversharing UI**: Menghapus badge `v1.1` dan `Baru` serta label versi berulang pada seluruh header dan tabel, menyajikan tampilan yang elegan dan bersih.

---

## 📦 Berkas Unduhan Rilis (Assets)

| Berkas | Ukuran | Deskripsi |
| :--- | :--- | :--- |
| **`SmartTKAScanner-Setup-v1.1.0.exe`** | ~22 MB | **Installer Resmi Windows (Rekomendasi)** — Otomatis memasang shortcut Desktop & Start Menu, mendukung pembaruan tanpa menimpa data pengaturan / TTD pengguna. |
| **`SmartTKAScanner-v1.1.0-Windows-x64.zip`** | ~60 MB | **Portable Windows Package** — Ekstrak ke folder mana pun dan langsung jalankan `SmartTKAScanner.exe` tanpa instalasi. |

---

## 🛠️ Catatan Pembaruan (Upgrade Notes)

Bagi pengguna yang telah memasang versi sebelumnya:
1. Anda dapat langsung menjalankan installer `SmartTKAScanner-Setup-v1.1.0.exe` di atas versi lama.
2. Seluruh pengaturan akun proktor, data master tanda tangan petugas, stempel sekolah, dan sesi login Anda tersimpan aman di `%APPDATA%\SmartTKAScanner` dan **TIDAK AKAN HILANG** ataupun terhapus oleh proses pembaruan.

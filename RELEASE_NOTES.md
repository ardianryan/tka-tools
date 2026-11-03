# Release Notes — Smart TKA Scanner v1.1.1

🎯 **Smart TKA Scanner v1.1.1** adalah rilis perbaikan kritis (*critical maintenance release*) yang menyelesaikan masalah penimpaan berkas lintas gelombang (Gelombang 2 menimpa Gelombang 1) pada saat pengunggahan Daftar Hadir & BAP, integrasi pemetaan tanggal dinamis dari portal BAP, presisi garis bawah cetak dokumen resmi, dan penyempurnaan batas cetak printer.

---

## 🌟 Sorotan Pembaruan (v1.1.1)

### 1. Perbaikan Timpa Gelombang (*Cross-Gelombang Overwrite Protection*)
* **Dynamic Date Mapping dari Portal BAP**: Sistem mengekstrak tanggal resmi per gelombang dan hari langsung dari endpoint BAP portal (`/api/v2/pelaksanaan/cetak`). Jadwal Oktober otomatis dikenali sebagai Gelombang 1, sedangkan jadwal November otomatis dikenali sebagai Gelombang 2.
* **OCR Gelombang Inference**: OCR Engine mendeteksi bulan pelaksanaan dari lembar fisik Daftar Hadir. Dokumen dengan bulan November otomatis dikunci ke Gelombang 2, dan Oktober ke Gelombang 1.
* **Bobot Pencocokan & Penalti Ketat**: Pencocokan slot jadwal kini memberikan bobot prioritas (+45) pada kesesuaian gelombang dan penalti (-80) untuk slot beda gelombang, serta pencocokan tanggal eksak (+35).
* **Isolasi Antrean Duplikat**: Berkas Gelombang 2 tidak akan pernah lagi dianggap sebagai duplikat rangkap dari Gelombang 1.

### 2. Autentisitas Format BAP Cetak & Ekspor
* **Garis Bawah Petugas Tegas (1.2px solid)**: Garis bawah pada nama dan NIP proktor, pengawas, dan penanggung jawab dijamin tercetak tajam pada printer fisik.
* **Perataan Baris ID Server & Ruang**: Teks Ruang (`Lab 1` dsb) dijamin sejajar sempurna dengan ID Server tanpa merosot ke bawah.
* **Batas Tepi Cetak Aman (Anti-Cutoff)**: Padding A4 disesuaikan menjadi 12mm simetris untuk memastikan sisi kanan lembar dokumen tidak terpotong pada printer Epson L-series / inkjet maupun saat konversi ke citra JPEG.
* **Sanitasi NIP Tunggal**: Memastikan tidak ada pengulangan kata `"NIP."` pada baris nomor NIP petugas.

---

## 📦 Berkas Unduhan Rilis (Assets)

| Berkas | Ukuran | Deskripsi |
| :--- | :--- | :--- |
| **`SmartTKAScanner-Setup-v1.1.1.exe`** | ~22 MB | **Installer Resmi Windows (Rekomendasi)** — Otomatis memasang shortcut Desktop & Start Menu, pembaruan aman tanpa menimpa data pengaturan pengguna. |
| **`SmartTKAScanner-v1.1.1-Windows-x64.zip`** | ~60 MB | **Portable Windows Package** — Ekstrak dan jalankan langsung tanpa instalasi. |

---

## 🛠️ Catatan Pembaruan (Upgrade Notes)
Instalasi versi 1.1.1 dapat langsung ditumpuk (*in-place update*) di atas versi sebelumnya. Seluruh pengaturan sesi, data scan, dan berkas tanda tangan yang sudah tersimpan akan tetap aman terjaga.

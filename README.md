# BPIC17 Analyzer

**Aplikasi Desktop untuk Analisis Event Log BPI Challenge 2017**

BPIC17 Analyzer merupakan aplikasi desktop yang dikembangkan menggunakan Python dan PM4Py untuk melakukan analisis terhadap event log BPI Challenge 2017 (BPIC17) dalam format XES.

Aplikasi ini dikembangkan sebagai proyek kelompok untuk menjawab latihan pada Bab 11 materi *Fundamentals of Business Process Management (FBPM)*. Analisis dilakukan secara dinamis berdasarkan dataset yang diimpor pengguna, kemudian hasilnya ditampilkan melalui antarmuka grafis.

## Tujuan Proyek

1. Mengimpor dan memvalidasi event log dalam format XES.
2. Menampilkan informasi umum dan statistik dasar event log.
3. Menghitung hasil latihan berdasarkan aturan analisis yang telah ditentukan.
4. Menampilkan daftar case dan bukti event yang mendasari hasil analisis.
5. Menyediakan aplikasi desktop yang dapat digunakan untuk mengeksplorasi dan menganalisis event log.

## Cakupan Fitur

| Kode | Fitur | Deskripsi |
|---|---|---|
| F01 | Impor dan Validasi Event Log | Mengimpor file XES, memvalidasi atribut wajib, dan mendeteksi atribut opsional. |
| F02 | Event Log Overview | Menampilkan jumlah case, event, frekuensi aktivitas, rentang waktu, dan rata-rata cycle time. |
| F03 | Exercise 11.7 A–E | Menganalisis jumlah case, cycle time, successful, unsuccessful, dan canceled cases. |
| F04 | Repeated Activity (11.15) | Mengidentifikasi case dengan aktivitas W_Assess Potential Fraud berstatus complete minimal dua kali. |
| F05 | Same Resource (11.18) | Mengidentifikasi pengulangan aktivitas complete yang dilakukan oleh resource yang sama. |
| F06 | Event Ordering (11.22) | Mengidentifikasi case dengan O_Cancelled yang kemudian diikuti O_Accepted. |
| F07 | Case Explorer dan Ekspor | Menampilkan detail case, urutan event, pencarian case, bukti analisis, dan ekspor hasil. |

## Pembagian Tugas Anggota

| Anggota | Tanggung Jawab | Cakupan |
|---|---|---|
| Binar | Impor XES, validasi, dan Event Log Overview | F01–F02 |
| Tiwi | Analisis jumlah case dan cycle time | Exercise 11.7 A–B |
| Hana | Analisis successful, unsuccessful, dan canceled cases | Exercise 11.7 C–E |
| Annis | Analisis repeated complete dan same resource | Exercise 11.15 dan 11.18 |
| Kayla | Analisis event ordering dan Case Explorer | Exercise 11.22 dan F07 |

## Teknologi yang Digunakan

| Teknologi | Kegunaan |
|---|---|
| Python | Bahasa pemrograman utama |
| PM4Py | Membaca dan memproses event log XES |
| Pandas | Pengolahan dan analisis data |
| PySide6 | Pembuatan antarmuka aplikasi desktop |
| Matplotlib | Visualisasi statistik dan aktivitas |

## Struktur Proyek

```text
BPIC17-Analyzer/
├── app.py
├── requirements.txt
├── README.md
├── .gitignore
│
├── modules/
│   ├── __init__.py
│   ├── importer.py
│   ├── overview.py
│   ├── exercise_11_7_ab.py
│   ├── exercise_11_7_ce.py
│   └── exercise_11_15_18.py
│
├── tests/
│   ├── test_importer.py
│   ├── test_overview.py
│   ├── test_exercise_11_7_ab.py
│   ├── test_exercise_11_7_ce.py
│   └── test_exercise_11_15_18.py
│
└── assets/
    └── ...
```

Keterangan:
- `app.py`: Aplikasi utama dan penghubung antarmodul.
- `requirements.txt`: Daftar dependency yang diperlukan.
- `modules/`: Tempat penyimpanan modul analisis setiap anggota.
- `assets/`: Tempat penyimpanan aset aplikasi apabila diperlukan.

File dan submodul tambahan akan dimasukkan sesuai perkembangan implementasi masing-masing fitur.

## Instalasi

### 1. Clone repository

```bash
git clone https://github.com/Binarri/BPIC17-Analyzer
cd BPIC17-Analyzer
```

### 2. Buat virtual environment

```bash
python -m venv .venv
```

### 3. Aktifkan virtual environment

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Windows Command Prompt:

```cmd
.venv\Scripts\activate.bat
```

### 4. Instal dependency

```bash
pip install -r requirements.txt
```

## Menjalankan Aplikasi

Jalankan perintah berikut dari direktori utama proyek:

```bash
python app.py
```

Setelah aplikasi terbuka, pengguna dapat mengimpor dataset BPIC17 berformat `.xes` melalui menu Dataset. Hasil analisis akan ditampilkan berdasarkan fitur yang telah diimplementasikan.

## Dataset

Proyek ini menggunakan dataset **BPI Challenge 2017 (BPIC17)** dalam format `.xes`.

- [BPI Challenge 2017 – 4TU.ResearchData](https://data.4tu.nl/articles/dataset/BPI_Challenge_2017/12696884)

## Ketentuan Analisis

Beberapa ketentuan yang digunakan dalam pengembangan aplikasi:

- Seluruh hasil analisis dihitung berdasarkan dataset XES yang sedang aktif.
- Jumlah case dihitung berdasarkan case ID unik, bukan jumlah event.
- Cycle time dihitung dari timestamp event terakhir dikurangi timestamp event pertama pada setiap case.
- Filter contains digunakan untuk memilih case yang memiliki aktivitas tertentu.
- Filter endpoint digunakan untuk memilih case berdasarkan aktivitas terakhir dalam trace.
- Pengulangan aktivitas hanya dihitung berdasarkan lifecycle complete sesuai ketentuan soal.
- Analisis same resource mensyaratkan resource yang sama dan teridentifikasi.
- Analisis eventually follows memperhatikan urutan event dalam trace, tanpa mengharuskan kedua event bersebelahan.

## Pengujian

Unit test untuk importer, overview, Exercise 11.7 A–E, serta Exercise 11.15 dan 11.18 menggunakan log sintetis agar aturan analisis dapat diuji secara terkontrol. Jalankan dari folder utama proyek:

```bash
python -m pytest tests -v
```

Pengujian dengan dataset BPIC17 asli tetap perlu dilakukan melalui aplikasi setelah dependency terpasang. Simpan hasil angka, screenshot, dan bukti case dari dataset yang digunakan untuk dokumentasi proyek.

Beberapa skenario yang perlu diuji:

1. Case memiliki aktivitas O_Accepted lebih dari satu kali.
2. O_Cancelled muncul di tengah trace dan masih diikuti event lainnya.
3. Case memiliki O_Refused sekaligus O_Accepted.
4. Aktivitas target memiliki beberapa occurrence, tetapi hanya satu yang berstatus complete.
5. Dua complete occurrence dilakukan oleh resource berbeda.
6. Dua complete occurrence dilakukan oleh resource yang sama.
7. O_Cancelled diikuti aktivitas lain sebelum O_Accepted.

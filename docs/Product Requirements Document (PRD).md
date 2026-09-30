# Product Requirements Document (PRD)
## Local ESP32 Compiler & Firmware Generator untuk Wokwi

**Versi:** MVP v1.0  
**Status:** Draft siap implementasi  
**Target platform:** Web Browser + Local Agent  
**Primary user:** Peserta kelas IoT pemula

---

## 1. Ringkasan Produk

Produk ini adalah **web application ringan** yang memungkinkan pengguna menulis atau menempelkan kode ESP32 melalui browser, kemudian melakukan proses compile secara lokal melalui aplikasi **Local Agent** yang berjalan di komputer pengguna.

Local Agent bertindak sebagai bridge antara browser dan toolchain **PlatformIO**. Setelah menerima source code dan konfigurasi dari web app, Local Agent:

1. Membuat project PlatformIO sementara.
2. Menghasilkan konfigurasi `platformio.ini` secara otomatis.
3. Menyiapkan environment ESP32 yang diperlukan.
4. Memeriksa dan mengelola dependency/library.
5. Menjalankan proses compile secara lokal.
6. Menghasilkan firmware binary.
7. Menggabungkan binary yang diperlukan menggunakan `merge_bin`/esptool.
8. Mengembalikan firmware dan compiler log ke browser.

Pengguna kemudian mengunduh firmware tersebut dan melakukan upload secara manual ke Wokwi menggunakan fitur resmi:

**F1 → Upload Firmware and Start Simulation**

Produk tidak mengintegrasikan proses upload firmware ke Wokwi pada MVP.

---

# 2. Latar Belakang

Dalam kegiatan pembelajaran IoT, peserta kelas menggunakan Wokwi sebagai simulator untuk menjalankan kode ESP32.

Salah satu hambatan yang berulang adalah **waktu tunggu compile cloud Wokwi**, terutama ketika server sedang sibuk pada jam praktikum.

Alternatif yang tersedia memang memungkinkan proses build lokal, tetapi memiliki tingkat kompleksitas yang tinggi bagi pemula. Contohnya:

- Arduino IDE membutuhkan konfigurasi board secara manual.
- VS Code + PlatformIO membutuhkan instalasi IDE dan extension.
- Pengguna perlu memahami konfigurasi `platformio.ini`.
- Sebagian workflow membutuhkan pemahaman command line.
- Peserta pemula juga kesulitan memahami raw compiler error.

Akibatnya, waktu yang seharusnya digunakan untuk belajar dan bereksperimen dapat terbuang untuk menunggu proses compile atau menyelesaikan konfigurasi environment.

---

# 3. Problem Statement

> Peserta kelas IoT pemula membutuhkan cara yang sederhana untuk melakukan compile kode ESP32 secara lokal sebelum menjalankannya di Wokwi, karena waktu tunggu compile cloud Wokwi dapat menghambat proses praktikum, sementara solusi compile lokal yang tersedia memiliki kompleksitas setup yang terlalu tinggi bagi pengguna pemula.

---

# 4. Product Goal

Menyediakan workflow compile ESP32 lokal yang:

- sederhana bagi pengguna pemula,
- tidak bergantung pada server compile Wokwi,
- mengotomatisasi konfigurasi PlatformIO,
- menghasilkan firmware yang dapat digunakan di Wokwi,
- memberikan feedback error yang tetap transparan,
- dan memiliki setup awal seminimal mungkin.

Empirical Validation — Temuan Eksperimen Fase 0

Sebelum keputusan arsitektur pada dokumen ini diambil, telah dilakukan serangkaian eksperimen langsung untuk memvalidasi asumsi teknis, bukan berdasarkan asumsi semata.

Setup Environment
Aspek	Hasil Terukur
Ukuran total environment (toolchain-xtensa-esp32 + framework-arduinoespressif32 + tool-esptoolpy + tool-scons)	916 MB
Waktu initial provisioning (unduhan pertama, tergantung jaringan)	±25 menit
Waktu compile pertama pada project baru (framework di-compile ulang)	±51 detik
Waktu compile incremental (project sama, sudah ada .pio/build)	±10 detik
Temuan Portabilitas Environment

Environment (packages_dir PlatformIO) diuji dengan cara disalin ke lokasi lain di mesin yang sama, lalu dipakai oleh project baru dengan PLATFORMIO_CORE_DIR diarahkan ke salinan tersebut.

Hasil:

Proses pio project init dan pio run pada environment hasil salinan berhasil tanpa mengunduh ulang apa pun (log menunjukkan "Already up-to-date"), mengonfirmasi tidak ada path absolut yang ter-hardcode ke lokasi asal folder.
Namun, hasil kompilasi framework (.pio/build/.../FrameworkArduino/*.o) bersifat spesifik per-project, tidak ikut tersimpan di packages_dir. Ini yang menyebabkan compile pertama pada project baru (±51 detik) tetap lebih lambat dibanding compile incremental (±10 detik), meski environment sudah tersedia.

Catatan batasan pengujian: validasi di atas dilakukan pada mesin dan OS yang sama (relokasi path, bukan lintas komputer/OS berbeda). Validasi portabilitas lintas mesin/OS direncanakan sebagai bagian pengujian lapangan (lihat Section Future Validation).

Implikasi terhadap Desain Arsitektur

Temuan ini menjadi dasar keputusan pemisahan dua jenis environment pada Local Agent:

Base Compiler Environment — berisi toolchain, framework, dan tools (esptool, scons). Bersifat reusable lintas-project dan lintas-sesi, sesuai temuan portabilitas di atas.
Project Environment — berisi source code, platformio.ini, dan hasil build (.pio/build) spesifik per sesi pengguna. Tidak persisten/reusable, dibuat ulang setiap sesi compile baru.

Pemisahan ini memastikan pengguna tidak mengunduh ulang 916 MB environment pada setiap sesi, sekaligus menjelaskan mengapa compile pertama per-sesi tetap memakan waktu lebih lama daripada compile berikutnya dalam sesi yang sama.

Skema Distribusi Environment untuk Konteks Kelas (Kontribusi Tambahan)

Karena environment terbukti portable dalam mesin yang sama, terbuka kemungkinan skema distribusi environment yang sudah di-provision sebelumnya (pre-provisioned environment) ke banyak peserta dalam satu kelas, melalui media seperti flashdisk atau file share jaringan lokal (LAN), tanpa memerlukan setiap peserta mengunduh 916 MB secara mandiri dan bersamaan. Skema ini relevan khusus untuk konteks penggunaan kelas/laboratorium (bukan pengguna individu acak), dan direncanakan diuji langsung pada tahap validasi lapangan (Section Success Metrics / Metric 1 — Setup Time).

### Prinsip utama

> **Install once → Configure minimally → Compile locally → Download firmware → Upload to Wokwi**

---

# 5. Target Users

## 5.1 Primary User

### Peserta Kelas IoT Pemula

Karakteristik:

- baru belajar ESP32/Arduino;
- belum familiar dengan PlatformIO;
- tidak ingin mengatur toolchain secara manual;
- membutuhkan feedback compile dengan cepat;
- menggunakan Wokwi sebagai simulator pembelajaran.

### Kebutuhan utama

- setup sederhana;
- memilih board tanpa mengetahui Board ID PlatformIO;
- compile dengan satu aksi;
- memahami apakah build berhasil;
- mendapatkan firmware siap digunakan.

---

## 5.2 Secondary Users

### Pengajar IoT

Membutuhkan tool yang dapat mengurangi waktu terbuang selama praktikum dan mempermudah troubleshooting peserta.

### Mahasiswa

Dapat menggunakan sistem untuk eksperimen ESP32 tanpa konfigurasi development environment yang kompleks.

### Embedded Developer

Dapat menggunakan workflow sederhana untuk eksperimen atau pengujian kode ESP32.

---

# 6. Scope MVP

## Included

### Hardware

Hanya:

**ESP32 DevKit V1 / ESP32 Dev Module (`esp32dev`)**

### Framework

**Arduino**

### Platform

- Web browser
- Local Agent
- Linux sebagai prioritas development/testing
- Windows sebagai target MVP

### Core features

- Code editor
- Paste/write source code
- Board selection
- Framework selection
- Project name
- `#include` detection
- Library selection
- Local dependency cache
- Automatic PlatformIO configuration
- Local compilation
- Build progress/status
- Raw compiler log
- Basic error explanation
- Firmware generation
- Firmware download
- Wokwi upload instructions
- Local Agent security mechanism
- First-time setup wizard
- Environment caching

---

# 7. Out of Scope MVP

Hal berikut tidak termasuk MVP:

- ESP8266
- Arduino Uno
- Arduino Nano
- Raspberry Pi Pico
- STM32
- macOS
- Cloud compilation
- Backend/cloud server
- User account/login
- Database
- Automatic upload ke Wokwi
- Integrasi API Wokwi untuk menjalankan simulator
- AI/NLP untuk menerjemahkan seluruh compiler error
- Full IDE functionality
- Advanced PlatformIO configuration
- OTA flashing
- Physical ESP32 flashing
- Collaborative editing

Board dan framework tambahan dapat menjadi **future work**.

---

# 8. User Journey

## First-time user

```text
Install Local Agent
       ↓
Launch Agent
       ↓
Environment Check
       ↓
Install/prepare required dependencies
       ↓
Open Web App
       ↓
Connect to Local Agent
       ↓
Write/Paste Code
       ↓
Select ESP32 DevKit V1
       ↓
Select Arduino
       ↓
Detect #include
       ↓
Select missing libraries
       ↓
Compile
       ↓
Build Result
       ↓
Download Firmware
       ↓
Follow Wokwi Instructions
       ↓
Upload Firmware to Wokwi
       ↓
Start Simulation
```

## Subsequent use

```text
Open Web App
    ↓
Connect Local Agent
    ↓
Write/Paste Code
    ↓
Select Board
    ↓
Compile
    ↓
Use cached environment/dependencies
    ↓
Download Firmware
    ↓
Upload to Wokwi
```

---

# 9. Functional Requirements

## FR-01 — Code Editor

Website harus menyediakan editor untuk:

- menulis kode;
- paste kode;
- editing dasar;
- syntax highlighting untuk C/C++;
- line number;
- clear/reset code.

Editor harus tetap ringan agar tidak membuat web application terlalu berat.

---

## FR-02 — Board Selection

User memilih board melalui nama yang mudah dipahami.

Contoh:

**ESP32 DevKit V1**

Sistem memetakan pilihan tersebut secara internal menjadi:

`esp32dev`

User tidak perlu mengetahui Board ID PlatformIO.

---

## FR-03 — Framework Selection

Untuk MVP:

**Arduino**

Konfigurasi framework dibuat otomatis oleh Local Agent.

---

## FR-04 — Project Configuration

User dapat menentukan nama project secara sederhana.

Contoh:

`My ESP32 Project`

Detail teknis project tidak perlu ditampilkan kepada user pemula.

---

# 10. Library Management

## FR-05 — Include Detection

Sistem membaca source code dan mendeteksi statement seperti:

```cpp
#include <DHT.h>
#include <WiFi.h>
```

Detection dilakukan sebelum proses build.

---

## FR-06 — Missing Library Detection

Jika library yang dibutuhkan belum tersedia, sistem memberikan informasi kepada pengguna.

Contoh:

> Library `DHT.h` belum tersedia.

Kemudian user dapat memilih library yang sesuai.

---

## FR-07 — Library Selection

User dapat memilih library melalui UI tanpa perlu menulis:

```ini
lib_deps =
```

atau konfigurasi PlatformIO secara manual.

---

## FR-08 — PlatformIO Registry

Jika library belum tersedia di cache:

```text
Local Cache
    ↓ miss
PlatformIO Registry
    ↓
Download
    ↓
Local Cache
    ↓
Build
```

Jika library tersedia:

```text
Local Cache
    ↓ hit
Build
```

---

# 11. Dependency Cache

Local Agent harus menyediakan cache untuk:

- PlatformIO packages;
- board environment;
- library/dependency.

Tujuannya mengurangi download berulang.

### Prinsip

**First use:**

> Download → Install → Cache

**Subsequent use:**

> Cache hit → Reuse → Build

Cache harus mempertimbangkan versi dependency agar dependency yang berbeda tidak tertukar.

---

# 12. Automatic PlatformIO Configuration

Local Agent membuat project PlatformIO berdasarkan konfigurasi sederhana yang dikirim browser.

Contoh konseptual:

```ini
[env:esp32dev]
platform = espressif32
board = esp32dev
framework = arduino
```

Detail aktual konfigurasi dikelola oleh Local Agent dan dapat berkembang sesuai kebutuhan implementasi.

User tidak perlu mengedit `platformio.ini`.

---

# 13. Local Build

Ketika user menekan:

**Compile**

browser mengirim request ke Local Agent.

Contoh alur:

```text
Browser
   │
   │ POST /api/build
   ↓
Local Agent
   │
   ├── Create temporary project
   ├── Generate platformio.ini
   ├── Resolve dependencies
   ├── Prepare environment
   └── Execute PlatformIO
           │
           ↓
       Compiler
           │
           ↓
       Firmware
```

---

# 14. Build Output

Jika berhasil, sistem harus mengembalikan minimal:

- status build;
- build duration;
- firmware binary;
- ukuran firmware;
- compiler/build log.

Firmware harus dapat diunduh sebagai file yang sesuai untuk workflow Wokwi.

---

# 15. Firmware Generation

Setelah proses compile, Local Agent menggunakan tool yang diperlukan, termasuk **esptool/`merge_bin`**, untuk menghasilkan firmware gabungan yang dapat digunakan dalam workflow upload firmware Wokwi.

Output utama:

> **Download Firmware**

---

# 16. Error Handling

Raw compiler error **tidak boleh disembunyikan**.

User tetap dapat melihat output compiler asli untuk kebutuhan debugging dan membantu pengajar.

Contoh:

```text
fatal error: DHT.h: No such file or directory
```

Sistem kemudian dapat menambahkan penjelasan sederhana.

### Contoh

**Compiler error:**

> `fatal error: DHT.h: No such file or directory`

**Kemungkinan penyebab:**

> Library DHT belum tersedia pada project.

**Saran:**

> Tambahkan library DHT melalui menu Library.

---

# 17. Basic Error Mapping

MVP hanya menyediakan mapping untuk sekitar **3–5 pola error umum**.

Contoh kategori:

1. Library/header tidak ditemukan.
2. Syntax error sederhana.
3. Missing semicolon.
4. Board/configuration mismatch.
5. Dependency/configuration error yang sudah diketahui.

Implementasi menggunakan:

- string matching;
- regex/pattern matching;
- rule-based mapping.

Tidak menggunakan AI generatif atau NLP.

### Future Work

Sistem penerjemahan error yang lebih komprehensif dapat dikembangkan menggunakan pendekatan NLP/AI pada penelitian lanjutan.

---

# 18. Local Agent

Local Agent adalah aplikasi/service yang berjalan pada komputer pengguna.

Tanggung jawab:

- menerima request dari browser;
- memvalidasi request;
- mengelola project sementara;
- membuat konfigurasi PlatformIO;
- mengelola dependency;
- mengelola cache;
- menjalankan PlatformIO;
- menghasilkan firmware;
- mengembalikan log dan hasil build.

Local Agent merupakan satu-satunya komponen backend dalam MVP.

---

# 19. API Architecture

Komunikasi:

```text
Browser
   │
   │ HTTP localhost
   ↓
Local Agent
   │
   ↓
PlatformIO
```

Tidak terdapat:

- cloud backend;
- application server;
- database;
- authentication server.

Contoh endpoint konseptual:

```text
GET  /api/status
POST /api/build
POST /api/libraries/check
POST /api/libraries/install
GET  /api/build/:id/status
GET  /api/build/:id/log
GET  /api/build/:id/firmware
```

Endpoint aktual dapat disesuaikan selama implementasi.

---

# 20. Local Agent Security

Karena service membuka API pada localhost, Local Agent tidak boleh menerima request secara bebas.

MVP menggunakan:

### Origin Allowlist

Hanya origin web application resmi yang diizinkan melakukan request.

### Local Session Token

Saat pertama kali Local Agent berjalan, sistem membuat random local session token.

Browser harus melakukan mekanisme handshake sebelum mengakses fungsi sensitif.

Token:

- dibuat secara lokal;
- tidak membutuhkan server authentication;
- tidak dikirim ke cloud;
- digunakan untuk memvalidasi request dari web app.

Tujuan utama:

> Mencegah website lain yang dibuka di browser mencoba menjalankan compile atau menyalahgunakan kemampuan Local Agent tanpa persetujuan pengguna.

---

# 21. Setup Wizard

Local Agent harus menyediakan proses setup pertama kali.

### Step 1 — Environment Check

Memeriksa:

- Python;
- PlatformIO;
- dependency yang dibutuhkan.

### Step 2 — Prepare Environment

Jika dependency belum tersedia, sistem melakukan provisioning.

### Step 3 — Board Environment

Environment ESP32 hanya disiapkan ketika dibutuhkan.

### Step 4 — Cache

Environment yang sudah berhasil dipasang disimpan untuk penggunaan berikutnya.

Target UX:

> **Install Local Agent sekali → Setup otomatis → Compile**

---

# 22. Wokwi Integration

MVP **tidak melakukan automatic upload ke Wokwi**.

Setelah firmware berhasil dibuat, website menampilkan:

### Step 1
Download firmware.

### Step 2
Buka project Wokwi.

### Step 3
Tekan:

**F1**

### Step 4

Pilih:

**Upload Firmware and Start Simulation**

### Step 5

Pilih firmware hasil download.

Instruksi dapat dilengkapi screenshot/visual guide agar mudah diikuti pemula.

---

# 23. Non-Functional Requirements

## NFR-01 — Performance

Web application harus ringan.

Prinsip:

- static web app;
- tidak membutuhkan backend;
- tidak melakukan compilation di browser;
- asset seminimal mungkin;
- tidak mengirim source code ke cloud;
- build dilakukan sepenuhnya oleh Local Agent.

---

## NFR-02 — Availability

Proses compile utama tidak bergantung pada availability atau load server Wokwi.

Internet hanya diperlukan ketika:

- melakukan setup awal tertentu;
- mengunduh PlatformIO package;
- mengunduh library yang belum tersedia;
- aktivitas online lain yang memang diperlukan.

Setelah dependency tersedia di cache, proses build dapat dilakukan secara lokal.

---

## NFR-03 — Cross Platform

MVP:

| Platform | Status |
|---|---|
| Linux | Prioritas development/testing |
| Windows | Target MVP |
| macOS | Future work |

---

## NFR-04 — Usability

Pengguna pemula seharusnya tidak perlu memahami:

- `platformio.ini`;
- Board ID;
- toolchain;
- command line;
- package manager;
- konfigurasi compiler.

---

## NFR-05 — Security

Local Agent harus:

- membatasi origin;
- menggunakan local session token;
- tidak membutuhkan akun cloud;
- tidak mengekspos API secara bebas kepada website lain;
- memvalidasi input build.

---

# 24. UX Structure

Struktur halaman MVP dapat dibuat sederhana:

### Header

**Local ESP32 Compiler**

Status:

> 🟢 Local Agent Connected

atau

> 🔴 Local Agent Not Connected

### Main Area

**Code Editor**

```text
┌─────────────────────────────────────┐
│ 1  #include <Arduino.h>             │
│ 2                                   │
│ 3  void setup() {                   │
│ 4      Serial.begin(115200);        │
│ 5  }                                │
│ ...                                 │
└─────────────────────────────────────┘
```

### Configuration

```text
Board
[ ESP32 DevKit V1 ▼ ]

Framework
[ Arduino ▼ ]

Project Name
[ My ESP32 Project ]

[ Compile ]
```

### Build Status

```text
Building...
████████████░░░░ 75%

Time: 4.82s
```

### Result

```text
✓ Build Successful

Firmware size: 234 KB
Build time: 4.82 seconds

[ Download Firmware ]
```

---

# 25. Failed Build UX

Jika build gagal:

```text
✕ Build Failed

Compiler Error

fatal error: DHT.h: No such file or directory
```

Kemudian:

```text
💡 What does this mean?

Library DHT belum tersedia.

[ Find/Add Library ]
```

Raw compiler output tetap tersedia:

```text
[ Show Full Compiler Log ]
```

---

# 26. Success Metrics

Penelitian menggunakan empat metrik utama.

## Metric 1 — Setup Time

Mengukur waktu dari:

> instalasi Local Agent → environment siap digunakan.

Minimal dibandingkan:

- first-time setup;
- subsequent use setelah cache tersedia.

---

## Metric 2 — Build/Compile Time

Membandingkan:

**Wokwi Cloud Compile**

vs.

**Local Agent Compile**

Pengujian harus menggunakan kondisi kode dan hardware target yang setara.

Variabel seperti:

- source code;
- board;
- dependency;
- kondisi cache;

harus dikontrol atau dicatat.

---

## Metric 3 — Build Success Rate

Mengukur:

> jumlah build berhasil / total percobaan build × 100%

Pengujian dapat menggunakan kumpulan source code yang representatif terhadap kode peserta kelas.

---

## Metric 4 — Usability

Menggunakan:

**System Usability Scale (SUS)**

Target responden dapat mencakup:

- peserta IoT pemula;
- mahasiswa;
- pengajar.

---

# 27. Experimental Comparison

Untuk skripsi, desain evaluasi dapat membandingkan minimal dua workflow:

### Baseline

```text
Code
 ↓
Wokwi Cloud Compile
 ↓
Simulation
```

### Proposed System

```text
Code
 ↓
Local Agent
 ↓
PlatformIO
 ↓
Firmware
 ↓
Manual Upload
 ↓
Wokwi Simulation
```

Pertanyaan penelitian yang dapat diturunkan:

> Apakah compile lokal menggunakan Local Agent dapat mengurangi waktu tunggu dibandingkan compile cloud Wokwi?

Dan:

> Apakah workflow compile lokal yang disederhanakan dapat digunakan oleh pengguna pemula dengan tingkat usability yang dapat diterima?

---

# 28. Suggested Research Variables

### Independent Variable

Metode compilation:

- Wokwi Cloud;
- Local Agent + PlatformIO.

### Dependent Variables

- waktu build;
- waktu setup;
- build success rate;
- SUS score.

### Controlled Variables

- board: ESP32 DevKit V1;
- framework: Arduino;
- source code;
- dependency;
- hardware specification;
- kondisi pengujian;
- komputer/network environment bila relevan.

---

# 29. Acceptance Criteria MVP

MVP dianggap berhasil apabila:

### AC-01

User dapat menginstal Local Agent tanpa melakukan konfigurasi PlatformIO secara manual.

### AC-02

Web app dapat mendeteksi Local Agent yang berjalan.

### AC-03

User dapat memilih ESP32 DevKit V1 dan Arduino tanpa mengetahui konfigurasi PlatformIO.

### AC-04

Source code dapat dikirim dari browser ke Local Agent.

### AC-05

Local Agent dapat membuat project PlatformIO secara otomatis.

### AC-06

Kode ESP32 Arduino dapat berhasil di-compile secara lokal.

### AC-07

Dependency yang belum tersedia dapat ditambahkan melalui workflow UI.

### AC-08

Dependency yang sudah tersedia dapat digunakan dari cache.

### AC-09

Build menghasilkan firmware yang dapat diunduh.

### AC-10

Firmware dapat digunakan melalui fitur resmi Wokwi **Upload Firmware and Start Simulation**.

### AC-11

Compiler log asli dapat dilihat pengguna.

### AC-12

Minimal 3–5 pola error umum dapat diberikan penjelasan sederhana.

### AC-13

Website tidak memerlukan backend/cloud server untuk proses build.

### AC-14

Local Agent menolak request dari origin yang tidak diizinkan.

### AC-15

Local Agent menggunakan local session token.

---

# 30. Technical Architecture

```text
┌─────────────────────────────────────┐
│              Browser                │
│                                     │
│  Code Editor                        │
│  Board Selection                    │
│  Framework Selection                │
│  Library UI                         │
│  Build Status                       │
│  Compiler Log                       │
│  Firmware Download                  │
│  Wokwi Instructions                 │
└──────────────────┬──────────────────┘
                   │
                   │ localhost API
                   │ + session token
                   ↓
┌─────────────────────────────────────┐
│            Local Agent              │
│                                     │
│ API Layer                           │
│ Security Layer                      │
│ Build Manager                       │
│ Dependency Manager                  │
│ Cache Manager                       │
│ Error Pattern Mapper                │
│ Firmware Generator                  │
└───────────────┬─────────┬───────────┘
                │         │
                ↓         ↓
        ┌────────────┐  ┌─────────────┐
        │ PlatformIO │  │ Local Cache │
        └─────┬──────┘  └─────────────┘
              │
              ↓
        ┌─────────────┐
        │ ESP32       │
        │ Toolchain   │
        └──────┬──────┘
               │
               ↓
        ┌─────────────┐
        │ esptool     │
        │ merge_bin   │
        └──────┬──────┘
               │
               ↓
          firmware.bin
```

---

# 31. Key Product Decisions

| Area | Decision |
|---|---|
| Primary user | IoT beginner |
| Build location | Local computer |
| Build engine | PlatformIO |
| Target board MVP | ESP32 DevKit V1 / `esp32dev` |
| Framework | Arduino |
| Website | Static web app |
| Backend | Local Agent |
| Cloud build | Tidak digunakan |
| Database | Tidak digunakan |
| Login | Tidak digunakan |
| Dependency source | PlatformIO Registry |
| Dependency cache | Ya |
| Board environment | Lazy provisioning |
| Firmware | Local binary |
| Firmware upload | Manual ke Wokwi |
| Wokwi API integration | Tidak |
| Error explanation | 3–5 common patterns |
| Error AI/NLP | Tidak untuk MVP |
| Security | Origin allowlist + local session token |
| Linux | Prioritas development/testing |
| Windows | MVP target |
| macOS | Future work |

---

# 32. Future Work

Setelah MVP stabil, pengembangan dapat mencakup:

1. macOS support.
2. ESP8266.
3. Arduino Uno/Nano.
4. Raspberry Pi Pico.
5. STM32.
6. Framework tambahan.
7. Automatic Wokwi integration jika mekanisme resmi memungkinkan.
8. Advanced dependency resolution.
9. Comprehensive compiler error explanation.
10. AI-assisted compiler error explanation.
11. Project persistence.
12. Cloud/project sharing.
13. Physical ESP32 flashing.
14. Advanced PlatformIO configuration.

---

# 33. Risiko dan Mitigasi

| Risiko | Dampak | Mitigasi |
|---|---|---|
| PlatformIO setup gagal | Tinggi | Setup wizard + environment validation |
| Download dependency lambat | Sedang | Local cache |
| Cache corrupt | Sedang | Validasi/versioning + re-download |
| Dependency mismatch | Tinggi | Version-aware dependency management |
| Localhost API disalahgunakan | Tinggi | Origin allowlist + session token |
| Compiler error terlalu beragam | Sedang | Scope mapping hanya 3–5 pola |
| Binary tidak kompatibel dengan Wokwi | Tinggi | Standardisasi firmware generation + integration test |
| Web app terlalu berat | Sedang | Static architecture + minimal assets |
| Perbedaan Linux/Windows | Sedang | Linux sebagai development baseline, Windows compatibility testing |
| Provisioning pertama lama | Sedang | Lazy provisioning + cache/pre-provisioning |
| Scope melebar | Tinggi | Lock MVP pada ESP32 + Arduino |

---

# 34. Definition of Done

Produk MVP dapat dinyatakan selesai apabila seorang pengguna baru dapat melakukan workflow berikut tanpa perlu memahami PlatformIO:

> **Install Local Agent → buka website → pilih ESP32 DevKit V1 → pilih Arduino → paste kode → pilih library bila diminta → Compile → mendapatkan firmware → mengikuti panduan upload ke Wokwi → menjalankan simulasi.**

Dan seluruh proses build utama berlangsung **tanpa menggunakan server compile Wokwi**.

---

# 35. Core Value Proposition

> **“Compile kode ESP32 secara lokal dengan mudah, tanpa harus memahami PlatformIO, lalu gunakan firmware hasil compile langsung di Wokwi.”**

Produk bukan dimaksudkan untuk menggantikan Wokwi.

Produk berfungsi sebagai **local compilation layer** yang mengatasi bottleneck compile cloud sekaligus menyederhanakan kompleksitas toolchain untuk pengguna pemula.

---

# 36. Thesis/Research Positioning

Dari perspektif tugas akhir, kontribusi utama proyek dapat diposisikan bukan sekadar sebagai “website compiler”, melainkan:

> **Perancangan dan implementasi local-agent-based compilation workflow untuk menyederhanakan proses kompilasi ESP32 Arduino bagi pengguna pemula sebelum deployment firmware ke simulator Wokwi.**

Evaluasi kemudian berfokus pada empat dimensi:

**Performance**
→ Apakah waktu build dapat dikurangi?

**Setup Efficiency**
→ Seberapa besar overhead first-time setup dan bagaimana cache memengaruhi penggunaan berikutnya?

**Reliability**
→ Seberapa konsisten kode dapat berhasil dikompilasi?

**Usability**
→ Apakah pengguna pemula dapat menggunakan workflow tersebut tanpa kompleksitas PlatformIO?

Dengan positioning tersebut, proyek memiliki hubungan yang jelas antara **masalah → solusi → implementasi → eksperimen → metrik → kesimpulan penelitian**.

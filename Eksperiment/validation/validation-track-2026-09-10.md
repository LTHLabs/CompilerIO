# VALIDATION TRACK REPORT — V1–V8 (CompilerIO Local Agent)

**Tanggal:** 2026-09-10
**Sesi:** Satu sesi agen tunggal (cache setara antar build), 9 build total (8 sukses + 1 expected-failure)
**Peran:** Implementation & Verification Agent — VALIDATION track, zero perubahan kode
**Dasar:** PRD CompilerIO, profiling-run-2026-09-08, optimization1-run-2026-09-09
**Kode saat pengujian:** manifest path 4-scan (Opt-1), instrumentasi timing 4 metrik aktif

---

## 1. Objective

Membuktikan secara empiris perilaku build sistem pada 8 skenario validasi (V1 repeated, V2 unchanged, V3 changed, V4 failed, V5 recovery, V6 environment integrity, V7 artifact integrity, V8 cleanup/lifecycle) dalam satu sesi agen, memverifikasi Base Environment tidak berubah, dan menghasilkan report sesuai format 10 seksi. STOP setelah report.

## 2. Configuration

- Agent: uvicorn `app.main:app` 127.0.0.1:8765, satu sesi berkelanjutan (restart hanya di V8, by design).
- Board/framework: `esp32dev` + `arduino` (MVP). Origin `http://localhost:3000`. Token sesi via pairing.
- Source varian (pre-registered): BASE = blink 12 baris (identik baseline `85ed…`); CHANGED = + Serial.begin + const message + println + delay 500; BROKEN = missing semicolon `digitalWrite(2, HIGH) delay(2000);`.
- Covariate sesi: `t_scan_start` = 4.563/4.342 s; `t_scan_end` = 4.444/4.352 s (≈4.35–4.56 s, cache hangat, konsisten sepanjang sesi); manifest `digest_start` = `digest_end` (lihat V6).

## 3. Test Procedure

Eksekusi sesuai plan validasi tanpa deviasi: 5× POST /build (BASE) berurutan → analisis determinisme → 1× CHANGED → 1× BROKEN (expected fail) → 1× BASE (recovery) → scan+digest akhir → verifikasi struktural artifacts → du/ls akhir → restart agent → 404/NOT_READY/prepare-READY. Setiap build: poll status, GET log, environment/status, artifacts size+SHA-256 (python hashlib). Semua operasi read-only terhadap Base Environment. Zero edit file source agent.

## 4. Raw Measurements

### 4.1 Tabel metrik per build

| Build | ID | Status | setup_s | pio_s | merge_s | total_s | Took | fw.bin (B / SHA256-16) | wokwi (B / SHA256-16) | elf (B) | env post |
|---|---|---|---|---|---|---|---|---|---|---|---|
| V1#1 | 9193b076 | SUCCEEDED | 0.001 | 54.460 | 9.510 | 63.972 | 43.57 | 240320 / d1271c8afae65f3d | 305856 / 90bc9754ca604b12 | 5693524 | READY |
| V1#2 | 84e81a6d | SUCCEEDED | 0.001 | 53.321 | 9.360 | 62.683 | 42.74 | 240320 / eb37c574cddd7356 | 305856 / d28f7f3bd516722f4 | 5693524 | READY |
| V1#3 | f4b3221e | SUCCEEDED | 0.001 | 53.249 | 9.506 | 62.757 | 42.82 | 240320 / 16ebedf92de785d2 | 305856 / 59702ff9a7c23443 | 5693524 | READY |
| V1#4 | 65ccee4a | SUCCEEDED | 0.002 | 53.244 | 9.679 | 62.925 | 42.42 | 240320 / 623aabff9cf2c8c7 | 305856 / 9308dcf6792101c1 | 5693524 | READY |
| V1#5 | a2da1a6e | SUCCEEDED | 0.001 | 53.259 | 9.746 | 63.008 | 42.66 | 240320 / 086fc3621879ad95 | 305856 / d681b6e48e0e9ec8 | 5693524 | READY |
| V3 | 20d2d04e | SUCCEEDED | 0.001 | 52.455 | 9.217 | 61.673 | 42.09 | 269712 / fac03787a79ea74c | 335248 / 96355ed8be122d54 | 6071620 | READY |
| V4 | 13ca54a5 | **FAILED (expected)** | 0.002 | 23.306 | unavailable | 23.308 | 13.51 | — (404) | — | — | READY |
| V5 | 233489b8 | SUCCEEDED | 0.002 | 52.036 | 9.207 | 61.246 | 41.65 | 240320 / 08782c9be057f983 | 305856 / 28a27012cb16ee66 | 5693524 | READY |

V4 log: `src/main.cpp:8:24: error: expected ';' before 'delay'` + `[FAILED] Took 13.51 seconds`; error API = "PlatformIO compilation failed."; RAM/Flash V1 ≈ 6.4% / 18.3% (239.949 B); V3 = 6.6% / 20.5% (269.345 B).

### 4.2 Statistik V1 repeated build (5 build, himpunan penuh)

| Metrik (s) | min | max | median | range |
|---|---|---|---|---|
| platformio_seconds | 53.244 | 54.460 | 53.259 | 1.216 |
| merge_seconds | 9.360 | 9.746 | 9.506 | 0.386 |
| total_seconds | 62.683 | 63.972 | 62.925 | 1.289 |
| Took | 42.42 | 43.57 | 42.74 | 1.15 |

Warm subset (build #2–#5): total 62.683–62.925, median 62.841, range 0.242 — sangat stabil. Covariate cache: t_scan konstan ~4.4 s sepanjang sesi; Took #1 (43.57) vs #2–5 (42.4–42.8) menunjukkan warm-up kecil pada build pertama sesi.

## 5. Pass/Fail Criteria & Hasil

| Test | Kriteria (pre-registered) | Hasil | Verdict |
|---|---|---|---|
| V1 | 5/5 SUCCEEDED + artifacts + env READY + identitas ≤0.5s | 5/5; identitas max Δ=0.000–0.002 s | **PASS** |
| V2 | unchanged sukses+valid; determinisme dilaporkan | 5/5 sukses; **5/5 hash firmware.bin UNIK** → NON-DETERMINISTIC | **PASS** (dengan finding) |
| V3 | SUCCEEDED + hash ∉ V1-set + Flash berbeda + artifacts | semua terpenuhi (Flash 239.949→269.345 B) | **PASS** |
| V4 | FAILED + error benar + timing (merge=unavailable) + env READY + firmware 404 | semua terpenuhi | **PASS** |
| V5 | SUCCEEDED + artifacts + env READY tanpa restart | semua terpenuhi | **PASS** |
| V6 | digest_end==digest_start + files 13237 + 0 integrity ERROR | `f37801b3…==f37801b3…`, 13237, 9 build tanpa ERROR | **PASS** |
| V7 | wokwi==65536+fw.bin, duration==total, size band, 7 build sukses | 7/7 struktural PASS; sizes: BASE 240320/305856, V3 269712/335248 (0x10000 offset terverifikasi) | **PASS** |
| V8 | lifecycle terdokumentasi: growth, restart-404, NOT_READY→READY | +83 MB/9 build (≈9.2 MB/build); restart→404/NOT_READY; prepare→READY | **PASS** (dokumentasi) |

## 6. Analysis

**Fakta terukur:**
1. V1: build stabil (range total 1.29 s pada 5 build; Took range 1.15 s); env READY sepanjang sesi.
2. V2: firmware.bin NON-DETERMINistik lintas build meski source identik — 5/5 hash unik; sizes & RAM/Flash identik persis. wokwi-firmware.bin juga unik (mewarisi non-determinisme firmware.bin).
3. V3: perubahan source ter-propagasi penuh (size +29.392 B, hash baru, Flash +29.396 B ≈ sama, RAM +352 B).
4. V4/V5: failure path bersih (error API jelas, raw compiler log utuh, merge=unavailable, firmware 404, project dir persist); recovery sukses tanpa restart.
5. V6: Base Environment 0 perubahan (digest identik awal/akhir; agent-internal before/after check lolos 9/9 build).
6. V7: struktur presisi `wokwi = 65536 + firmware` 7/7; `duration_seconds == total_seconds` semua build.
7. V8: growth ~9.2 MB/build; `environment-check-*` dirs akumulasi lintas sesi (4 dirs dari prepare ulang); builds record in-memory (404 setelah restart); tidak ada mekanisme cleanup/TTL/max-builds di kode (terkonfirmasi via inspeksi).
8. Cross-check model 4-scan Opt-1 (semua build sukses): R_pio = pio_s − Took ≈ 10.39–10.88 s ≈ 2·t_scan (8.7–9.1 s) + pio startup + mount/unshare overhead — konsisten dengan struktur 2-scan per fase pada SELURUH 8 build sukses (bukan hanya build tunggal kemarin). R_merge = merge_s − mergebin(≈0.1) ≈ 9.1–9.65 s ≈ 2·t_scan — konsisten.

**Inferensi:**
1. Non-determinisme firmware.bin kemungkinan dari timestamp build dan/atau alamat/path project uuid yang di-embed toolchain (elf DIPREDIKSI non-deterministik — terkonfirmasi 5/5 unik; firmware.bin turut bervariasi walau size identik, mengindikasikan konten header/segment yang bergantung waktu/path). Implikasi: hash firmware TIDAK dapat dipakai sebagai fingerprint konten source; reproducibility byte-level tidak dijamin oleh toolchain default.
2. Kondisi cache sesi ini hangat dan stabil (t_scan ~4.4 s konstan), sehingga statistik V1 mencerminkan performa steady-state build pada mesin ini hari ini — bukan kontrak SLA absolut.
3. Perbedaan V4 ( Took 13.51 s, pio_s 23.31 s): compile gagal cepat, namun pio_s tetap memuat 2 scan (~8.7 s) + startup — failure path tidak memotong overhead scan.
4. V5 setelah failure: tidak ada degradasi (61.25 s, termasuk paling cepat sesi) — failure tidak mencemari build berikutnya.

**Rekomendasi (menunggu approval, tidak dieksekusi):**
1. V2 finding → jika reproducibility byte-level diinginkan (mis. untuk versioning artifact), evaluasi `-ffile-prefix-map`/`-fdebug-prefix-map` + kontrol timestamp — perlu eksperimen terpisah; PRD MVP tidak mewajibkan.
2. V8 finding → rancang cleanup lifecycle policy (retention project dirs, max builds in-memory, hapus `environment-check-*` setelah prepare sukses) sebagai proposal fitur terpisah.
3. Tahap optimasi 2 (manifest TTL/cache) kini punya data dasar yang lebih kaya (t_scan stabil ~4.4 s warm; 2 scan in-timer per fase ≈ 8.8–9.1 s per fase).

## 7. Evidence

- Log mentah 8 build: `Eksperiment/validation/logs/v1-build-{1..5}.log`, `v3-build.log`, `v4-build.log`, `v5-build.log` (blok timing + Took + RAM/Flash + raw compiler error V4).
- SHA-256 lengkap artifacts (64-hex) tercatat di sesi pengukuran; ringkasan 16-hex di tabel §4.1.
- digest manifest start/end: `f37801b3f9578a3c6de803995126ed530633212476f060d9c4298529679513f7` (identik, 13237 file).
- Disk: projects 59M→142M; agent-state 13K konstan.
- Restart evidence: 404 status build lama `9193b076…`; NOT_READY post-restart; prepare → READY.
- Project dirs sesi (9) tetap ada (tidak dihapus — evidence; termasuk failed build `13ca54a5…`).

## 8. Verdict

| Test | Verdict |
|---|---|
| V1 repeated build | **PASS** |
| V2 unchanged source | **PASS** — dengan finding NON-DETERMINISTIC artifacts (5/5 unik) |
| V3 changed source | **PASS** — propagasi terverifikasi |
| V4 failed compilation | **PASS** — expected-failure path bersih |
| V5 recovery after failure | **PASS** |
| V6 environment integrity | **PASS** — Base Environment immutable terkonfirmasi |
| V7 artifact integrity | **PASS** — 7/7 struktural |
| V8 cleanup/lifecycle | **PASS** — dokumentasi lifecycle; cleanup TIDAK ada (finding) |

**Verdict agregat: VALIDATION TRACK V1–V8 = 8/8 PASS.** Sistem build lokal terverifikasi stabil, integritas environment terjaga penuh, failure path sehat, dan struktur 4-scan Optimization-1 konsisten pada seluruh build. Dua temuan non-blocking terdokumentasi (non-determinisme artifact; absennya mekanisme cleanup).

## 9. Recommendation

1. **Lanjut ke pertimbangan Optimization 2 (manifest TTL/cache)** — kini didukung data: 2 scan in-timer/fase ~4.4 s each; potensi hemat ~8.8 s/build warm. Butuh plan + approval terpisah (per RULES).
2. **Proposal fitur cleanup lifecycle** (retention/eviction) — dari finding V8 (~9.2 MB/build, dirs `environment-check-*` menumpuk lintas sesi).
3. **Opsional: eksperimen reproducible build** (prefix-map + timestamp deterministik) dari finding V2 — relevan bila versioning artifact diinginkan; tidak wajib untuk MVP.
4. Pertahankan instrumentasi timing 4 metrik sebagai bagian permanen build path (sudah terbukti bernilai untuk seluruh analisis ini).

## 10. STOP — Await approval

Tidak ada tindakan lanjutan yang dieksekusi. Tahap berikutnya (optimization 2, cleanup lifecycle, reproducible build, atau arah lain) menunggu keputusan pengguna/reviewer.

# Optimization Run 1 — Eliminasi Scan `_manifest()` Redundan (6→4 per build)

**Tanggal:** 2026-09-09
**Build ID:** `3f44966611324f01bb2ab2ed4b3f7d03`
**Status:** SUCCEEDED
**Source:** identik baseline `85ed…` (blink 12 baris)
**Log mentah:** `optimization1-build-3f449666.log` (satu direktori ini)
**Dasar:** `profiling-run-2026-09-08.md` (verdict CONFIRMED)

---

## 1. Perubahan Kode (dieksekusi sesuai plan)

File: `local-agent/app/environment.py` — 3 fungsi:

1. `assert_ready()` → wrapper memanggil `_assert_ready_manifest()` (behavior pemanggil luar identik).
2. **Baru** `_assert_ready_manifest()`: gabungan state-check + verifikasi manifest vs baseline, **mengembalikan manifest** sebagai `before` (menghapus jendela divergensi lama antara scan assert dan scan before).
3. `run_platformio()` & `run_readonly_command()`: `before = self._assert_ready_manifest()` (1 scan) — post-command integrity check **tidak diubah** (tetap 1 scan per fase).

Scan `_manifest()` per build: **6 → 4** (in-timer). Endpoint 1 (luar timer) & `prepare()` 2 scan: tidak disentuh. `main.py`: 0 diff. Read-only mount/unshare/network isolation: 0 diff.

## 2. Data Verification Build

```
[CompilerIO timing]
project_setup_seconds=0.004
platformio_seconds=108.066   ← PIO "Took 76.16 seconds"
merge_seconds=32.367
total_seconds=140.439        (= duration_seconds via /status ✓)
```

Pengukuran standalone sesi ini: `t_scan_before` = 14.540 / 14.043 s; `t_scan_after` = 15.921 / 16.616 s (median **16.27 s**; 13.237 file — konsisten jumlahnya).

Artifacts: `firmware.bin` 240.320 B (== baseline 240.320 B), `firmware.elf` 5.693.524 B, `wokwi-firmware.bin` 305.856 B (== baseline 305.856 B). Environment `/status` post-build: **READY** (tidak ada false-positive integrity).

## 3. Analisis K1–K7

| K | Kriteria | Hasil | Status |
|---|---|---|---|
| K1 | Build sukses + 3 artifacts + env READY post-build | semua terpenuhi | **PASS** |
| K2 | \|total − Σ fase\| ≤ 0.5 s | 0.002 s | **PASS** |
| K3 | platformio_after ≤ 54.816 − 0.5·t_scan_after | 108.07 > 46.68 | **FAIL** ⚠ |
| K4 | merge_after ≤ 13.964 − 0.5·t_scan_after | 32.37 > 5.83 | **FAIL** ⚠ |
| K5 | total_after ≤ 68.783 − 1.0·t_scan_after | 140.44 > 52.51 | **FAIL** ⚠ |
| K6 | Kontrol variabel: Took ∈ [35, 48] s | **76.16 s** | **FAIL** ⚠ |
| K7 | R_pio ≈ 2·t_scan + t_pio_startup (path 4-scan aktif) | \|31.91 − 32.84\| = 0.93 ≤ 8.13 | **PASS** |

### Akar kegagalan K3–K6: session confound, bukan regresi optimasi

Kondisi mesin sesi ini berbeda drastis dari sesi profiling kemarin (page cache mount NTFS dingin — kemungkinan reboot/maintenance filesystem antara 08 Sep dan 09 Sep):

| Variabel kontrol | 2026-09-08 (before) | 2026-09-09 (after) |
|---|---|---|
| PIO "Took" (compile murni, TIDAK terpengaruh refactor) | 41.29 s | **76.16 s** (+34.9 s) |
| t_scan standalone | 3.95–4.07 s | 14.0–16.6 s |
| total_seconds | 68.78 s | 140.44 s |

Kenaikan "Took" +35 s adalah compile murni di dalam `pio run` — **mustahil disebabkan refactor environment.py** (refactor hanya menghapus 1 scan per fase). K3–K6 membandingkan metrik mentah lintas sesi yang tidak setara; sesuai metodologi penelitian, perbandingan tersebut tidak sahih.

### Bukti struktural optimasi bekerja (dalam-sesi, valid)

Hipotesis 6-scan vs 4-scan dapat dibedakan TANPA perbandingan lintas sesi — cukup residual dalam sesi ini:

- **R_pio** = platformio_seconds − Took = 108.066 − 76.16 = **31.91 s**
  - Prediksi path 4-scan (2 scan): 2·t_scan_after + t_pio_startup ≈ 32.84 s → Δ **−0.93 s** (K7 PASS)
  - Prediksi path 6-scan (3 scan) [counterfactual]: ≈ 48.8 s → tidak cocok
- **R_merge** = merge_seconds − t_mergebin ≈ 32.37 − 0.1 = **32.27 s**
  - Prediksi 2 scan: 2·t_scan_after ≈ 32.53 s → Δ **−0.26 s**
  - Prediksi 3 scan: ≈ 48.8 s → tidak cocok
- **Gap dalam-sesi** G = total − Took = 64.28 s ≈ 4·t_scan_after (65.07 s) → coverage ≈ **101%**

Ketiga residual jatuh **tepat pada 2×t_scan per fase** — path 4-scan terbukti aktif. Counterfactual 6-scan pada sesi ini: ≈ setup + [76.16 + 3·16.27 + 0.3] + [3·16.27 + 0.1] ≈ 174.3 s vs aktual 140.44 s → **penghematan ≈ 33.9 s ≈ 2×t_scan sesi ini**.

## 4. VERDICT: **STRUCTURALLY VERIFIED — TIME-REDUCTION CLAIM DEFERRED (PARTIAL)**

1. **Optimasi terverifikasi secara struktural dan fungsional**: path 4-scan aktif (K7 PASS, residual tepat 2×t_scan di kedua fase), build sukses, artifacts identik ukuran dengan baseline, integrity verification tetap berjalan, environment tetap READY.
2. **Klaim "total build time turun vs sebelum optimasi" BELUM dapat dibuktikan dari run ini** karena perbandingan lintas sesi tidak setara (K6 FAIL: Took 76.16 vs rentang kontrol 35–48; t_scan 16.3 vs 3.9). Klaim tersebut membutuhkan fase repeated-build testing (build beruntun dalam kondisi cache setara/stabil) yang memang merupakan fase berikutnya dalam roadmap.
3. Sesuai plan §6: TIDAK otomatis lanjut ke tahap optimasi 2 (TTL/cache) — menunggu analisis ini direview.

## 5. Rekomendasi untuk fase berikutnya (repeated-build testing)

- Jalankan build beruntun dalam satu sesi agen (cache setara) — fase berikutnya sudah direncanakan: repeated build, unchanged source, changed source, failed compilation.
- Ambil metrik per-build dengan instrumentasi yang sama; bandingkan within-session antar build ke-1..ke-N (bukan lintas hari).
- Untuk future: catat kondisi sesi (t_scan awal) sebagai covariate setiap kali profiling; variasi 4→16 s antar sesi adalah temuan operasional penting untuk target SLA build-time.
- Perbandingan before/after optimasi yang sahih dapat direkonstruksi: pada repeated-build fase, jalankan beberapa build, lalu (jika disetujui) satu build dengan kode lama via backup `/tmp/kilo/environment.py.backup` dalam sesi yang sama cache-nya — optional, keputusan pemilik project.

## 6. Status

- [x] Refactor 6→4 scan dieksekusi + diverifikasi (py_compile, import, diff minimal)
- [x] Verification build sukses + artifacts + integrity tetap READY
- [x] Struktur 4-scan terbukti aktif (K7, R_pio & R_merge ≈ 2×t_scan)
- [x] Laporan jujur: time-reduction lintas-sesi invalid (session confound terdokumentasi)
- [ ] Repeated / unchanged / changed / failed-compilation testing (fase berikut)
- [ ] Tahap optimasi 2 (TTL/cache) — tertunda, menunggu hasil repeated-build

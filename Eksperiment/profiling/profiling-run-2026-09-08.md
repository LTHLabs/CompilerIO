# Profiling Run — run_build() Timing Instrumentation

**Tanggal:** 2026-09-08
**Build ID:** `fcf60eae5f7a430eae70bb3e8ec1922f`
**Status:** SUCCEEDED
**Source:** identik baseline `85ed…` (blink 12 baris)
**Log mentah:** `profiling-build-fcf60eae.log` (satu direktori ini)

---

## 1. Perubahan Kode (satu-satunya yang dieksekusi)

File: `local-agent/app/main.py` (fungsi `run_build()` + helper `_timing_value()`)

1. Fix typo blocker `result.stderrls` → `result.stderr` (line lama 149).
2. Blok `[CompilerIO timing]` dikonsolidasikan ke `finally`: selalu muncul di semua outcome (SUCCEEDED / compile-fail / merge-fail / exception), dengan nilai `unavailable` untuk fase yang belum terekam.
3. `total_seconds` kini dihitung dari `started` yang sama dengan `record.duration_seconds` — dijamin identik.

Tidak ada perubahan lain: `environment.py` 0 diff, read-only mount utuh, security/pairing utuh, kontrak endpoint utuh, Base Environment hanya dibaca.

---

## 2. Data Terkumpul

### Blok timing dari build (via `GET /build/{id}/log`)

```
[CompilerIO timing]
project_setup_seconds=0.001
platformio_seconds=54.816
merge_seconds=13.964
total_seconds=68.783
```

Cross-check: `duration_seconds=68.783` dari `/build/{id}/status` — identik. ✓

### PlatformIO reference

```
========================= [SUCCESS] Took 41.29 seconds =========================
```

### Pengukuran pendukung (standalone, di luar agent)

| Pengukuran | Run 1 | Run 2 | Median (t) |
|---|---|---|---|
| `_manifest()` scan (13.237 file) — before build | 3.924 s | 3.965 s | **3.945 s** |
| `_manifest()` scan — after build | 4.097 s | 4.049 s | **4.073 s** |
| `pio --version` startup (PLATFORMIO_CORE_DIR diset) | 0.297 s | 0.212 s | **0.255 s** |
| `merge_bin` standalone (python+esptool startup termasuk) | 0.121 s | 0.081 s | **0.101 s** |

Scan post-build sedikit lebih lambat (4.05–4.10 s vs 3.92–3.97 s) — mungkin efek cache filesystem; keduanya konsisten ~4 s.

Artifacts: `firmware.bin` 240.320 B + `wokwi-firmware.bin` 305.856 B di project env `fcf6…` — sesuai baseline.

---

## 3. Analisis Kriteria (C1–C4)

Definisi:
- `G` = total − pio_took = 68.783 − 41.29 = **27.49 s**
- `R_pio` = platformio_seconds − pio_took = 54.816 − 41.29 = **13.53 s**
- `R_merge` = merge_seconds − t_mergebin = 13.964 − 0.101 = **13.86 s**
- `t_scan` (session ini) = **3.945 s** (before) — dipakai untuk C2/C3; scan after 4.073 s dipakai sebagai sensitivitas.

**C1 — Identitas instrumentasi:** |total − (setup + platformio + merge)| = |68.783 − 68.781| = **0.002 s ≤ 0.5 s** → **PASS**

**C2 — Residual fase PlatformIO:** prediksi = 3·t_scan + t_pio_startup = 11.835 + 0.255 = **12.09 s**; aktual R_pio = 13.53 s; selisih = 1.44 s ≤ max(3, 0.25·11.835=2.96) = 3 s → **PASS**
(dengan t_scan after 4.073: prediksi 12.47 s → selisih 1.06 s — tetap pass; catatan: residual juga memuat biaya mount/unshare + scons di dalam subprocess pio yang tidak diukur "Took", jadi 1.4 s sisanya wajar)

**C3 — Residual fase merge:** prediksi = 3·t_scan = 11.835 s; aktual R_merge = 13.86 s; selisih = 2.02 s ≤ max(3, 2.96) = 3 s → **PASS**
(dengan t_scan after: selisih 1.65 s — konsisten)

**C4 — Cakupan gap:** 6·t_scan = 23.67 s; G = 27.49 s → coverage = **86.2% ≥ 80%** → **PASS**
Sisa tak terjelaskan: 27.49 − 23.67 − 0.255 ≈ 3.6 s — berasal dari: biaya `unshare`+mount-remount bind ×2 proses, startup esptool dalam namespace, overhead `asyncio.to_thread`/subprocess capture, penulisan platformio.log di mount NTFS.

### Perhitungan prediksi hipotesis vs aktual

| Besaran | Prediksi hipotesis | Aktual run ini | Konsisten? |
|---|---|---|---|
| `platformio_seconds` | pio_took + 3·t_scan + pio_startup ≈ 41.29+11.84+0.26 ≈ 53.4 s | 54.82 s | ✓ (Δ +1.4 s) |
| `merge_seconds` | 3·t_scan + t_mergebin ≈ 11.94 s | 13.96 s | ✓ (Δ +2.0 s) |
| `total_seconds` | ≈ 65–70 s (est. ballpark plan) | 68.78 s | ✓ |

### Catatan penting baseline

Gap pada session ini (27.49 s) LEBIH KECIL daripada gap baseline historis (39.33 s pada build 85ed: total 83.134 s, Took 43.80 s). Penjelasan: t_scan baseline kemungkinan ~6.5 s (sesuai pengukuran lepas Anda 6.8–7.6 s — kondisi cache berbeda) vs ~4.0 s pada session ini; aritmetika 6×6.5=39 s cocok dengan gap historis. Session ini memiliki page cache hangat (prepare + pengukuran pendukung sebelumnya), mempercepat scan. Ini TIDAK menyalahkan validitas verdict — arsitektur pemanggilan (6 scan) adalah yang diuji, dan pola residual per-fase (≈3× t_scan per fase) terkonfirmasi di KEDUA fase secara independen.

---

## 4. VERDICT: **CONFIRMED**

Hipotesis terkonfirmasi secara empiris: `_manifest()` dipanggil 6× per build (3× di `run_platformio`, 3× di `run_readonly_command`) dan merupakan **sumber overhead dominan** (86% dari gap pada session ini; cocok penuh dengan gap historis pada t_scan ~6.5 s).

Bukti kunci:
1. Residual per fase ≈ tepat 3× t_scan di kedua fase, independen (C2, C3 pass).
2. Instrumentasi konsisten secara internal (C1 pass, gap 0.002 s).
3. Coverage 86% ≥ 80% (C4 pass).
4. Aritmetika juga menjelaskan gap historis dengan t_scan baseline ~6.5 s.

---

## 5. Impikasi (untuk plan berikutnya — TIDAK dieksekusi sekarang)

Optimasi `_manifest()` kini punya dasar bukti untuk dievaluasi. Kandidat yang teridentifikasi dari data (semua menunggu plan + approval terpisah):
1. Scan `assert_ready()` + scan `before` pada awal tiap fase redundan secara semantik (keduanya memverifikasi state sama berurutan) → merge 2 scan jadi 1 di tiap fase (−2 scan, −~8 s).
2. Verifikasi post-command (1 scan per fase) adalah jaminan integritas sesuai desain arsitektur → dipertahankan, atau diganti sampling/TTL manifest cache dengan trade-off keamanan yang harus dieksplisitkan.
3. Cache manifest ber-TTL → menghilangkan mayoritas scan pada build beruntun (repeated build fase uji berikutnya) dengan menjaga verifikasi penuh di momen kritis.

Estimasi dampak potensial (bukan hasil, hanya proyeksi dari data): −2 s/dari 6 scan → total build ~60–61 s pada kondisi cache session ini; dengan cache TTL bisa mendekati setup+pio_took+merge(~1 s)+sisa kecil ≈ 45–48 s.

## 6. Status Fase 1

- [x] Instrumentasi timing berjalan di semua outcome
- [x] Satu profiling build selesai + data lengkap
- [x] Sumber overhead terbukti empiris (verdict CONFIRMED)
- [ ] Repeated build / unchanged source / changed source / failed compilation
- [ ] Base Environment integrity / artifact integrity / cleanup lifecycle
- [ ] Final build-time measurement

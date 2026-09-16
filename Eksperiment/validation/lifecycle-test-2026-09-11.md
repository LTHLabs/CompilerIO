# LIFECYCLE TEST REPORT — Cleanup & Lifecycle Policy Implementation

**Tanggal:** 2026-09-11
**Plan dasar:** Cleanup & Lifecycle Policy Local Agent (approved: count-based N=20 default / coupled eviction / full startup sweep / FAILED=SUCCEEDED policy)
**Peran:** Implementation & Verification Agent
**Kode yang diuji:** `local-agent/app/config.py` (+`build_retention`), `local-agent/app/lifecycle.py` (baru, BuildJanitor), `local-agent/app/main.py` (3 titik integrasi). `environment.py` & `security.py`: **0 diff** (diverifikasi via snapshot diff).

---

## 1. Objective

Mengimplementasikan cleanup & lifecycle policy (retention cap N coupled record+dir, startup full sweep, environment-check cleanup post-prepare) dan memverifikasinya dengan test A1–A7, tanpa mengganggu artifact download, status/log retrieval, Base Environment integrity, security, build isolation, dan endpoint contract.

## 2. Configuration

- Test retention: `COMPILERIO_BUILD_RETENTION=3` (produksi default 20, tanpa env var).
- Board/framework: `esp32dev` + `arduino`. Origin `http://localhost:3000`. 3 sesi agen (restart di A4 & A5 by design).
- Covariate cache sesi: build ~84.3–86.2 s / Took 57.6–59.1 s (cache dingin-sedang; t_scan start 10.5 s → end 6.4 s — tidak mempengaruhi validitas test lifecycle yang bukan test performa).
- Source varian: BASE (blink) & BROKEN (missing semicolon) — sama dengan sesi validasi.

## 3. Test Procedure

Sesuai plan §8: unit sanity BuildJanitor di sandbox → digest start → agent retention=3 → verifikasi startup sweep (14 entri lama) → pair + prepare + cek environment-check cleanup → A1 5 build BASE → A2 aksesibilitas retained → A3 build BROKEN → A4 restart + smoke → A5 decoy + restart + smoke → digest end → report. Semua deletion diuji via `ls`/`du` + HTTP status codes.

## 4. Raw Measurements

### 4.1 Implementasi (diff terhadap backup)

- `config.py`: field `build_retention: int = 20`; env `COMPILERIO_BUILD_RETENTION` (parse int, ValueError → 20; clamp `max(1, …)`).
- `lifecycle.py` (baru): `BuildJanitor` — `enforce()` (FIFO evict terminal builds melewati cap; QUEUED/RUNNING tak pernah dihitung), `sweep_startup()` (hapus semua entri projects_dir), `cleanup_validation_dirs()` (prefix `environment-check-`), `safe_delete()` (containment: `path.parent.resolve() == projects_dir.resolve()`; rmtree untuk dir, unlink untuk file/symlink; OSError ditangkap → warning print → return False; tidak pernah raise).
- `main.py`: import + instansiasi `janitor`; startup event → `sweep_startup()` sebelum pairing code (failures di-print, tidak menghentikan startup); `run_build` finally (dalam `build_lock`, setelah timing block) → `janitor.enforce(builds)`; endpoint `/environment/prepare` → jika status READY → `cleanup_validation_dirs()`.
- Verifikasi statis: py_compile 3 file OK; `import app.main` OK (retention default 20); diff `environment.py`/`security.py` vs snapshot = **identik (0 diff)**.
- Unit sanity BuildJanitor (sandbox `/tmp/kilo/janitor-sandbox`): FIFO evict benar (oldest terminal di-evict, QUEUED bertahan), dir ikut terhapus, environment-check cleanup, sweep hapus semua termasuk file biasa, containment menolak path di luar projects_dir (return False + warning), clamp retention 0→1. **Lulus semua.**

### 4.2 Hasil test live

| Test | Bukti kunci | Hasil |
|---|---|---|
| Startup sweep awal | 14 entri (9 build dirs + 5 environment-check) → `ls` = 0; agent hidup; pairing code tercetak | **OK** |
| Post-prepare cleanup | `prepare` → READY; `runtime/projects` = 0 entri/0B (validation build dir terhapus otomatis) | **OK** |
| A1 retention (5 build BASE) | Setelah build#4: dirs = #2,#3,#4 (b1 `849c…` dihapus); setelah #5: dirs = #3 `6350…`, #4 `32af…`, #5 `3dea…`; b1+b2 → 404; selalu tepat 3 | **PASS** |
| A2 retained accessible | 3 retained builds × (status, log, fw.bin, fw.elf, wokwi) = **15/15 HTTP 200**; log retained #5: blok timing 4 metrik lengkap | **PASS** |
| A3 FAILED retention | BROKEN → FAILED `038f…` (Took 21.26 s, total 35.4 s, merge=unavailable); evict b3 `6350…` → 404; FAILED log + raw error + timing retrievable; dirs tetap 3 (2 SUCCEEDED + 1 FAILED) | **PASS** |
| A4 restart full sweep | restart → semua dirs (termasuk retained + FAILED) tersapu → 0 entri; build record lama 404; NOT_READY → prepare → READY; smoke build `6118…` SUCCEEDED 86.2 s | **PASS** |
| A5 decoy + restart | tanam `decoy.txt` + `decoy-dir/` + 1 build dir → restart → 0 entri (semua tersapu), tanpa crash, tanpa startup failure; pairing/prepare/smoke build `3522…` SUCCEEDED 84.8 s normal | **PASS** |
| A6 Base Env integrity | `digest_start == digest_end == f37801b3f9578a3c6de803995126ed530633212476f060d9c4298529679513f7`, files 13237 (identik juga dengan sesi validasi 09-10) | **PASS** |
| A7 regression | Smoke builds A4/A5: blok timing lengkap; `total_seconds == duration_seconds` (86.156, 84.781); Took terekam; env READY sepanjang sesi; kontrak endpoint tak berubah (rute/method/response shape sama) | **PASS** |

### 4.3 Metrik build sesi (covariate: cache dingin-sedang)

| Build | ID | Status | setup_s | pio_s | merge_s | total_s | Took |
|---|---|---|---|---|---|---|---|
| A1#1 | 849c86f8 | SUCCEEDED (evicted) | — | — | — | 85.347 | — |
| A1#2 | f61e0249 | SUCCEEDED (evicted) | — | — | — | 85.709 | — |
| A1#3 | 6350246c | SUCCEEDED (evicted di A3) | — | — | — | 85.308 | — |
| A1#4 | 32af01b1 | SUCCEEDED (retained→swept A4) | — | — | — | 84.830 | — |
| A1#5 | 3deac9f9 | SUCCEEDED (retained→swept A4) | 0.002 | 71.789 | 12.508 | 84.300 | 57.65 |
| A3 | 038f7d26 | FAILED (retained→swept A4) | 0.001 | 35.403 | unavailable | 35.404 | 21.26 |
| A4 smoke | 61188bf7 | SUCCEEDED (swept A5) | 0.001 | 73.396 | 12.758 | 86.156 | 59.05 |
| A5 smoke | 3522493c | SUCCEEDED (retained, akhir sesi) | 0.001 | 72.069 | 12.711 | 84.781 | 57.59 |

State akhir disk: `runtime/projects` = 1 dir (smoke A5, ~12 MB) ≤ cap 3; `agent-state` 13K.

## 5. Pass/Fail Criteria → Hasil

| Kriteria (plan §8) | Hasil |
|---|---|
| A1: tepat 3 dirs + evicted 404 (status/log/firmware) | **PASS** |
| A2: retained 200 + log timing + 3 artifacts downloadable | **PASS** |
| A3: FAILED retained/evicted seragam; env READY | **PASS** |
| A4: sweep penuh + 404 + NOT_READY→READY + smoke OK | **PASS** |
| A5: decoy file/dir tersapu, tanpa crash, build normal | **PASS** |
| A6: digest identik | **PASS** |
| A7: timing + total==duration + kontrak endpoint | **PASS** |

## 6. Analysis

**Fakta terukur:** semua 7 acceptance criteria terpenuhi; disk `runtime/projects` ter-bound ≤ N×~9.2MB per sesi + kembali 0 setiap restart; memori `builds` ter-bound N record (coupled eviction, FIFO, single invariant 404); environment-check tidak lagi menumpuk (dibersihkan post-prepare-success); startup sweep membuktikan self-healing (decoy ter-tangani); Base Environment 0 perubahan; security/mount/endpoint contract 0 diff.

**Inferensi:** (1) coupled eviction + FIFO aman dari race by construction karena `enforce` dipanggil dalam `build_lock` — konsisten dengan semua observasi (tidak ada 404 untuk build retained, tidak ada dir leak saat 5 build beruntun). (2) Konsekuensi desain yang terverifikasi sesuai keputusan: setelah restart, SEMUA build sebelumnya (termasuk artifacts di disk) tidak lagi tersedia — penuh dan seragam (404 semua), bukan parsial. (3) Performa build sesi ini (Took ~58 s) lebih lambat dari sesi validasi (Took ~42 s) — covariate cache mesin, bukan efek lifecycle code (janitor berjalan sekali per build, di luar subprocess compile; waktu enforce ≈ rmtree 12 MB, tak terukur pada total).

**Rekomendasi (menunggu approval, tidak dieksekusi):** (1) default N=20 sudah sesuai target disk ≤ ~184 MB; pertimbangkan dokumentasikan di README. (2) Opsi future: `du`-based cap jika diperlukan (saat ini count-based sesuai keputusan). (3) Tidak ada temuan blocking.

## 7. Evidence

- Snapshot 0-diff: `/tmp/kilo/lifecycle/verify-{environment,security}.py` vs file aktual = identik; rollback copies `rollback-{main,config}.py`.
- ID build sesi + token log: `/tmp/kilo/lifecycle/ids.txt`.
- Pengukuran disk/`ls` sequence tiap tahap (terdokumentasi di §4.2).
- digest manifest start/end (§4.2 A6).
- Log HTTP status code: b1/b2/b3 404 pasca evict; 15/15×200 retained; 404 record lama post-restart.

## 8. Verdict

**Cleanup & Lifecycle Policy Implementation: PASS (A1–A7 lulus semua).**
Retention N (coupled record+dir+artifacts, FIFO, FAILED dihitung sama), startup full sweep, dan environment-check cleanup terverifikasi bekerja sesuai desain tanpa mengganggu fungsi build, retrieval, download, maupun integritas Base Environment.

## 9. Recommendation

1. Terima implementasi lifecycle ini sebagai bagian stabil dari Local Agent.
2. Item berikutnya menunggu keputusan: README/dokumentasi konfigurasi `COMPILERIO_BUILD_RETENTION`, lalu kembali ke roadmap (error mapping / library detection per PRD, atau eksperimen lain sesuai arah Anda).

## 10. STOP — Await approval

Tidak ada tindakan lanjutan yang dieksekusi. Agent di-stop; state disk bersih (1 build dir retained ≤ cap).

# Toko Online Mikroservis - Tugas Kelompok

Repositori tugas kelompok berisi **5 arsip zip bertahap**. Setiap arsip adalah versi
sebelumnya ditambah bagian milik peserta berikutnya, sehingga riwayat pekerjaan terlihat
jelas (v1 → v5). Arsip berada di folder `releases/`.

> **Versi ini: tahap 2 dari 5** - Pelanggan Service.

## Matriks tahap

| Arsip | Isi utama | Pemilik | Status |
|---|---|---|---|
| v1 | Katalog Service | Peserta 1 | selesai |
| v2 | Pelanggan Service | Peserta 2 | selesai |
| v3 | Order Service + saga kompensasi | Peserta 3 | belum |
| v4 | Pembayaran Service | Peserta 4 | belum |
| v5 | API Gateway, dashboard, docker compose, seed, e2e | Peserta 5 | belum |

Rincian tiap arsip: [`releases/README.md`](releases/README.md). Hasil uji per tahap:
[`docs/HASIL-VERIFIKASI.md`](docs/HASIL-VERIFIKASI.md). Pohon sumber di akar repositori ini
adalah isi v5 (kondisi akhir).

## Distribusi tugas

Rincian peran dan kontrak antar layanan: [docs/DISTRIBUSI-TUGAS.md](docs/DISTRIBUSI-TUGAS.md).
Alur checkout + kompensasi: [docs/ALUR-SAGA.md](docs/ALUR-SAGA.md).
Ringkasan endpoint: [docs/API.md](docs/API.md).

## Arsitektur

```
                       ┌───────────────────────────┐
   browser / curl ───► │  API Gateway  :8000       │  JWT, proksi, agregasi
   (toko & admin)      │  dashboard / dan /admin   │
                       └───────┬───────────────────┘
             ┌─────────────────┼──────────────────┬──────────────────┐
             ▼                 ▼                  ▼                  ▼
     ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐
     │ Katalog :8001│  │Pelanggan:8002│  │  Order :8003 │  │Pembayaran :8004│
     │ produk, stok │  │ auth JWT,    │  │ keranjang,   │  │ tagihan,       │
     │ reservasi    │  │ profil,alamat│  │ saga checkout│  │ simulasi,      │
     └──────────────┘  └──────────────┘  └──────────────┘  │ laporan        │
            SQLite            SQLite            SQLite      └────────────────┘
                                                            SQLite
```

Layanan berbicara lewat HTTP + JSON dengan amplop `{success, data, error, request_id}`.
Autentikasi pengguna memakai JWT HS256; autentikasi antar layanan memakai `X-Service-Token`.

## Layanan pada tahap ini

| Layanan | Folder | Alamat |
|---|---|---|
| katalog | `katalog-service/` | http://localhost:8001 |
| pelanggan | `pelanggan-service/` | http://localhost:8002 |

## Menjalankan

```bash
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r katalog-service/requirements.txt
python scripts/dev_up.py
python seed/seed_data.py --pesanan 4     # opsional, data contoh
```

### Menjalankan dengan Docker Compose

```bash
cp .env.example .env
docker compose up --build -d
docker compose ps
```

Akun demo setelah seed: `admin@contoh.test / admin12345`, `siti@contoh.test / rahasia123`.
Dashboard toko: <http://localhost:8000> · Dashboard admin: <http://localhost:8000/admin>.

## Pengujian

```bash
python tests/run_tests.py          # menyalakan layanan yang ada, menjalankan semua tes, lalu mematikan
python tests/run_tests.py -v       # verbose
python tests/run_tests.py --tanpa-boot   # bila layanan sudah jalan
```

Tes yang layanannya belum ada akan **dilewati** (bukan gagal) - itu normal untuk arsip tahap awal.

## Struktur berkas pada tahap ini

- `.env.example`
- `.gitignore`
- `common/__init__.py`
- `common/config.py`
- `common/db.py`
- `common/errors.py`
- `common/httpc.py`
- `common/jwtutil.py`
- `common/responses.py`
- `common/security.py`
- `common/service.py`
- `docs/ALUR-SAGA.md`
- `docs/API.md`
- `docs/DISTRIBUSI-TUGAS.md`
- `docs/HASIL-VERIFIKASI.md`
- `katalog-service/Dockerfile`
- `katalog-service/app.py`
- `katalog-service/requirements.txt`
- `katalog-service/schema.sql`
- `pelanggan-service/Dockerfile`
- `pelanggan-service/app.py`
- `pelanggan-service/requirements.txt`
- `pelanggan-service/schema.sql`
- `scripts/dev_up.py`
- `seed/data/katalog.json`
- `seed/data/pelanggan.json`
- `seed/seed_data.py`
- `tests/base.py`
- `tests/run_tests.py`
- `tests/test_katalog.py`
- `tests/test_pelanggan.py`

## Catatan tahap 2

Pelanggan Service dikerjakan oleh **Peserta 2**. Detail perubahan ada di
[CHANGELOG.md](CHANGELOG.md). Arsip tahap sebelumnya tetap dapat dijalankan sendiri karena
setiap tahap membawa seluruh kode tahap sebelumnya.

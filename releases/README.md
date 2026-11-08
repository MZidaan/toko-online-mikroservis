# Arsip Rilis - 5 Zip Bertahap

Setiap arsip adalah **versi kumulatif**: isinya seluruh kode arsip sebelumnya ditambah
bagian milik peserta berikutnya. Unzip salah satu arsip, dan proyek pada tahap itu
langsung bisa dijalankan serta diuji.

| # | Arsip | Isi utama | Ditambahkan oleh | Tes |
|---|---|---|---|---|
| 1 | `v1-katalog-service.zip` | `common/`, Katalog Service (produk, kategori, stok, reserve/commit/release) | Peserta 1 | 8 lulus |
| 2 | `v2-pelanggan-service.zip` | Pelanggan Service (registrasi, login JWT, profil, alamat, verifikasi token) | Peserta 2 | 16 lulus |
| 3 | `v3-order-service.zip` | Order Service (keranjang, checkout saga + kompensasi, riwayat, status) | Peserta 3 | 24 lulus |
| 4 | `v4-pembayaran-service.zip` | Pembayaran Service (inisiasi, simulasi, sinkronisasi, laporan) | Peserta 4 | 30 lulus |
| 5 | `v5-integrasi-dan-dashboard.zip` | API Gateway, dashboard toko & admin, Docker Compose, seed data, tes e2e | Peserta 5 | 39 lulus |

## Kode sumber kerja

Pohon sumber di akar repositori ini **adalah isi v5** (kondisi akhir). Folder `releases/`
hanya menyimpan kelima arsip.

## Menjalankan satu arsip

```bash
unzip releases/v4-pembayaran-service.zip -d /tmp/uji
cd /tmp/uji/tugas-kelompok
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r katalog-service/requirements.txt
python tests/run_tests.py        # layanan dinyalakan otomatis, lalu dimatikan
```

Untuk versi 5, setelah layanan hidup:

```bash
python seed/seed_data.py --pesanan 5
# buka http://localhost:8000  (toko)  dan  http://localhost:8000/admin
```

## Catatan kompatibilitas

- Arsip v3 belum memuat layanan pembayaran; `tests/run_tests.py` otomatis mengeset
  `INTEGRASI_PEMBAYARAN=0` sehingga checkout tetap berjalan (kompensasi diuji lewat hook `simulasi`).
- Setiap arsip membawa `docker-compose.yml` yang hanya memuat layanan yang sudah ada.
- Rincian hasil uji: `docs/HASIL-VERIFIKASI.md`.

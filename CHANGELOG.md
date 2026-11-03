# Changelog

Semua perubahan penting proyek. Setiap entri = satu arsip zip di `releases/`.

## v1 - Katalog Service (Peserta 1)

Arsip: `releases/v1-katalog-service.zip`

- Katalog Service lengkap: kategori, produk, stok, reserve/commit/release yang atomik.
- Paket `common/` (config, SQLite, JWT HS256, keamanan, klien HTTP) sebagai fondasi bersama.
- Runner tes `tests/run_tests.py` + `tests/base.py` + `scripts/dev_up.py` agar tahap ini bisa diverifikasi.
- Dokumentasi distribusi tugas, ringkasan API, dan alur saga.

## v2 - Pelanggan Service (Peserta 2)

Arsip: `releases/v2-pelanggan-service.zip`

- Pelanggan Service: registrasi, login JWT, profil, buku alamat, endpoint verifikasi token.
- Peran `admin` hanya bisa dibuat lewat endpoint internal (dipakai seed/admin bootstrap).
- Tes pelanggan: registrasi, login salah, email duplikat, verifikasi token, alamat utama.

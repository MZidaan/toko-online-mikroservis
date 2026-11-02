# Distribusi Tugas Kelompok

Proyek: **Toko Online Mikroservis** - 5 layanan Python/Flask + SQLite, satu API Gateway
dengan dua dashboard (toko & admin), dijalankan dengan Docker Compose atau skrip lokal.

Periode: dibuka Senin, 2 November 2026 00:00 - tenggat Senin, 9 November 2026 00:00.

| Peran | Tanggung jawab | Folder |
|---|---|---|
| **Peserta 1** | Katalog Service (produk, kategori, stok, reserve/release) | `katalog-service/` |
| **Peserta 2** | Pelanggan Service (registrasi, login JWT, profil, alamat, endpoint verifikasi token) | `pelanggan-service/` |
| **Peserta 3** | Order Service (keranjang, checkout dengan kompensasi, riwayat dan status pesanan) | `order-service/` |
| **Peserta 4** | Pembayaran Service (inisiasi dan simulasi pembayaran, sinkronisasi status pembayaran, laporan) | `pembayaran-service/` |
| **Peserta 5** | API Gateway, Dashboard (toko dan admin), Docker Compose, seed data, tes end-to-end | `gateway/`, `tests/`, `docker-compose.yml` |

## Kontrak antar layanan (WAJIB dipatuhi semua peserta)

Semua respons memakai amplop yang sama:

```json
{ "success": true, "data": { }, "meta": { }, "request_id": "..." }
{ "success": false, "error": { "kode": "VALIDASI_GAGAL", "pesan": "..." }, "request_id": "..." }
```

- Autentikasi pengguna: `Authorization: Bearer <JWT HS256>`.
- Autentikasi antar layanan: header `X-Service-Token: $SERVICE_TOKEN`.
- Port: katalog 8001, pelanggan 8002, order 8003, pembayaran 8004, gateway 8000.
- Klaim JWT: `sub` (id pelanggan), `email`, `nama`, `peran` (`pelanggan`/`admin`), `iat`, `exp`.

## Pembagian berkas (agar tidak bentrok saat merge)

Setiap peserta hanya menulis di foldernya sendiri. `common/` dan `docker-compose.yml`
milik Peserta 5; usulan perubahan `common/` diajukan lewat issue, bukan commit langsung.

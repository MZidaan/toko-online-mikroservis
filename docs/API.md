# Ringkasan API

Semua endpoint lewat gateway: `http://localhost:8000/api/<layanan>/...`

## Katalog Service (`/api/katalog`)
| Metode | Path | Akses | Keterangan |
|---|---|---|---|
| GET | `/kategori` | publik | daftar kategori |
| POST | `/kategori` | admin | buat kategori |
| GET | `/produk` | publik | filter `kategori`, `q`, `aktif`, `halaman`, `batas` |
| GET | `/produk/<id>` | publik | detail + stok tersedia |
| POST | `/produk` | admin | buat produk |
| PUT | `/produk/<id>` | admin | ubah produk |
| POST | `/produk/<id>/stok` | admin | tambah/kurangi stok (`{ "tambah": 10 }`) |
| POST | `/internal/reservasi` | layanan | reserve stok (`order_ref`, `items[]`, `ttl_detik`) |
| POST | `/internal/reservasi/<id>/komit` | layanan | stok keluar permanen |
| POST | `/internal/reservasi/<id>/rilis` | layanan | kembalikan stok (kompensasi) |

## Pelanggan Service (`/api/pelanggan`)
| Metode | Path | Akses | Keterangan |
|---|---|---|---|
| POST | `/auth/registrasi` | publik | `email`, `kata_sandi`, `nama` |
| POST | `/auth/login` | publik | mengembalikan JWT |
| GET/POST | `/auth/verifikasi` | bearer/body | validasi token (dipakai gateway & order) |
| GET/PUT | `/pelanggan/saya` | bearer | profil sendiri |
| PUT | `/pelanggan/saya/kata-sandi` | bearer | ganti kata sandi |
| GET | `/pelanggan` | admin | daftar pelanggan |
| GET/POST/PUT/DELETE | `/alamat`, `/alamat/<id>` | bearer | alamat pengiriman |
| POST | `/alamat/<id>/utama` | bearer | jadikan alamat utama |

## Order Service (`/api/order`)
| Metode | Path | Akses | Keterangan |
|---|---|---|---|
| GET/POST/PUT/DELETE | `/keranjang`, `/keranjang/<produk_id>` | bearer | keranjang belanja |
| POST | `/checkout` | bearer | saga: reserve stok → pesanan → inisiasi pembayaran |
| GET | `/pesanan` | bearer | riwayat (`status`, `halaman`, `batas`) |
| GET | `/pesanan/<id>` | bearer/admin | detail + jejak saga |
| POST | `/pesanan/<id>/batalkan` | bearer | batal + kompensasi stok |
| POST | `/internal/pesanan/<id>/pembayaran` | layanan | webhook status pembayaran |

## Pembayaran Service (`/api/pembayaran`)
| Metode | Path | Akses | Keterangan |
|---|---|---|---|
| POST | `/pembayaran` | layanan | inisiasi pembayaran (idempoten per pesanan) |
| GET | `/pembayaran`, `/pembayaran/<id>` | bearer/admin | status pembayaran |
| POST | `/pembayaran/<id>/simulasi` | admin | simulasi hasil (`berhasil`/`gagal`) |
| POST | `/internal/pembayaran/<id>/sinkronisasi` | layanan | kirim ulang webhook |
| GET | `/laporan/ringkasan` | admin | agregat `dari`/`sampai` |
| GET | `/laporan/transaksi.csv` | admin | ekspor CSV |

## Gateway
| Metode | Path | Keterangan |
|---|---|---|
| GET | `/` | dashboard toko |
| GET | `/admin` | dashboard admin |
| GET | `/api/ringkasan/toko` | agregasi produk + kategori |
| GET | `/api/ringkasan/admin` | agregasi pesanan + pembayaran |
| ANY | `/api/<layanan>/<path>` | proksi ke layanan tujuan |

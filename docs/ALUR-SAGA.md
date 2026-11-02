# Alur Checkout: Saga dengan Kompensasi

Checkout melibatkan tiga layanan sehingga tidak mungkin memakai satu transaksi basis data.
Order Service memakai **saga orkestrasi**: setiap langkah punya aksi maju dan aksi kompensasi.
Bila satu langkah gagal, langkah sebelumnya dibatalkan dengan urutan terbalik.

```
Klien ──POST /api/order/checkout──► Order Service
                                      │
        1. validasi_pelanggan ───────► Pelanggan Service  (baca profil + alamat)
                                      │
        2. reservasi_stok ───────────► Katalog Service    (stok_reserved += qty)
                                      │        kompensasi: POST /internal/reservasi/{id}/rilis
                                      │
        3. simpan_pesanan ───────────► SQLite order       (status MENUNGGU_PEMBAYARAN)
                                      │        kompensasi: status DIBATALKAN
                                      │
        4. inisiasi_pembayaran ──────► Pembayaran Service (tagihan MENUNGGU + referensi VA)
                                      │
                                      ▼
                            respons 201 + instruksi bayar
```

## Skenario gagal

| Langkah gagal | Efek kompensasi | Status pesanan |
|---|---|---|
| `reservasi_stok` (stok kurang) | tidak ada langkah sukses sebelumya | tidak dibuat |
| `simpan_pesanan` | rilis reservasi | tidak dibuat |
| `inisiasi_pembayaran` | pesanan DIBATALKAN + rilis reservasi | `DIBATALKAN` |
| pembayaran GAGAL/KEDALUWARSA (webhook) | rilis reservasi | `DIBATALKAN` |
| pembayaran BERHASIL (webhook) | komit reservasi (stok keluar permanen) | `DIBAYAR` |

Setiap langkah dan kompensasi dicatat pada tabel `saga_log` dan bisa dilihat pada
`GET /api/order/pesanan/<id>` (`jejak_saga`) maupun di dashboard admin.

## Uji cepat kompensasi

```bash
curl -X POST http://localhost:8000/api/order/checkout \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"simulasi":"gagal_pembayaran"}'
```

Respons `502 CHECKOUT_GAGAL` memuat `detail.kompensasi` dan `detail.jejak`. Stok pada
Katalog Service harus kembali seperti sebelum checkout (`stok_reserved` = 0).
Hook `simulasi` hanya aktif bila `SIMULASI_AKTIF=1` (bawaan pada mode pengembangan).

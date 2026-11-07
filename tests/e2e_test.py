"""
Tes end-to-end (Peserta 5): satu perjalanan pengguna lengkap melalui API Gateway.

Mencakup: katalog publik, registrasi & login, alamat, keranjang, checkout,
simulasi pembayaran oleh admin, perubahan status pesanan, stok permanen,
kompensasi saat pembayaran gagal, serta laporan transaksi.
"""
import unittest

from base import ADMIN_EMAIL, ApiKlien, butuh_layanan  # noqa: F401

GATEWAY = "http://127.0.0.1:8000"


@unittest.skipUnless(butuh_layanan(GATEWAY), "gateway tidak berjalan")
class TesEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = ApiKlien(GATEWAY)
        cls.admin = cls.api.token_admin()
        cls.admin_token = cls.admin["token"]

    # ------------------------------------------------------------------ pembantu
    def _produk_baru(self, stok=12, harga=75000):
        return self.api.post("/api/katalog/produk",
                             {"nama": "Kopi E2E " + self.api.acak(), "harga": harga, "stok": stok},
                             token=self.admin_token)["data"]

    def _pelanggan(self):
        email = f"e2e_{self.api.acak()}@contoh.test"
        data = self.api.post("/api/pelanggan/auth/registrasi",
                             {"email": email, "nama": "Pembeli E2E", "kata_sandi": "rahasia123"})["data"]
        token = data["token"]
        self.api.post("/api/pelanggan/alamat", {
            "label": "Rumah", "penerima": "Pembeli E2E", "telepon": "081200000123",
            "jalan": "Jl. End To End 7", "kota": "Bandung", "provinsi": "Jawa Barat",
            "kode_pos": "40115",
        }, token=token)
        return token, data["pengguna"]

    def _pesan(self, token, produk_id, qty=2, tambahan=None):
        self.api.post("/api/order/keranjang", {"produk_id": produk_id, "qty": qty}, token=token)
        badan = {"kurir": "reguler", "metode": "virtual_account"}
        if tambahan:
            badan.update(tambahan)
        return self.api.post("/api/order/checkout", badan, token=token)["data"]

    # ---------------------------------------------------------------------- tes
    def test_01_semua_layanan_sehat(self):
        data = self.api.get("/api/status")["data"]
        self.assertTrue(data["sehat"], data)
        for nama in ("katalog", "pelanggan", "order", "pembayaran"):
            self.assertEqual(data["layanan"][nama]["status"], "ok")

    def test_02_katalog_publik(self):
        produk = self.api.get("/api/katalog/produk")["data"]
        self.assertIsInstance(produk, list)
        kategori = self.api.get("/api/katalog/kategori")["data"]
        self.assertIsInstance(kategori, list)

    def test_03_perjalanan_beli_lengkap(self):
        token, pengguna = self._pelanggan()
        produk = self._produk_baru(stok=12, harga=75000)
        self.assertEqual(produk["stok_tersedia"], 12)

        hasil = self._pesan(token, produk["id"], qty=3)
        pesanan = hasil["pesanan"]
        tagihan = hasil["pembayaran"]
        self.assertEqual(pesanan["status"], "MENUNGGU_PEMBAYARAN")
        self.assertEqual(pesanan["subtotal"], 3 * 75000)
        self.assertEqual(pesanan["ongkir"], 15000)
        self.assertEqual(pesanan["total"], 3 * 75000 + 15000)
        self.assertIsNotNone(tagihan)
        self.assertEqual(tagihan["status"], "MENUNGGU")
        self.assertTrue(tagihan["referensi"].isdigit())

        # stok ditahan, belum berkurang permanen
        sesudah_reserve = self.api.get(f"/api/katalog/produk/{produk['id']}")["data"]
        self.assertEqual(sesudah_reserve["stok"], 12)
        self.assertEqual(sesudah_reserve["stok_reserved"], 3)

        # admin mensimulasikan pembayaran berhasil
        simulasi = self.api.post(f"/api/pembayaran/pembayaran/{tagihan['id']}/simulasi",
                                 {"hasil": "berhasil"}, token=self.admin_token)["data"]
        self.assertEqual(simulasi["status"], "BERHASIL")

        # pesanan menjadi DIBAYAR dan stok keluar permanen
        detail = self.api.get(f"/api/order/pesanan/{pesanan['id']}", token=token)["data"]
        self.assertEqual(detail["status"], "DIBAYAR")
        langkah = [(j["langkah"], j["jenis"], j["status"]) for j in detail["jejak_saga"]]
        self.assertIn(("komit_stok", "AKSI", "SUKSES"), langkah)
        akhir = self.api.get(f"/api/katalog/produk/{produk['id']}")["data"]
        self.assertEqual((akhir["stok"], akhir["stok_reserved"]), (12 - 3, 0))

        # admin memajukan status pesanan
        maju = self.api.post(f"/api/order/pesanan/{pesanan['id']}/status",
                             {"status": "DIKEMAS"}, token=self.admin_token)["data"]
        self.assertEqual(maju["status"], "DIKEMAS")

        # laporan mencatat transaksi berhasil
        laporan = self.api.get("/api/pembayaran/laporan/ringkasan", token=self.admin_token)["data"]
        self.assertGreaterEqual(laporan["per_status"].get("BERHASIL", 0), 1)
        self.assertGreater(laporan["nominal_berhasil"], 0)

    def test_04_kompensasi_saat_pembayaran_gagal(self):
        token, _ = self._pelanggan()
        produk = self._produk_baru(stok=5, harga=30000)
        self.api.post("/api/order/keranjang", {"produk_id": produk["id"], "qty": 4}, token=token)
        r = self.api.get_raw("/api/order/checkout", method="POST",
                             json={"simulasi": "gagal_pembayaran"}, token=token)
        self.assertEqual(r.status_code, 502, r.text)
        detail = r.json()["error"]["detail"]
        self.assertEqual(detail["langkah_gagal"], "inisiasi_pembayaran")
        nama = [k["langkah"] for k in detail["kompensasi"]]
        self.assertIn("reservasi_stok", nama)
        self.assertIn("simpan_pesanan", nama)
        stok = self.api.get(f"/api/katalog/produk/{produk['id']}")["data"]
        self.assertEqual(stok["stok_reserved"], 0)
        self.assertEqual(stok["stok_tersedia"], 5)

    def test_05_pembayaran_gagal_membatalkan_pesanan(self):
        token, _ = self._pelanggan()
        produk = self._produk_baru(stok=6, harga=15000)
        hasil = self._pesan(token, produk["id"], qty=2)
        pesanan, tagihan = hasil["pesanan"], hasil["pembayaran"]
        self.api.post(f"/api/pembayaran/pembayaran/{tagihan['id']}/simulasi",
                      {"hasil": "gagal"}, token=self.admin_token)
        detail = self.api.get(f"/api/order/pesanan/{pesanan['id']}", token=token)["data"]
        self.assertEqual(detail["status"], "DIBATALKAN")
        stok = self.api.get(f"/api/katalog/produk/{produk['id']}")["data"]
        self.assertEqual((stok["stok"], stok["stok_reserved"]), (6, 0))

        # simulasi kedua ditolak karena status sudah final
        r = self.api.get_raw(f"/api/pembayaran/pembayaran/{tagihan['id']}/simulasi",
                             method="POST", json={"hasil": "berhasil"}, token=self.admin_token)
        self.assertEqual(r.status_code, 409)

    def test_06_keranjang_dan_riwayat_terpisah_per_pelanggan(self):
        token_a, _ = self._pelanggan()
        token_b, _ = self._pelanggan()
        produk = self._produk_baru(stok=3)
        self.api.post("/api/order/keranjang", {"produk_id": produk["id"], "qty": 1}, token=token_a)
        self.assertEqual(self.api.get("/api/order/keranjang", token=token_a)["data"]["jumlah_item"], 1)
        self.assertEqual(self.api.get("/api/order/keranjang", token=token_b)["data"]["jumlah_item"], 0)
        self.assertEqual(self.api.get("/api/order/pesanan", token=token_b)["data"], [])

    def test_07_proteksi_gateway(self):
        for path, metode in (("/api/order/keranjang", "GET"),
                             ("/api/order/pesanan", "GET"),
                             ("/api/pembayaran/pembayaran", "GET")):
            r = self.api.get_raw(path, method=metode)
            self.assertEqual(r.status_code, 401, path)
        r = self.api.get_raw("/api/katalog/internal/reservasi/x")
        self.assertEqual(r.status_code, 404)

    def test_08_validasi_stok_dan_kuantitas(self):
        token_a, _ = self._pelanggan()
        token_b, _ = self._pelanggan()
        produk = self._produk_baru(stok=1, harga=10000)
        # qty melebihi stok langsung ditolak saat masuk keranjang
        r = self.api.get_raw("/api/order/keranjang", method="POST",
                             json={"produk_id": produk["id"], "qty": 99}, token=token_a)
        self.assertEqual(r.status_code, 409)
        # dua pelanggan sama-sama menaruh sisa stok terakhir di keranjang
        self.api.post("/api/order/keranjang", {"produk_id": produk["id"], "qty": 1}, token=token_a)
        self.api.post("/api/order/keranjang", {"produk_id": produk["id"], "qty": 1}, token=token_b)
        # B checkout lebih dulu -> berhasil menahan stok, A gagal karena stok sudah ditahan
        hasil_b = self.api.post("/api/order/checkout", {}, token=token_b)["data"]
        self.assertEqual(hasil_b["pesanan"]["status"], "MENUNGGU_PEMBAYARAN")
        r2 = self.api.get_raw("/api/order/checkout", method="POST", json={}, token=token_a)
        self.assertEqual(r2.status_code, 409, r2.text)
        self.assertEqual(r2.json()["error"]["kode"], "STOK_TIDAK_CUKUP")
        stok = self.api.get(f"/api/katalog/produk/{produk['id']}")["data"]
        self.assertEqual(stok["stok_reserved"], 1)

    def test_09_dashboard_dapat_diakses(self):
        toko = self.api.get_raw("/")
        admin = self.api.get_raw("/admin")
        self.assertEqual(toko.status_code, 200)
        self.assertEqual(admin.status_code, 200)
        self.assertIn("Toko Online", toko.text)
        self.assertIn("Dashboard Admin", admin.text)

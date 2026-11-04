"""Tes Order Service (Peserta 3): keranjang, checkout saga, kompensasi, riwayat."""
import unittest

from base import ApiKlien, butuh_layanan

KATALOG = "http://127.0.0.1:8001"
PELANGGAN = "http://127.0.0.1:8002"
ORDER = "http://127.0.0.1:8003"


@unittest.skipUnless(butuh_layanan(ORDER) and butuh_layanan(KATALOG) and butuh_layanan(PELANGGAN),
                     "order/katalog/pelanggan belum berjalan")
class TesOrder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.katalog = ApiKlien(KATALOG)
        cls.pelanggan = ApiKlien(PELANGGAN)
        cls.order = ApiKlien(ORDER)
        cls.admin = cls.katalog.token_admin()
        cls.svc = {"X-Service-Token": "token-antar-layanan-dev"}

    def pelanggan_baru(self):
        email = f"beli_{self.order.acak()}@contoh.test"
        data = self.pelanggan.post("/auth/registrasi",
                                   {"email": email, "nama": "Pembeli Uji", "kata_sandi": "rahasia123"})["data"]
        token = data["token"]
        self.pelanggan.post("/alamat", {
            "label": "Rumah", "penerima": "Pembeli Uji", "telepon": "081200000009",
            "jalan": "Jl. Uji 10", "kota": "Bandung", "provinsi": "Jawa Barat", "kode_pos": "40111",
        }, token=token)
        return token

    def produk(self, stok=10, harga=50000):
        return self.katalog.post("/produk", {"nama": "Barang Uji " + self.order.acak(),
                                             "harga": harga, "stok": stok},
                                 token=self.admin["token"])["data"]

    def test_01_keranjang_kosong(self):
        token = self.pelanggan_baru()
        isi = self.order.get("/keranjang", token=token)["data"]
        self.assertEqual(isi["jumlah_item"], 0)
        r = self.order.get_raw("/checkout", method="POST", json={}, token=token)
        self.assertEqual(r.status_code, 422)

    def test_02_tambah_ubah_hapus_keranjang(self):
        token = self.pelanggan_baru()
        p = self.produk()
        self.order.post("/keranjang", {"produk_id": p["id"], "qty": 2}, token=token)
        isi = self.order.post("/keranjang", {"produk_id": p["id"], "qty": 1}, token=token)["data"]
        self.assertEqual(isi["items"][0]["qty"], 3)
        self.assertEqual(isi["total"], 3 * p["harga"])
        self.order.put(f"/keranjang/{p['id']}", {"qty": 5}, token=token)
        self.assertEqual(self.order.get("/keranjang", token=token)["data"]["total"], 5 * p["harga"])
        self.order.delete(f"/keranjang/{p['id']}", token=token)
        self.assertEqual(self.order.get("/keranjang", token=token)["data"]["jumlah_item"], 0)

    def test_03_checkout_berhasil_dan_stok_ditahan(self):
        token = self.pelanggan_baru()
        p = self.produk(stok=10, harga=40000)
        self.order.post("/keranjang", {"produk_id": p["id"], "qty": 4}, token=token)
        hasil = self.order.post("/checkout", {}, token=token)["data"]
        pesanan = hasil["pesanan"]
        self.assertEqual(pesanan["status"], "MENUNGGU_PEMBAYARAN")
        self.assertEqual(pesanan["subtotal"], 160000)
        self.assertEqual(pesanan["ongkir"], 15000)
        self.assertEqual(pesanan["total"], 175000)
        self.assertTrue(pesanan["nomor"].startswith("ORD-"))
        self.assertEqual(self.order.get("/keranjang", token=token)["data"]["jumlah_item"], 0)
        stok = self.katalog.get(f"/produk/{p['id']}")["data"]
        self.assertEqual(stok["stok_reserved"], 4)
        langkah = [j["langkah"] for j in pesanan["jejak_saga"] if j["jenis"] == "AKSI" and j["status"] == "SUKSES"]
        self.assertIn("reservasi_stok", langkah)
        self.assertIn("simpan_pesanan", langkah)

    def test_04_kompensasi_saat_inisiasi_pembayaran_gagal(self):
        """Bila langkah setelah reserve gagal, stok harus kembali dan pesanan dibatalkan."""
        token = self.pelanggan_baru()
        p = self.produk(stok=6, harga=20000)
        self.order.post("/keranjang", {"produk_id": p["id"], "qty": 5}, token=token)
        r = self.order.get_raw("/checkout", method="POST", json={"simulasi": "gagal_pembayaran"}, token=token)
        self.assertIn(r.status_code, (502, 409), r.text)
        body = r.json()
        self.assertFalse(body["success"])
        detail = body["error"].get("detail") or {}
        self.assertEqual(detail.get("langkah_gagal"), "inisiasi_pembayaran")
        nama_kompensasi = [k["langkah"] for k in detail.get("kompensasi", [])]
        self.assertIn("reservasi_stok", nama_kompensasi)
        self.assertIn("simpan_pesanan", nama_kompensasi)
        stok = self.katalog.get(f"/produk/{p['id']}")["data"]
        self.assertEqual(stok["stok_reserved"], 0, "stok harus dikembalikan setelah kompensasi")
        self.assertEqual(stok["stok_tersedia"], 6)

    def test_05_stok_kurang_saat_checkout(self):
        token = self.pelanggan_baru()
        p = self.produk(stok=3)
        self.order.post("/keranjang", {"produk_id": p["id"], "qty": 3}, token=token)
        # Habiskan stok lewat reservasi lain setelah item masuk keranjang.
        self.katalog.post("/internal/reservasi",
                          {"order_ref": "saingan", "items": [{"produk_id": p["id"], "qty": 3}]},
                          headers=self.svc)
        r = self.order.get_raw("/checkout", method="POST", json={}, token=token)
        self.assertEqual(r.status_code, 409)
        self.assertIn("stok", r.json()["error"]["pesan"].lower())

    def test_06_riwayat_dan_detail(self):
        token = self.pelanggan_baru()
        p = self.produk()
        self.order.post("/keranjang", {"produk_id": p["id"], "qty": 1}, token=token)
        oid = self.order.post("/checkout", {}, token=token)["data"]["pesanan"]["id"]
        riwayat = self.order.get("/pesanan", token=token)["data"]
        self.assertEqual(len(riwayat), 1)
        detail = self.order.get(f"/pesanan/{oid}", token=token)["data"]
        self.assertEqual(detail["items"][0]["qty"], 1)

    def test_07_pesanan_orang_lain_tidak_bisa_dilihat(self):
        token_a = self.pelanggan_baru()
        token_b = self.pelanggan_baru()
        p = self.produk()
        self.order.post("/keranjang", {"produk_id": p["id"], "qty": 1}, token=token_a)
        oid = self.order.post("/checkout", {}, token=token_a)["data"]["pesanan"]["id"]
        r = self.order.get_raw(f"/pesanan/{oid}", token=token_b)
        self.assertEqual(r.status_code, 403)

    def test_08_batalkan_mengembalikan_stok(self):
        token = self.pelanggan_baru()
        p = self.produk(stok=8)
        self.order.post("/keranjang", {"produk_id": p["id"], "qty": 2}, token=token)
        oid = self.order.post("/checkout", {}, token=token)["data"]["pesanan"]["id"]
        hasil = self.order.post(f"/pesanan/{oid}/batalkan", {"alasan": "berubah pikiran"}, token=token)["data"]
        self.assertEqual(hasil["status"], "DIBATALKAN")
        stok = self.katalog.get(f"/produk/{p['id']}")["data"]
        self.assertEqual((stok["stok"], stok["stok_reserved"]), (8, 0))


if __name__ == "__main__":
    unittest.main()

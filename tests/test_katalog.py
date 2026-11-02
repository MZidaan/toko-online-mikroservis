"""Tes Katalog Service (Peserta 1): CRUD, reserve, komit, rilis, validasi stok."""
import unittest

from base import ApiKlien, butuh_layanan

KATALOG = "http://127.0.0.1:8001"


@unittest.skipUnless(butuh_layanan(KATALOG), "katalog-service tidak berjalan")
class TesKatalog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = ApiKlien(KATALOG)
        cls.admin = cls.api.token_admin()
        cls.pelanggan = cls.api.token_pelanggan()
        cls.svc = {"X-Service-Token": "token-antar-layanan-dev"}

    def buat_produk(self, stok=10, harga=25000):
        body = self.api.post(
            "/produk",
            {"nama": "Produk Uji " + self.api.acak(), "harga": harga, "stok": stok},
            token=self.admin["token"],
        )
        self.assertEqual(body["success"], True)
        return body["data"]

    def test_01_health_dan_kategori(self):
        self.assertEqual(self.api.get_raw("/health").status_code, 200)
        nama = "Kategori Uji " + self.api.acak()
        r = self.api.post("/kategori", {"nama": nama}, token=self.admin["token"])
        self.assertTrue(r["success"])
        daftar = self.api.get("/kategori")["data"]
        self.assertTrue(any(k["nama"] == nama for k in daftar))

    def test_02_produk_wajib_admin(self):
        r = self.api.get_raw("/produk", method="POST", json={"nama": "X", "harga": 1},
                             token=self.pelanggan["token"])
        self.assertEqual(r.status_code, 403)

    def test_03_produk_crud_dan_pencarian(self):
        p = self.buat_produk(stok=7)
        self.assertEqual(p["stok_tersedia"], 7)
        ubah = self.api.put(f"/produk/{p['id']}", {"harga": 99000}, token=self.admin["token"])
        self.assertEqual(ubah["data"]["harga"], 99000)
        cari = self.api.get("/produk", {"q": p["sku"][:6]})["data"]
        self.assertTrue(any(x["id"] == p["id"] for x in cari))
        self.api.delete(f"/produk/{p['id']}", token=self.admin["token"])
        self.assertEqual(self.api.get(f"/produk/{p['id']}")["data"]["aktif"], False)

    def test_04_reserve_komit_mengurangi_stok(self):
        p = self.buat_produk(stok=5, harga=10000)
        rsv = self.api.post(
            "/internal/reservasi",
            {"order_ref": "uji-" + self.api.acak(), "items": [{"produk_id": p["id"], "qty": 3}]},
            headers=self.svc,
        )["data"]
        self.assertEqual(rsv["status"], "AKTIF")
        self.assertEqual(rsv["total"], 30000)
        sesudah = self.api.get(f"/produk/{p['id']}")["data"]
        self.assertEqual(sesudah["stok"], 5)
        self.assertEqual(sesudah["stok_reserved"], 3)
        self.assertEqual(sesudah["stok_tersedia"], 2)
        komit = self.api.post(f"/internal/reservasi/{rsv['id']}/komit", {}, headers=self.svc)["data"]
        self.assertEqual(komit["status"], "DIKOMIT")
        akhir = self.api.get(f"/produk/{p['id']}")["data"]
        self.assertEqual((akhir["stok"], akhir["stok_reserved"]), (2, 0))

    def test_05_rilis_mengembalikan_stok(self):
        p = self.buat_produk(stok=4)
        rsv = self.api.post(
            "/internal/reservasi",
            {"order_ref": "uji-" + self.api.acak(), "items": [{"produk_id": p["id"], "qty": 4}]},
            headers=self.svc,
        )["data"]
        self.api.post(f"/internal/reservasi/{rsv['id']}/rilis", {}, headers=self.svc)
        sesudah = self.api.get(f"/produk/{p['id']}")["data"]
        self.assertEqual((sesudah["stok"], sesudah["stok_reserved"]), (4, 0))
        # rilis dua kali tetap aman (idempoten)
        self.api.post(f"/internal/reservasi/{rsv['id']}/rilis", {}, headers=self.svc)
        self.assertEqual(self.api.get(f"/produk/{p['id']}")["data"]["stok_tersedia"], 4)

    def test_06_reserve_melebihi_stok_ditolak(self):
        p = self.buat_produk(stok=2)
        r = self.api.get_raw(
            "/internal/reservasi", method="POST", headers=self.svc,
            json={"order_ref": "uji-x", "items": [{"produk_id": p["id"], "qty": 5}]},
        )
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["error"]["kode"], "STOK_TIDAK_CUKUP")
        self.assertEqual(self.api.get(f"/produk/{p['id']}")["data"]["stok_reserved"], 0)

    def test_07_internal_tanpa_token_ditolak(self):
        r = self.api.get_raw("/internal/reservasi", method="POST",
                             json={"order_ref": "x", "items": []})
        self.assertEqual(r.status_code, 401)

    def test_08_tambah_stok(self):
        p = self.buat_produk(stok=1)
        hasil = self.api.post(f"/produk/{p['id']}/stok", {"tambah": 9}, token=self.admin["token"])
        self.assertEqual(hasil["data"]["stok"], 10)


if __name__ == "__main__":
    unittest.main()

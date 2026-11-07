"""Tes API Gateway & dashboard (Peserta 5): proksi, proteksi JWT, agregasi, halaman."""
import unittest

from base import ApiKlien, butuh_layanan

GATEWAY = "http://127.0.0.1:8000"


@unittest.skipUnless(butuh_layanan(GATEWAY), "gateway tidak berjalan")
class TesGateway(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = ApiKlien(GATEWAY)

    def test_01_halaman_dashboard(self):
        for path, kata in (("/", "Toko Online"), ("/admin", "Dashboard Admin")):
            r = self.api.get_raw(path)
            self.assertEqual(r.status_code, 200)
            self.assertIn(kata, r.text)
            self.assertIn("text/html", r.headers["Content-Type"])

    def test_02_produk_publik_tanpa_token(self):
        r = self.api.get_raw("/api/katalog/produk")
        self.assertEqual(r.status_code, 200)
        self.assertIn("data", r.json())

    def test_03_keranjang_tanpa_token_ditolak(self):
        r = self.api.get_raw("/api/order/keranjang")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["error"]["kode"], "BELUM_LOGIN")

    def test_04_login_lewat_gateway(self):
        email = f"gw_{self.api.acak()}@contoh.test"
        daftar = self.api.post("/api/pelanggan/auth/registrasi",
                               {"email": email, "nama": "Lewat Gateway", "kata_sandi": "rahasia123"})
        self.assertTrue(daftar["success"])
        token = daftar["data"]["token"]
        login = self.api.post("/api/pelanggan/auth/login",
                              {"email": email, "kata_sandi": "rahasia123"})
        self.assertEqual(login["data"]["pengguna"]["email"], email)
        isi = self.api.get("/api/order/keranjang", token=token)
        self.assertEqual(isi["data"]["jumlah_item"], 0)

    def test_05_endpoint_internal_disembunyikan(self):
        r = self.api.get_raw("/api/katalog/internal/reservasi/abc")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["error"]["kode"], "TIDAK_DITEMUKAN")

    def test_06_layanan_tidak_dikenal(self):
        r = self.api.get_raw("/api/entah/apa")
        self.assertEqual(r.status_code, 404)

    def test_07_ringkasan_toko(self):
        data = self.api.get("/api/ringkasan/toko")["data"]
        self.assertIn("produk", data)
        self.assertIn("kategori", data)

    def test_08_ringkasan_admin_butuh_peran(self):
        email = f"gw_{self.api.acak()}@contoh.test"
        token = self.api.post("/api/pelanggan/auth/registrasi",
                              {"email": email, "nama": "Biasa", "kata_sandi": "rahasia123"})["data"]["token"]
        r = self.api.get_raw("/api/ringkasan/admin", token=token)
        self.assertEqual(r.status_code, 403)
        admin = self.api.token_admin()
        r2 = self.api.get_raw("/api/ringkasan/admin", token=admin["token"])
        self.assertEqual(r2.status_code, 200)
        self.assertIn("statistik_pesanan", r2.json()["data"])

    def test_09_status_layanan(self):
        r = self.api.get_raw("/api/status")
        self.assertIn(r.status_code, (200, 503))
        self.assertIn("layanan", r.json()["data"])


if __name__ == "__main__":
    unittest.main()

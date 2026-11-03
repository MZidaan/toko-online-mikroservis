"""Tes Pelanggan Service (Peserta 2): registrasi, login JWT, verifikasi, alamat."""
import unittest

from base import ApiKlien, butuh_layanan

PELANGGAN = "http://127.0.0.1:8002"


@unittest.skipUnless(butuh_layanan(PELANGGAN), "pelanggan-service tidak berjalan")
class TesPelanggan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = ApiKlien(PELANGGAN)

    def daftar(self, sandi="rahasia123"):
        email = f"uji_{self.api.acak()}@contoh.test"
        body = self.api.post("/auth/registrasi", {"email": email, "nama": "Uji Coba", "kata_sandi": sandi})
        self.assertTrue(body["success"], body)
        return email, sandi, body["data"]

    def test_01_registrasi_dan_login(self):
        email, sandi, data = self.daftar()
        self.assertEqual(data["pengguna"]["peran"], "pelanggan")
        self.assertIn("token", data)
        login = self.api.post("/auth/login", {"email": email, "kata_sandi": sandi})["data"]
        self.assertTrue(login["token"].count(".") == 2)

    def test_02_login_salah_ditolak(self):
        email, _, _ = self.daftar()
        r = self.api.get_raw("/auth/login", method="POST", json={"email": email, "kata_sandi": "salahbanget"})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["error"]["kode"], "KREDENSIAL_SALAH")

    def test_03_email_duplikat_ditolak(self):
        email, sandi, _ = self.daftar()
        r = self.api.get_raw("/auth/registrasi", method="POST",
                             json={"email": email.upper(), "nama": "Duplikat", "kata_sandi": sandi})
        self.assertEqual(r.status_code, 409)

    def test_04_verifikasi_token(self):
        _, _, data = self.daftar()
        hasil = self.api.get("/auth/verifikasi", token=data["token"])["data"]
        self.assertTrue(hasil["valid"])
        self.assertEqual(hasil["pengguna"]["email"], data["pengguna"]["email"])
        r = self.api.get_raw("/auth/verifikasi", token="token.palsu.sekali")
        self.assertEqual(r.status_code, 401)

    def test_05_profil_dan_ganti_sandi(self):
        email, sandi, data = self.daftar("rahasia123")
        token = data["token"]
        profil = self.api.get("/pelanggan/saya", token=token)["data"]
        self.assertEqual(profil["email"], email)
        self.api.put("/pelanggan/saya", {"nama": "Nama Baru"}, token=token)
        baru = self.api.put("/pelanggan/saya/kata-sandi",
                            {"kata_sandi_lama": "rahasia123", "kata_sandi_baru": "rahasia456"},
                            token=token)
        self.assertTrue(baru["success"])
        self.api.post("/auth/login", {"email": email, "kata_sandi": "rahasia456"})

    def test_06_kelola_alamat_dan_utama(self):
        _, _, data = self.daftar()
        token = data["token"]
        a1 = self.api.post("/alamat", {
            "label": "Rumah", "penerima": "Uji", "telepon": "081200000001",
            "jalan": "Jl. Merdeka 1", "kota": "Bandung", "provinsi": "Jawa Barat",
            "kode_pos": "40111",
        }, token=token)["data"]
        self.assertEqual(a1["utama"], 1)
        a2 = self.api.post("/alamat", {
            "label": "Kantor", "penerima": "Uji", "telepon": "081200000002",
            "jalan": "Jl. Asia Afrika 2", "kota": "Bandung", "provinsi": "Jawa Barat",
            "kode_pos": "40112",
        }, token=token)["data"]
        self.api.post(f"/alamat/{a2['id']}/utama", {}, token=token)
        daftar = self.api.get("/alamat", token=token)["data"]
        utama = [a for a in daftar if a["utama"]]
        self.assertEqual(len(utama), 1)
        self.assertEqual(utama[0]["id"], a2["id"])

    def test_07_alamat_milik_orang_lain_ditolak(self):
        _, _, saya = self.daftar()
        _, _, lain = self.daftar()
        alamat = self.api.post("/alamat", {
            "penerima": "Orang", "telepon": "08123", "jalan": "Jl. X", "kota": "Bogor",
            "provinsi": "Jawa Barat", "kode_pos": "16111",
        }, token=lain["token"])["data"]
        r = self.api.get_raw(f"/alamat/{alamat['id']}", method="PUT",
                             json={"kota": "Depok"}, token=saya["token"])
        self.assertEqual(r.status_code, 403)

    def test_08_validasi_input(self):
        r = self.api.get_raw("/auth/registrasi", method="POST",
                             json={"email": "bukan-email", "nama": "", "kata_sandi": "123"})
        self.assertEqual(r.status_code, 422)
        r2 = self.api.get_raw("/auth/registrasi", method="POST",
                              json={"email": "ok@contoh.test", "nama": "A", "kata_sandi": "pendek"})
        self.assertEqual(r2.status_code, 422)


if __name__ == "__main__":
    unittest.main()

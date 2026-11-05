"""Tes Pembayaran Service (Peserta 4): inisiasi idempoten, simulasi, webhook, laporan."""
import unittest

from base import ApiKlien, butuh_layanan

PEMBAYARAN = "http://127.0.0.1:8004"
ORDER = "http://127.0.0.1:8003"


@unittest.skipUnless(butuh_layanan(PEMBAYARAN) and butuh_layanan(ORDER),
                     "pembayaran/order belum berjalan")
class TesPembayaran(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bayar = ApiKlien(PEMBAYARAN)
        cls.order = ApiKlien(ORDER)
        cls.svc = {"X-Service-Token": "token-antar-layanan-dev"}
        cls.admin = cls.bayar.token_admin()

    def pesanan_menunggu(self):
        """Buat pesanan lewat alur nyata agar tagihan tersedia."""
        hasil = self.order.pesan_contoh()
        return hasil

    def test_01_inisiasi_idempoten(self):
        konteks = self.order.pesan_contoh(bayar=False)
        pid = konteks["pesanan_id"]
        a = self.bayar.post("/pembayaran", {"pesanan_id": pid, "nomor_pesanan": "ORD-UJI",
                                            "pelanggan_id": konteks["pelanggan_id"], "jumlah": 50000},
                            headers=self.svc)
        self.assertTrue(a["success"])
        b = self.bayar.post("/pembayaran", {"pesanan_id": pid, "nomor_pesanan": "ORD-UJI",
                                            "pelanggan_id": konteks["pelanggan_id"], "jumlah": 50000},
                            headers=self.svc)
        self.assertEqual(b["data"]["id"], a["data"]["id"])
        self.assertTrue(b["data"]["idempoten"])
        self.assertGreaterEqual(len(b["data"]["event"]), 2)
        self.assertEqual(b["data"]["event"][0]["jenis"], "INISIASI")

    def test_02_simulasi_berhasil_mengubah_status_pesanan(self):
        konteks = self.order.pesan_contoh(bayar=False)
        tagihan = self.bayar.post("/pembayaran", {
            "pesanan_id": konteks["pesanan_id"], "nomor_pesanan": konteks["nomor"],
            "pelanggan_id": konteks["pelanggan_id"], "jumlah": 50000,
        }, headers=self.svc)["data"]
        hasil = self.bayar.post(f"/pembayaran/{tagihan['id']}/simulasi", {"hasil": "berhasil"},
                               token=self.admin["token"])["data"]
        self.assertEqual(hasil["status"], "BERHASIL")
        self.assertIsNotNone(hasil["dibayar_at"])
        pesanan = self.order.get(f"/pesanan/{konteks['pesanan_id']}",
                                 token=konteks["token"])["data"]
        self.assertEqual(pesanan["status"], "DIBAYAR")

    def test_03_simulasi_gagal_mengembalikan_stok(self):
        konteks = self.order.pesan_contoh(bayar=False)
        tagihan = self.bayar.post("/pembayaran", {
            "pesanan_id": konteks["pesanan_id"], "nomor_pesanan": konteks["nomor"],
            "pelanggan_id": konteks["pelanggan_id"], "jumlah": 50000,
        }, headers=self.svc)["data"]
        self.bayar.post(f"/pembayaran/{tagihan['id']}/simulasi", {"hasil": "gagal"},
                        token=self.admin["token"])
        pesanan = self.order.get(f"/pesanan/{konteks['pesanan_id']}",
                                 token=konteks["token"])["data"]
        self.assertEqual(pesanan["status"], "DIBATALKAN")
        stok = self.order.stok_produk(konteks["produk_id"])
        self.assertEqual(stok["stok_reserved"], 0)

    def test_04_sinkronisasi_ulang_webhook(self):
        konteks = self.order.pesan_contoh(bayar=False)
        tagihan = self.bayar.post("/pembayaran", {
            "pesanan_id": konteks["pesanan_id"], "nomor_pesanan": konteks["nomor"],
            "pelanggan_id": konteks["pelanggan_id"], "jumlah": 50000,
        }, headers=self.svc)["data"]
        self.bayar.post(f"/pembayaran/{tagihan['id']}/simulasi", {"hasil": "berhasil"},
                        token=self.admin["token"])
        ulang = self.bayar.post(f"/internal/pembayaran/{tagihan['id']}/sinkronisasi", {},
                                headers=self.svc)["data"]
        self.assertTrue(ulang["webhook"]["terkirim"])
        self.assertGreaterEqual(ulang["pembayaran"]["jumlah_webhook"], 1)

    def test_05_laporan_ringkasan_dan_csv(self):
        ringkas = self.bayar.get("/laporan/ringkasan", token=self.admin["token"])["data"]
        self.assertIn("per_status", ringkas)
        self.assertGreaterEqual(ringkas["jumlah_transaksi"], 1)
        csv = self.bayar.get_raw("/laporan/transaksi.csv", token=self.admin["token"])
        self.assertEqual(csv.status_code, 200)
        self.assertIn("text/csv", csv.headers["Content-Type"])
        self.assertIn("nomor_pesanan", csv.text)

    def test_06_metode_tidak_dikenal_ditolak(self):
        konteks = self.order.pesan_contoh(bayar=False)
        r = self.bayar.get_raw("/pembayaran", method="POST", headers=self.svc,
                               json={"pesanan_id": konteks["pesanan_id"], "jumlah": 1000,
                                     "metode": "bitcoin"})
        self.assertEqual(r.status_code, 422)


if __name__ == "__main__":
    unittest.main()

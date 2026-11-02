"""
Basis bersama untuk seluruh tes: klien HTTP tipis, pengecekan ketersediaan layanan,
pembuatan token admin, dan pembantu alur pesanan.

Berkas ini juga dipakai skrip seed dan e2e, jadi tidak bergantung pada pytest.
"""
import os
import sys
import uuid

import requests

AKAR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if AKAR not in sys.path:
    sys.path.insert(0, AKAR)

from common.jwtutil import buat_token  # noqa: E402

SEKRET = os.environ.get("JWT_SECRET", "dev-secret-jangan-dipakai-di-produksi")
TOKEN_LAYANAN = os.environ.get("SERVICE_TOKEN", "token-antar-layanan-dev")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@contoh.test")
ADMIN_SANDI = os.environ.get("ADMIN_SANDI", "admin12345")

URL = {
    "katalog": os.environ.get("KATALOG_URL", "http://127.0.0.1:8001"),
    "pelanggan": os.environ.get("PELANGGAN_URL", "http://127.0.0.1:8002"),
    "order": os.environ.get("ORDER_URL", "http://127.0.0.1:8003"),
    "pembayaran": os.environ.get("PEMBAYARAN_URL", "http://127.0.0.1:8004"),
    "gateway": os.environ.get("GATEWAY_URL", "http://127.0.0.1:8000"),
}

_cache_admin = {}


def butuh_layanan(basis, detik=1.5):
    """True bila /health layanan menjawab 200 (dipakai skipUnless)."""
    try:
        return requests.get(basis.rstrip("/") + "/health", timeout=detik).status_code == 200
    except requests.RequestException:
        return False


class Jawaban:
    """Pembungkus respons agar tes ringkas: .status_code/.json()/.text/.headers."""

    def __init__(self, respons):
        self._r = respons

    @property
    def status_code(self):
        return self._r.status_code

    @property
    def headers(self):
        return self._r.headers

    @property
    def text(self):
        return self._r.text

    def json(self):
        try:
            return self._r.json()
        except ValueError:
            return {"success": False, "error": {"kode": "BUKAN_JSON", "pesan": self._r.text[:300]}}


def _admin_baru():
    """Buat/ambil akun admin nyata agar token lolos verifikasi gateway."""
    bila = _cache_admin.get("data")
    if bila:
        return bila
    try:
        r = requests.post(
            URL["pelanggan"] + "/internal/pelanggan/buat-admin",
            json={"email": ADMIN_EMAIL, "nama": "Administrator Toko", "kata_sandi": ADMIN_SANDI},
            headers={"X-Service-Token": TOKEN_LAYANAN}, timeout=5,
        )
        data = r.json()["data"]
        hasil = {"token": data["token"], "pengguna": data["pengguna"]}
    except Exception:  # noqa: BLE001 - layanan pelanggan mungkin belum hidup
        sekarang = int(__import__("time").time())
        token = buat_token({"sub": "1", "email": ADMIN_EMAIL, "nama": "Administrator Toko",
                            "peran": "admin", "iat": sekarang, "exp": sekarang + 3600}, SEKRET)
        hasil = {"token": token, "pengguna": {"id": 1, "email": ADMIN_EMAIL,
                                              "nama": "Administrator Toko", "peran": "admin"}}
    _cache_admin["data"] = hasil
    return hasil


class ApiKlien:
    """Klien HTTP sederhana untuk satu layanan (atau gateway)."""

    def __init__(self, basis, batas=15):
        self.basis = basis.rstrip("/")
        self.batas = batas

    # ------------------------------------------------------------------ dasar
    @staticmethod
    def acak(n=8):
        return uuid.uuid4().hex[:n]

    def _header(self, token=None, headers=None, json_=None):
        h = {"Accept": "application/json"}
        if json_ is not None:
            h["Content-Type"] = "application/json"
        if token:
            h["Authorization"] = f"Bearer {token}"
        if headers:
            h.update(headers)
        return h

    def kirim(self, method, path, json=None, params=None, headers=None, token=None):
        url = self.basis + "/" + path.lstrip("/")
        return Jawaban(requests.request(method, url, json=json, params=params,
                                        headers=self._header(token, headers, json),
                                        timeout=self.batas))

    def get_raw(self, path, method="GET", json=None, params=None, headers=None, token=None):
        return self.kirim(method, path, json=json, params=params, headers=headers, token=token)

    # ------------------------------------------------------------- data sukses
    def _data(self, jawaban):
        """Kembalikan seluruh body JSON ({success, data, meta}) bila status < 400."""
        body = jawaban.json()
        if jawaban.status_code >= 400 or body.get("success") is False:
            raise AssertionError(f"{self.basis}{jawaban.text[:400]}")
        return body

    def get(self, path, params=None, token=None, headers=None):
        return self._data(self.kirim("GET", path, params=params, token=token, headers=headers))

    def post(self, path, json=None, token=None, headers=None):
        return self._data(self.kirim("POST", path, json=json, token=token, headers=headers))

    def put(self, path, json=None, token=None, headers=None):
        return self._data(self.kirim("PUT", path, json=json, token=token, headers=headers))

    def delete(self, path, token=None, headers=None):
        return self._data(self.kirim("DELETE", path, token=token, headers=headers))

    # ------------------------------------------------------------------- token
    def token_admin(self):
        return _admin_baru()

    def token_pelanggan(self):
        return {"token": buat_token({"sub": "2", "email": "uji@contoh.test", "nama": "Uji",
                                     "peran": "pelanggan"}, SEKRET),
                "pengguna": {"id": 2, "email": "uji@contoh.test", "peran": "pelanggan"}}

    # ------------------------------------------------------- pembantu alur nyata
    def daftar_pelanggan_baru(self, nama="Pembeli Uji", sandi="rahasia123"):
        email = f"uji_{self.acak()}@contoh.test"
        data = requests.post(URL["pelanggan"] + "/auth/registrasi",
                             json={"email": email, "nama": nama, "kata_sandi": sandi},
                             timeout=self.batas).json()["data"]
        requests.post(URL["pelanggan"] + "/alamat", timeout=self.batas,
                      headers={"Authorization": "Bearer " + data["token"]},
                      json={"label": "Rumah", "penerima": nama, "telepon": "081200000000",
                            "jalan": "Jl. Pengujian 1", "kota": "Bandung",
                            "provinsi": "Jawa Barat", "kode_pos": "40111"})
        return data

    def buat_produk(self, stok=10, harga=50000, nama=None):
        admin = self.token_admin()
        return requests.post(URL["katalog"] + "/produk", timeout=self.batas,
                             headers={"Authorization": "Bearer " + admin["token"]},
                             json={"nama": nama or "Produk Uji " + self.acak(),
                                   "harga": harga, "stok": stok}).json()["data"]

    def stok_produk(self, produk_id):
        return requests.get(URL["katalog"] + f"/produk/{produk_id}", timeout=self.batas).json()["data"]

    def pesan_contoh(self, bayar=True, qty=2, harga=50000, stok=10):
        """Alur penuh: registrasi -> alamat -> produk -> keranjang -> checkout (-> bayar)."""
        pengguna = self.daftar_pelanggan_baru()
        token = pengguna["token"]
        produk = self.buat_produk(stok=stok, harga=harga)
        h = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
        requests.post(URL["order"] + "/keranjang", json={"produk_id": produk["id"], "qty": qty},
                      headers=h, timeout=self.batas)
        hasil = requests.post(URL["order"] + "/checkout", json={}, headers=h,
                              timeout=self.batas).json()["data"]
        pesanan = hasil["pesanan"]
        tagihan = hasil.get("pembayaran")
        if bayar and tagihan and tagihan["status"] == "MENUNGGU":
            admin = self.token_admin()
            requests.post(URL["pembayaran"] + f"/pembayaran/{tagihan['id']}/simulasi",
                          json={"hasil": "berhasil"},
                          headers={"Authorization": "Bearer " + admin["token"]}, timeout=self.batas)
        return {
            "pesanan_id": pesanan["id"],
            "nomor": pesanan["nomor"],
            "token": token,
            "pelanggan_id": pengguna["pengguna"]["id"],
            "produk_id": produk["id"],
            "pembayaran_id": (tagihan or {}).get("id"),
            "total": pesanan["total"],
        }

"""
API Gateway (Peserta 5) - port 8000.

Tanggung jawab:
  * Satu pintu masuk: /api/katalog, /api/pelanggan, /api/order, /api/pembayaran.
  * Verifikasi JWT di tepi (memanggil Pelanggan Service, dengan cache singkat).
  * Menyembunyikan endpoint /internal/* milik layanan.
  * Endpoint agregasi ringkas untuk dashboard toko & admin.
  * Menyajikan dashboard toko (/) dan dashboard admin (/admin).
"""
import os
import sys
import time
import uuid

import requests
from flask import Response, g, request, send_from_directory

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import config, httpc  # noqa: E402
from common.errors import ApiError  # noqa: E402
from common.responses import sukses  # noqa: E402
from common.security import token_dari_header  # noqa: E402
from common.service import create_app  # noqa: E402
import dashboard  # noqa: E402

DISK = os.path.dirname(os.path.abspath(__file__))

app = create_app(__name__, db_name=None)

TUJUAN = {
    "katalog": config.KATALOG_URL,
    "pelanggan": config.PELANGGAN_URL,
    "order": config.ORDER_URL,
    "pembayaran": config.PEMBAYARAN_URL,
}

METODE_DIIZINKAN = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]

_cache_token = {}
CACHE_DETIK = 20.0


# ------------------------------------------------------------------ verifikasi JWT
def _verifikasi_token(token):
    sekarang = time.monotonic()
    tersimpan = _cache_token.get(token)
    if tersimpan and tersimpan[0] > sekarang:
        return tersimpan[1]
    try:
        data = httpc.get(config.PELANGGAN_URL, "/auth/verifikasi", token=token, retry=0)
    except httpc.UpstreamError as exc:
        if exc.status == 401:
            raise ApiError(401, "TOKEN_TIDAK_VALID", exc.pesan)
        raise ApiError(503, "PELANGGAN_TIDAK_TERJANGKAU",
                       "Layanan pelanggan tidak dapat dihubungi untuk verifikasi token")
    _cache_token[token] = (sekarang + CACHE_DETIK, data)
    if len(_cache_token) > 500:  # jaga memori tetap wajar
        for k in list(_cache_token)[:200]:
            _cache_token.pop(k, None)
    return data


def _perlu_login(method, layanan, sub):
    jalur = f"{layanan}/{sub}"
    if jalur.startswith("pelanggan/auth/"):
        return False
    if method == "GET" and (jalur.startswith("katalog/produk") or jalur.startswith("katalog/kategori")):
        return False
    if jalur.startswith("ringkasan/toko"):
        return False
    return True


def _autentikasi(layanan="", sub="", method="GET", peran=None):
    token = token_dari_header()
    if not token:
        raise ApiError(401, "BELUM_LOGIN", "Header Authorization: Bearer <token> wajib diisi")
    data = _verifikasi_token(token)
    if peran and data["pengguna"]["peran"] != peran:
        raise ApiError(403, "TERLARANG", f"Endpoint ini hanya untuk peran '{peran}'")
    g.pengguna = data["pengguna"]
    g.klaim = data["klaim"]
    return data


# ----------------------------------------------------------------------- halaman
@app.get("/")
def halaman_toko():
    return Response(dashboard.halaman_toko(), mimetype="text/html; charset=utf-8")


@app.get("/admin")
def halaman_admin():
    return Response(dashboard.halaman_admin(), mimetype="text/html; charset=utf-8")


@app.get("/assets/<path:berkas>")
def aset(berkas):
    return send_from_directory(os.path.join(DISK, "assets"), berkas)


# ------------------------------------------------------------------- agregasi UI
@app.get("/api/ringkasan/toko")
def ringkasan_toko():
    try:
        produk = httpc.ambil("GET", config.KATALOG_URL, "/produk", params={"batas": 60})
        kategori = httpc.ambil("GET", config.KATALOG_URL, "/kategori")
    except httpc.UpstreamError as exc:
        raise ApiError(503, "KATALOG_TIDAK_TERJANGKAU", str(exc)[:200])
    return sukses({
        "produk": produk["data"],
        "kategori": kategori["data"],
        "jumlah_produk": produk.get("meta", {}).get("jumlah", len(produk["data"])),
    })


@app.get("/api/ringkasan/admin")
def ringkasan_admin():
    _autentikasi(peran="admin")
    hasil = {}
    try:
        hasil["katalog"] = httpc.ambil("GET", config.KATALOG_URL, "/produk",
                                       params={"batas": 100, "aktif": "semua"})
        hasil["pesanan"] = httpc.get(config.ORDER_URL, "/internal/statistik", service_token=True)
        hasil["pembayaran"] = httpc.get(config.PEMBAYARAN_URL, "/internal/statistik", service_token=True)
        hasil["pelanggan"] = httpc.get(config.PELANGGAN_URL, "/internal/statistik", service_token=True)
        hasil["laporan"] = httpc.ambil("GET", config.PEMBAYARAN_URL, "/laporan/ringkasan",
                                       token=token_dari_header())
    except httpc.UpstreamError as exc:
        raise ApiError(503, "LAYANAN_TIDAK_TERJANGKAU", f"{exc.layanan}: {exc.pesan}")
    stok_kritis = [p for p in hasil["katalog"]["data"] if p["stok_tersedia"] <= 5]
    return sukses({
        "produk": hasil["katalog"]["data"],
        "stok_kritis": stok_kritis,
        "statistik_pesanan": hasil["pesanan"],
        "statistik_pembayaran": hasil["pembayaran"],
        "statistik_pelanggan": hasil["pelanggan"],
        "laporan": hasil["laporan"]["data"],
    })


# ------------------------------------------------------------------------- proksi
@app.route("/api/<layanan>/<path:sub>", methods=METODE_DIIZINKAN)
def proksi(layanan, sub):
    if layanan not in TUJUAN:
        raise ApiError(404, "LAYANAN_TIDAK_DIKENAL", f"layanan '{layanan}' tidak terdaftar")
    if sub.startswith("internal/") or "/internal/" in sub:
        raise ApiError(404, "TIDAK_DITEMUKAN", "Endpoint internal tidak diekspos oleh gateway")
    if request.method == "OPTIONS":
        return Response(status=204, headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Authorization,Content-Type,X-Request-Id",
            "Access-Control-Allow-Methods": ",".join(METODE_DIIZINKAN),
        })
    if _perlu_login(request.method, layanan, sub):
        _autentikasi(layanan, sub, request.method)

    url = TUJUAN[layanan].rstrip("/") + "/" + sub
    headers = {"Accept": "application/json", "X-Request-Id": getattr(g, "request_id", uuid.uuid4().hex[:12])}
    if request.headers.get("Authorization"):
        headers["Authorization"] = request.headers["Authorization"]
    if request.headers.get("Content-Type"):
        headers["Content-Type"] = request.headers["Content-Type"]

    mulai = time.perf_counter()
    try:
        balik = requests.request(
            request.method, url,
            params=request.args.to_dict(flat=False),
            data=request.get_data() if request.method in ("POST", "PUT", "PATCH", "DELETE") else None,
            headers=headers, timeout=config.HTTP_TIMEOUT * 2,
        )
    except requests.RequestException as exc:
        app.logger.error("proksi gagal %s %s: %s", request.method, url, exc)
        raise ApiError(502, "LAYANAN_GAGAL", f"{layanan}-service tidak dapat dihubungi")
    durasi = int((time.perf_counter() - mulai) * 1000)
    app.logger.info("proksi %s %s -> %s (%s ms)", request.method, sub, balik.status_code, durasi)

    resp = Response(balik.content, status=balik.status_code,
                    content_type=balik.headers.get("Content-Type", "application/json"))
    resp.headers["X-Layanan-Tujuan"] = layanan
    resp.headers["X-Waktu-Proksi-Ms"] = str(durasi)
    resp.headers["X-Request-Id"] = getattr(g, "request_id", "-")
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


@app.get("/api/status")
def status_layanan():
    hasil = {}
    for nama, url in TUJUAN.items():
        try:
            r = requests.get(url.rstrip("/") + "/health", timeout=2)
            hasil[nama] = {"status": "ok" if r.status_code == 200 else "terganggu", "url": url}
        except requests.RequestException:
            hasil[nama] = {"status": "mati", "url": url}
    semua = all(v["status"] == "ok" for v in hasil.values())
    return sukses({"layanan": hasil, "sehat": semua}, status=200 if semua else 503)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.logger.info("API Gateway siap di http://0.0.0.0:%s", port)
    app.run(host="0.0.0.0", port=port, threaded=True)

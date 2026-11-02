"""Konfigurasi terpusat, dibaca dari environment variable."""
import os

AKAR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def env(nama, bawaan=None):
    nilai = os.environ.get(nama)
    if nilai is None or nilai.strip() == "":
        return bawaan
    return nilai


KATALOG_URL = env("KATALOG_URL", "http://127.0.0.1:8001")
PELANGGAN_URL = env("PELANGGAN_URL", "http://127.0.0.1:8002")
ORDER_URL = env("ORDER_URL", "http://127.0.0.1:8003")
PEMBAYARAN_URL = env("PEMBAYARAN_URL", "http://127.0.0.1:8004")
GATEWAY_URL = env("GATEWAY_URL", "http://127.0.0.1:8000")

JWT_SECRET = env("JWT_SECRET", "dev-secret-jangan-dipakai-di-produksi")
JWT_TTL = int(env("JWT_TTL_SECONDS", "3600"))
SERVICE_TOKEN = env("SERVICE_TOKEN", "token-antar-layanan-dev")

DATA_DIR = env("DATA_DIR", os.path.join(AKAR, "data"))

RESERVASI_TTL = int(env("RESERVASI_TTL_DETIK", "900"))
PEMBAYARAN_TTL = int(env("PEMBAYARAN_TTL_DETIK", "1800"))

HTTP_TIMEOUT = float(env("HTTP_TIMEOUT", "8"))
HTTP_RETRY = int(env("HTTP_RETRY", "2"))

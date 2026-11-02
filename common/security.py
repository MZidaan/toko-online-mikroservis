"""Hash kata sandi (PBKDF2-SHA256) dan decorator otorisasi."""
import base64
import functools
import hashlib
import hmac
import os

from flask import g, request

from . import config
from .errors import ApiError
from .jwtutil import TokenTidakValid, baca_token

_ITERASI = 120_000


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def hash_sandi(sandi: str) -> str:
    if not isinstance(sandi, str) or len(sandi) < 8:
        raise ApiError(422, "VALIDASI_GAGAL", "Kata sandi minimal 8 karakter")
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", sandi.encode("utf-8"), salt, _ITERASI)
    return f"pbkdf2_sha256${_ITERASI}${_b64(salt)}${_b64(dk)}"


def cek_sandi(sandi: str, tersimpan: str) -> bool:
    try:
        algo, iterasi, salt_b64, hash_b64 = tersimpan.split("$")
        if algo != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64)
        harapan = base64.b64decode(hash_b64)
        hitung = hashlib.pbkdf2_hmac("sha256", (sandi or "").encode("utf-8"), salt, int(iterasi))
        return hmac.compare_digest(hitung, harapan)
    except Exception:  # noqa: BLE001
        return False


def token_dari_header():
    raw = request.headers.get("Authorization", "")
    if raw.lower().startswith("bearer "):
        return raw[7:].strip()
    return None


def pengguna_dari_request():
    token = token_dari_header()
    if not token:
        raise ApiError(401, "BELUM_LOGIN", "Header Authorization: Bearer <token> wajib diisi")
    try:
        klaim = baca_token(token)
    except TokenTidakValid as exc:
        raise ApiError(401, "TOKEN_TIDAK_VALID", str(exc)) from exc
    return klaim


def butuh_login(peran=None):
    def dekorator(fn):
        @functools.wraps(fn)
        def bungkus(*args, **kwargs):
            klaim = pengguna_dari_request()
            if peran and klaim.get("peran") != peran:
                raise ApiError(403, "TERLARANG", f"Endpoint ini hanya untuk peran '{peran}'")
            g.pengguna = klaim
            return fn(*args, **kwargs)

        return bungkus

    return dekorator


def butuh_layanan():
    def dekorator(fn):
        @functools.wraps(fn)
        def bungkus(*args, **kwargs):
            token = request.headers.get("X-Service-Token", "")
            if not hmac.compare_digest(token, config.SERVICE_TOKEN):
                raise ApiError(401, "LAYANAN_TIDAK_DIKENAL", "X-Service-Token tidak valid")
            return fn(*args, **kwargs)

        return bungkus

    return dekorator

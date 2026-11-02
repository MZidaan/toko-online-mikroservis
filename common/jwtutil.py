"""JWT HS256 tanpa dependensi eksternal (hmac + hashlib + base64)."""
import base64
import hashlib
import hmac
import json
import time

from . import config


class TokenTidakValid(Exception):
    """Token rusak, kedaluwarsa, atau tanda tangan tidak cocok."""


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _json(d: dict) -> bytes:
    return json.dumps(d, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _tanda(pesan: bytes, secret: str) -> bytes:
    return hmac.new(secret.encode("utf-8"), pesan, hashlib.sha256).digest()


def buat_token(klaim: dict, secret=None, ttl=None) -> str:
    secret = secret or config.JWT_SECRET
    ttl = config.JWT_TTL if ttl is None else ttl
    sekarang = int(time.time())
    payload = dict(klaim)
    payload.setdefault("iat", sekarang)
    payload.setdefault("exp", sekarang + ttl)
    payload.setdefault("typ", "JWT")
    header = {"alg": "HS256", "typ": "JWT"}
    bagian = _b64e(_json(header)) + "." + _b64e(_json(payload))
    return bagian + "." + _b64e(_tanda(bagian.encode("ascii"), secret))


def baca_token(token: str, secret=None, lewati_kedaluwarsa=False) -> dict:
    secret = secret or config.JWT_SECRET
    if not token or token.count(".") != 2:
        raise TokenTidakValid("format token tidak valid")
    bagian, ttd = token.rsplit(".", 1)
    if not hmac.compare_digest(_b64e(_tanda(bagian.encode("ascii"), secret)), ttd):
        raise TokenTidakValid("tanda tangan token tidak cocok")
    try:
        payload = json.loads(_b64d(bagian.split(".")[1]))
    except Exception as exc:  # noqa: BLE001
        raise TokenTidakValid("isi token tidak dapat dibaca") from exc
    if payload.get("typ") not in (None, "JWT") or payload.get("alg") == "none":
        raise TokenTidakValid("tipe token tidak didukung")
    if not lewati_kedaluwarsa:
        exp = int(payload.get("exp", 0))
        if exp and exp < int(time.time()):
            raise TokenTidakValid("token sudah kedaluwarsa")
    return payload

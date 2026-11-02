"""Amplop respons JSON seragam: {success, data|error, meta, request_id}."""
from datetime import datetime, timezone

from flask import g, jsonify
from werkzeug.exceptions import HTTPException

from .errors import ApiError


def waktu_iso(dt=None):
    dt = dt or datetime.now(timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _rid():
    return getattr(g, "request_id", None)


def sukses(data=None, meta=None, status=200):
    body = {"success": True, "data": data}
    if meta is not None:
        body["meta"] = meta
    if _rid():
        body["request_id"] = _rid()
    return jsonify(body), status


def daftar(items, total=None, halaman=None, batas=None):
    meta = {"jumlah": len(items) if total is None else total}
    if halaman is not None:
        meta["halaman"] = halaman
    if batas is not None:
        meta["batas"] = batas
    return sukses(items, meta=meta)


def gagal(kode, pesan, status=400, detail=None):
    body = {"success": False, "error": {"kode": kode, "pesan": pesan}}
    if detail is not None:
        body["error"]["detail"] = detail
    if _rid():
        body["request_id"] = _rid()
    return jsonify(body), status


def daftarkan_handler(app):
    @app.errorhandler(ApiError)
    def _api_error(e):
        return gagal(e.kode, e.pesan, e.status, e.detail)

    @app.errorhandler(404)
    def _404(e):
        return gagal("TIDAK_DITEMUKAN", "Endpoint tidak ditemukan", 404)

    @app.errorhandler(405)
    def _405(e):
        return gagal("METODE_SALAH", "Metode HTTP tidak diizinkan", 405)

    @app.errorhandler(HTTPException)
    def _http(e):
        return gagal(e.name.upper().replace(" ", "_"), e.description, e.code or 500)

    @app.errorhandler(Exception)
    def _500(e):
        app.logger.exception("kesalahan tak tertangani: %s", e)
        return gagal("KESALAHAN_INTERNAL", "Terjadi kesalahan pada layanan", 500)

"""Klien HTTP antar layanan: timeout, retry, service token, error terstruktur."""
import time

import requests

from . import config


class UpstreamError(Exception):
    """Layanan tujuan menolak atau tidak dapat dihubungi."""

    def __init__(self, layanan, status, kode, pesan, detail=None):
        super().__init__(f"[{layanan}] {status} {kode}: {pesan}")
        self.layanan = layanan
        self.status = status
        self.kode = kode
        self.pesan = pesan
        self.detail = detail


def _url(layanan, path):
    return layanan.rstrip("/") + "/" + path.lstrip("/")


def panggil_penuh(method, layanan, path, json=None, params=None, headers=None, timeout=None,
                  retry=None, service_token=False, token=None):
    """Kembalikan seluruh body respons (termasuk `data` dan `meta`)."""
    timeout = config.HTTP_TIMEOUT if timeout is None else timeout
    retry = config.HTTP_RETRY if retry is None else retry
    h = {"Accept": "application/json"}
    if json is not None:
        h["Content-Type"] = "application/json"
    if service_token:
        h["X-Service-Token"] = config.SERVICE_TOKEN
    if token:
        h["Authorization"] = f"Bearer {token}"
    if headers:
        h.update(headers)

    upaya = 0
    terakhir = None
    while upaya <= retry:
        upaya += 1
        try:
            resp = requests.request(method, _url(layanan, path), json=json, params=params,
                                    headers=h, timeout=timeout)
        except requests.RequestException as exc:
            terakhir = UpstreamError(layanan, 0, "KONEKSI_GAGAL", f"tidak dapat menghubungi layanan: {exc}")
            if upaya <= retry:
                time.sleep(0.25 * upaya)
                continue
            raise terakhir from exc
        if resp.status_code >= 500 and upaya <= retry:
            time.sleep(0.25 * upaya)
            continue
        try:
            body = resp.json()
        except ValueError:
            body = {"raw": resp.text[:500]}
        if resp.status_code >= 400:
            err = (body or {}).get("error") or {}
            raise UpstreamError(layanan, resp.status_code, err.get("kode", "KESALAHAN"),
                                err.get("pesan", "permintaan ditolak"), err.get("detail"))
        return body
    raise terakhir  # pragma: no cover


def panggil(method, layanan, path, **kw):
    """Seperti panggil_penuh, tetapi hanya mengembalikan nilai `data`."""
    body = panggil_penuh(method, layanan, path, **kw)
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body


def ambil(method, layanan, path, **kw):
    """Alias eksplisit untuk panggil_penuh (butuh meta/paginasi)."""
    return panggil_penuh(method, layanan, path, **kw)


def get(layanan, path, **kw):
    return panggil("GET", layanan, path, **kw)


def post(layanan, path, json=None, **kw):
    return panggil("POST", layanan, path, json=json, **kw)


def put(layanan, path, json=None, **kw):
    return panggil("PUT", layanan, path, json=json, **kw)


def delete(layanan, path, **kw):
    return panggil("DELETE", layanan, path, **kw)

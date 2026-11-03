"""
Pelanggan Service (Peserta 2) - port 8002.

Tanggung jawab:
  * Registrasi & login (kata sandi di-hash PBKDF2-SHA256, tidak pernah disimpan polos).
  * Penerbitan JWT HS256 berisi klaim sub/email/nama/peran.
  * Endpoint verifikasi token: dipakai API Gateway dan Order Service.
  * Profil pelanggan dan buku alamat (satu alamat utama).
  * Endpoint internal untuk layanan lain (profil ringkas + alamat utama).
"""
import os
import sys
import time

from flask import g, request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import config, db  # noqa: E402
from common.errors import ApiError, bentrok, terlarang, tidak_ditemukan, tidak_valid  # noqa: E402
from common.jwtutil import TokenTidakValid, baca_token, buat_token  # noqa: E402
from common.responses import daftar, sukses, waktu_iso  # noqa: E402
from common.security import (  # noqa: E402
    butuh_layanan, butuh_login, cek_sandi, hash_sandi, token_dari_header,
)
from common.service import create_app  # noqa: E402

DISK = os.path.dirname(os.path.abspath(__file__))
SKEMA = open(os.path.join(DISK, "schema.sql"), encoding="utf-8").read()

app = create_app(__name__, db_name="pelanggan", skema=SKEMA)

RE_EMAIL = r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$"


# --------------------------------------------------------------------------- util
def _email(nilai):
    import re

    email = (nilai or "").strip().lower()
    if not re.match(RE_EMAIL, email):
        raise tidak_valid("format email tidak valid")
    return email


def _teks(body, kunci, wajib=True, bawaan=None, maks=200):
    nilai = body.get(kunci, bawaan)
    if nilai is None or (isinstance(nilai, str) and not nilai.strip()):
        if wajib:
            raise tidak_valid(f"{kunci} wajib diisi")
        return bawaan
    nilai = str(nilai).strip()
    if len(nilai) > maks:
        raise tidak_valid(f"{kunci} maksimal {maks} karakter")
    return nilai


def publik(row):
    """Bentuk aman data pelanggan (tanpa hash kata sandi)."""
    if not row:
        return None
    return {
        "id": row["id"],
        "email": row["email"],
        "nama": row["nama"],
        "peran": row["peran"],
        "telepon": row["telepon"],
        "aktif": bool(row["aktif"]),
        "dibuat_at": row["dibuat_at"],
    }


def _klaim(row):
    return {
        "sub": str(row["id"]),
        "email": row["email"],
        "nama": row["nama"],
        "peran": row["peran"],
        "iss": "pelanggan-service",
    }


def _token(row):
    sekarang = int(time.time())
    klaim = _klaim(row)
    klaim["iat"] = sekarang
    klaim["exp"] = sekarang + config.JWT_TTL
    return buat_token(klaim, ttl=config.JWT_TTL)


def _alamat_pelanggan(pid):
    return db.q("SELECT * FROM alamat WHERE pelanggan_id = ? ORDER BY utama DESC, id", (pid,))


def _alamat_utama(pid):
    rows = _alamat_pelanggan(pid)
    return next((a for a in rows if a["utama"]), rows[0] if rows else None)


def _pastikan_pemilik(alamat_id, pengguna):
    row = db.q1("SELECT * FROM alamat WHERE id = ?", (alamat_id,))
    if not row:
        raise tidak_ditemukan("Alamat")
    if row["pelanggan_id"] != int(pengguna["sub"]) and pengguna.get("peran") != "admin":
        raise terlarang("Alamat ini milik pelanggan lain")
    return row


def _norm_alamat(body, wajib_semua=True):
    data = {
        "label": _teks(body, "label", wajib_semua, "Rumah", 40),
        "penerima": _teks(body, "penerima", wajib_semua, None, 120),
        "telepon": _teks(body, "telepon", wajib_semua, None, 30),
        "jalan": _teks(body, "jalan", wajib_semua, None, 300),
        "kelurahan": _teks(body, "kelurahan", False, None, 120),
        "kecamatan": _teks(body, "kecamatan", False, None, 120),
        "kota": _teks(body, "kota", wajib_semua, None, 120),
        "provinsi": _teks(body, "provinsi", wajib_semua, None, 120),
        "kode_pos": _teks(body, "kode_pos", wajib_semua, None, 10),
    }
    if data["kode_pos"] and not data["kode_pos"].isdigit():
        raise tidak_valid("kode_pos harus angka")
    return data


# ---------------------------------------------------------------------- auth API
@app.post("/auth/registrasi")
def registrasi():
    body = request.get_json(silent=True) or {}
    email = _email(body.get("email"))
    nama = _teks(body, "nama", True, None, 120)
    sandi = body.get("kata_sandi") or ""
    if db.q1("SELECT id FROM pelanggan WHERE lower(email) = ?", (email,)):
        raise bentrok("Email sudah terdaftar")
    peran = "pelanggan"  # peran admin hanya lewat endpoint internal
    pid = db.sisip(
        "INSERT INTO pelanggan (email, nama, kata_sandi_hash, peran, telepon) VALUES (?, ?, ?, ?, ?)",
        (email, nama, hash_sandi(sandi), peran, body.get("telepon")),
    )
    row = db.q1("SELECT * FROM pelanggan WHERE id = ?", (pid,))
    app.logger.info("registrasi baru: %s", email)
    return sukses(
        {"pengguna": publik(row), "token": _token(row), "tipe": "Bearer",
         "kedaluwarsa_detik": config.JWT_TTL},
        status=201,
    )


@app.post("/auth/login")
def login():
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    sandi = body.get("kata_sandi") or ""
    if not email or not sandi:
        raise tidak_valid("email dan kata_sandi wajib diisi")
    row = db.q1("SELECT * FROM pelanggan WHERE lower(email) = ?", (email,))
    if not row or not cek_sandi(sandi, row["kata_sandi_hash"]):
        db.eksekusi("INSERT INTO audit_login (pelanggan_id, email, berhasil, alasan) VALUES (?, ?, 0, ?)",
                    (row["id"] if row else None, email, "kredensial salah"))
        raise ApiError(401, "KREDENSIAL_SALAH", "Email atau kata sandi salah")
    if not row["aktif"]:
        raise terlarang("Akun dinonaktifkan")
    db.eksekusi("INSERT INTO audit_login (pelanggan_id, email, berhasil) VALUES (?, ?, 1)",
                (row["id"], email))
    return sukses(
        {"token": _token(row), "tipe": "Bearer", "kedaluwarsa_detik": config.JWT_TTL,
         "pengguna": publik(row)}
    )


def _verifikasi(token, lewati_kedaluwarsa=False):
    try:
        klaim = baca_token(token, lewati_kedaluwarsa=lewati_kedaluwarsa)
    except TokenTidakValid as exc:
        return {"valid": False, "alasan": str(exc)}
    row = db.q1("SELECT * FROM pelanggan WHERE id = ?", (int(klaim.get("sub", 0)),))
    if not row or not row["aktif"]:
        return {"valid": False, "alasan": "pelanggan tidak ditemukan atau tidak aktif"}
    return {
        "valid": True,
        "pengguna": publik(row),
        "klaim": {k: klaim.get(k) for k in ("sub", "email", "peran", "iat", "exp")},
        "sisa_detik": max(int(klaim.get("exp", 0)) - int(time.time()), 0),
    }


@app.get("/auth/verifikasi")
def verifikasi_get():
    """Dipakai API Gateway (setiap request) dan Order Service."""
    token = token_dari_header()
    if not token:
        raise ApiError(401, "BELUM_LOGIN", "Header Authorization: Bearer <token> wajib diisi")
    hasil = _verifikasi(token)
    if not hasil["valid"]:
        raise ApiError(401, "TOKEN_TIDAK_VALID", hasil["alasan"])
    return sukses(hasil)


@app.post("/auth/verifikasi")
def verifikasi_post():
    body = request.get_json(silent=True) or {}
    token = body.get("token") or token_dari_header()
    if not token:
        raise tidak_valid("token wajib diisi")
    return sukses(_verifikasi(token, lewati_kedaluwarsa=bool(body.get("abaikan_kedaluwarsa"))))


# ------------------------------------------------------------------- profil saya
@app.get("/pelanggan/saya")
@butuh_login()
def profil_saya():
    row = db.q1("SELECT * FROM pelanggan WHERE id = ?", (int(g.pengguna["sub"]),))
    if not row:
        raise tidak_ditemukan("Pelanggan")
    data = publik(row)
    data["alamat"] = _alamat_pelanggan(row["id"])
    return sukses(data)


@app.put("/pelanggan/saya")
@butuh_login()
def ubah_profil():
    body = request.get_json(silent=True) or {}
    row = db.q1("SELECT * FROM pelanggan WHERE id = ?", (int(g.pengguna["sub"]),))
    if not row:
        raise tidak_ditemukan("Pelanggan")
    db.eksekusi(
        "UPDATE pelanggan SET nama = ?, telepon = ?, diperbarui_at = ? WHERE id = ?",
        (_teks(body, "nama", False, row["nama"], 120), body.get("telepon", row["telepon"]),
         waktu_iso(), row["id"]),
    )
    return sukses(publik(db.q1("SELECT * FROM pelanggan WHERE id = ?", (row["id"],))))


@app.put("/pelanggan/saya/kata-sandi")
@butuh_login()
def ganti_sandi():
    body = request.get_json(silent=True) or {}
    row = db.q1("SELECT * FROM pelanggan WHERE id = ?", (int(g.pengguna["sub"]),))
    if not row:
        raise tidak_ditemukan("Pelanggan")
    if not cek_sandi(body.get("kata_sandi_lama") or "", row["kata_sandi_hash"]):
        raise ApiError(401, "KREDENSIAL_SALAH", "Kata sandi lama salah")
    db.eksekusi("UPDATE pelanggan SET kata_sandi_hash = ?, diperbarui_at = ? WHERE id = ?",
                (hash_sandi(body.get("kata_sandi_baru") or ""), waktu_iso(), row["id"]))
    return sukses({"id": row["id"], "diperbarui": True})


# ---------------------------------------------------------------- admin: daftar
@app.get("/pelanggan")
@butuh_login("admin")
def daftar_pelanggan():
    halaman = max(int(request.args.get("halaman", 1) or 1), 1)
    batas = min(max(int(request.args.get("batas", 20) or 20), 1), 100)
    filter_peran = request.args.get("peran")
    where, params = "", []
    if filter_peran in ("pelanggan", "admin"):
        where, params = "WHERE peran = ?", [filter_peran]
    total = db.skalar(f"SELECT COUNT(*) FROM pelanggan {where}", params, 0)
    rows = db.q(f"SELECT * FROM pelanggan {where} ORDER BY id DESC LIMIT ? OFFSET ?",
                params + [batas, (halaman - 1) * batas])
    return daftar([publik(r) for r in rows], total=total, halaman=halaman, batas=batas)


@app.get("/pelanggan/<int:pid>")
@butuh_login("admin")
def detail_pelanggan(pid):
    row = db.q1("SELECT * FROM pelanggan WHERE id = ?", (pid,))
    if not row:
        raise tidak_ditemukan("Pelanggan")
    data = publik(row)
    data["alamat"] = _alamat_pelanggan(pid)
    return sukses(data)


# ----------------------------------------------------------------------- alamat
@app.get("/alamat")
@butuh_login()
def daftar_alamat():
    return daftar(_alamat_pelanggan(int(g.pengguna["sub"])))


@app.post("/alamat")
@butuh_login()
def tambah_alamat():
    body = request.get_json(silent=True) or {}
    data = _norm_alamat(body)
    pid = int(g.pengguna["sub"])
    jumlah = db.skalar("SELECT COUNT(*) FROM alamat WHERE pelanggan_id = ?", (pid,), 0)
    utama = 1 if (jumlah == 0 or body.get("utama")) else 0
    with db.transaksi():
        if utama:
            db.eksekusi("UPDATE alamat SET utama = 0 WHERE pelanggan_id = ?", (pid,))
        aid = db.sisip(
            """INSERT INTO alamat (pelanggan_id, label, penerima, telepon, jalan, kelurahan,
               kecamatan, kota, provinsi, kode_pos, utama)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (pid, data["label"], data["penerima"], data["telepon"], data["jalan"],
             data["kelurahan"], data["kecamatan"], data["kota"], data["provinsi"],
             data["kode_pos"], utama),
        )
    return sukses(db.q1("SELECT * FROM alamat WHERE id = ?", (aid,)), status=201)


@app.put("/alamat/<int:aid>")
@butuh_login()
def ubah_alamat(aid):
    lama = _pastikan_pemilik(aid, g.pengguna)
    body = request.get_json(silent=True) or {}
    baru = {k: (body.get(k, lama[k]) if body.get(k) is not None else lama[k])
            for k in ("label", "penerima", "telepon", "jalan", "kelurahan", "kecamatan",
                      "kota", "provinsi", "kode_pos")}
    db.eksekusi(
        """UPDATE alamat SET label = ?, penerima = ?, telepon = ?, jalan = ?, kelurahan = ?,
           kecamatan = ?, kota = ?, provinsi = ?, kode_pos = ? WHERE id = ?""",
        (baru["label"], baru["penerima"], baru["telepon"], baru["jalan"], baru["kelurahan"],
         baru["kecamatan"], baru["kota"], baru["provinsi"], baru["kode_pos"], aid),
    )
    return sukses(db.q1("SELECT * FROM alamat WHERE id = ?", (aid,)))


@app.delete("/alamat/<int:aid>")
@butuh_login()
def hapus_alamat(aid):
    row = _pastikan_pemilik(aid, g.pengguna)
    db.eksekusi("DELETE FROM alamat WHERE id = ?", (aid,))
    if row["utama"]:
        sisa = db.q1("SELECT id FROM alamat WHERE pelanggan_id = ? ORDER BY id LIMIT 1",
                     (row["pelanggan_id"],))
        if sisa:
            db.eksekusi("UPDATE alamat SET utama = 1 WHERE id = ?", (sisa["id"],))
    return sukses({"id": aid, "dihapus": True})


@app.post("/alamat/<int:aid>/utama")
@butuh_login()
def jadikan_utama(aid):
    row = _pastikan_pemilik(aid, g.pengguna)
    with db.transaksi():
        db.eksekusi("UPDATE alamat SET utama = 0 WHERE pelanggan_id = ?", (row["pelanggan_id"],))
        db.eksekusi("UPDATE alamat SET utama = 1 WHERE id = ?", (aid,))
    return sukses(db.q1("SELECT * FROM alamat WHERE id = ?", (aid,)))


# --------------------------------------------------------------------- internal
@app.get("/internal/pelanggan/<int:pid>")
@butuh_layanan()
def internal_pelanggan(pid):
    row = db.q1("SELECT * FROM pelanggan WHERE id = ?", (pid,))
    if not row:
        raise tidak_ditemukan("Pelanggan")
    data = publik(row)
    data["alamat_utama"] = _alamat_utama(pid)
    data["jumlah_alamat"] = db.skalar("SELECT COUNT(*) FROM alamat WHERE pelanggan_id = ?", (pid,), 0)
    return sukses(data)


@app.post("/internal/pelanggan/buat-admin")
@butuh_layanan()
def buat_admin():
    """Bootstrap akun admin (dipakai skrip seed)."""
    body = request.get_json(silent=True) or {}
    email = _email(body.get("email"))
    ada = db.q1("SELECT * FROM pelanggan WHERE lower(email) = ?", (email,))
    if ada:
        if ada["peran"] != "admin":
            db.eksekusi("UPDATE pelanggan SET peran = 'admin', diperbarui_at = ? WHERE id = ?",
                        (waktu_iso(), ada["id"]))
            ada = db.q1("SELECT * FROM pelanggan WHERE id = ?", (ada["id"],))
        return sukses({"pengguna": publik(ada), "token": _token(ada), "dibuat": False})
    pid = db.sisip(
        "INSERT INTO pelanggan (email, nama, kata_sandi_hash, peran) VALUES (?, ?, ?, 'admin')",
        (email, (body.get("nama") or "Administrator Toko"), hash_sandi(body.get("kata_sandi") or "")),
    )
    row = db.q1("SELECT * FROM pelanggan WHERE id = ?", (pid,))
    return sukses({"pengguna": publik(row), "token": _token(row), "dibuat": True}, status=201)


@app.get("/internal/statistik")
@butuh_layanan()
def statistik():
    return sukses({
        "pelanggan": db.skalar("SELECT COUNT(*) FROM pelanggan WHERE peran = 'pelanggan'", bawaan=0),
        "admin": db.skalar("SELECT COUNT(*) FROM pelanggan WHERE peran = 'admin'", bawaan=0),
        "alamat": db.skalar("SELECT COUNT(*) FROM alamat", bawaan=0),
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8002"))
    app.logger.info("Pelanggan Service siap di http://0.0.0.0:%s", port)
    app.run(host="0.0.0.0", port=port, threaded=True)

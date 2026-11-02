"""
Katalog Service (Peserta 1) - port 8001.

Tanggung jawab:
  * CRUD kategori dan produk.
  * Manajemen stok: stok fisik + stok_reserved (stok yang sedang ditahan pesanan).
  * Reserve / commit / release stok secara atomik (dipakai Order Service saat checkout).

Model stok:
  tersedia = stok - stok_reserved
  reserve  -> stok_reserved += qty        (stok belum berkurang)
  komit    -> stok -= qty, stok_reserved -= qty
  rilis    -> stok_reserved -= qty        (kompensasi bila checkout gagal)
"""
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

from flask import g, request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import config, db, httpc  # noqa: E402
from common.errors import ApiError, bentrok, tidak_ditemukan, tidak_valid  # noqa: E402
from common.responses import daftar, sukses, waktu_iso  # noqa: E402
from common.security import butuh_layanan, butuh_login  # noqa: E402
from common.service import create_app  # noqa: E402

DISK = os.path.dirname(os.path.abspath(__file__))
SKEMA = open(os.path.join(DISK, "schema.sql"), encoding="utf-8").read()

app = create_app(__name__, db_name="katalog", skema=SKEMA)

AKSES_PUBLIK = {"/health"}


# --------------------------------------------------------------------------- util
def _harga(nilai):
    try:
        harga = int(nilai)
    except (TypeError, ValueError):
        raise tidak_valid("harga harus bilangan bulat (rupiah)")
    if harga < 0:
        raise tidak_valid("harga tidak boleh negatif")
    return harga


def _bulat(nilai, nama, minimal=0):
    try:
        angka = int(nilai)
    except (TypeError, ValueError):
        raise tidak_valid(f"{nama} harus bilangan bulat")
    if angka < minimal:
        raise tidak_valid(f"{nama} minimal {minimal}")
    return angka


def _produk_ringkas(row):
    if not row:
        return None
    data = dict(row)
    data["stok_tersedia"] = max(data["stok"] - data["stok_reserved"], 0)
    data["aktif"] = bool(data["aktif"])
    data["harga_format"] = "Rp{:,}".format(data["harga"]).replace(",", ".")
    return data


def _ambil_produk(pid):
    row = db.q1("SELECT * FROM produk WHERE id = ?", (pid,))
    if not row:
        raise tidak_ditemukan("Produk")
    return row


def _detail_reservasi(rid):
    head = db.q1("SELECT * FROM reservasi WHERE id = ?", (rid,))
    if not head:
        raise tidak_ditemukan("Reservasi")
    head["items"] = db.q(
        "SELECT produk_id, nama_produk, qty, harga FROM reservasi_item WHERE reservasi_id = ? ORDER BY id",
        (rid,),
    )
    return head


# ------------------------------------------------------------------------ health
@app.get("/siap")
def siap():
    return sukses({"layanan": "katalog-service", "produk": db.skalar("SELECT COUNT(*) FROM produk", bawaan=0)})


# ---------------------------------------------------------------------- kategori
@app.get("/kategori")
def daftar_kategori():
    rows = db.q(
        """
        SELECT k.*, (SELECT COUNT(*) FROM produk p WHERE p.kategori_id = k.id AND p.aktif = 1) AS jumlah_produk
        FROM kategori k ORDER BY k.nama
        """
    )
    return daftar(rows)


@app.post("/kategori")
@butuh_login("admin")
def buat_kategori():
    body = request.get_json(silent=True) or {}
    nama = (body.get("nama") or "").strip()
    if not nama:
        raise tidak_valid("nama kategori wajib diisi")
    if db.q1("SELECT id FROM kategori WHERE lower(nama) = lower(?)", (nama,)):
        raise bentrok(f"Kategori '{nama}' sudah ada")
    kid = db.sisip("INSERT INTO kategori (nama, deskripsi) VALUES (?, ?)", (nama, body.get("deskripsi")))
    return sukses(db.q1("SELECT * FROM kategori WHERE id = ?", (kid,)), status=201)


@app.put("/kategori/<int:kid>")
@butuh_login("admin")
def ubah_kategori(kid):
    row = db.q1("SELECT * FROM kategori WHERE id = ?", (kid,))
    if not row:
        raise tidak_ditemukan("Kategori")
    body = request.get_json(silent=True) or {}
    nama = (body.get("nama") or row["nama"]).strip()
    db.eksekusi("UPDATE kategori SET nama = ?, deskripsi = ? WHERE id = ?",
                (nama, body.get("deskripsi", row["deskripsi"]), kid))
    return sukses(db.q1("SELECT * FROM kategori WHERE id = ?", (kid,)))


@app.delete("/kategori/<int:kid>")
@butuh_login("admin")
def hapus_kategori(kid):
    if not db.q1("SELECT id FROM kategori WHERE id = ?", (kid,)):
        raise tidak_ditemukan("Kategori")
    if db.skalar("SELECT COUNT(*) FROM produk WHERE kategori_id = ?", (kid,), 0):
        raise bentrok("Kategori masih memiliki produk, pindahkan produk terlebih dahulu")
    db.eksekusi("DELETE FROM kategori WHERE id = ?", (kid,))
    return sukses({"id": kid, "dihapus": True})


# ------------------------------------------------------------------------ produk
@app.get("/produk")
def daftar_produk():
    arg = request.args
    halaman = max(_bulat(arg.get("halaman", 1), "halaman", 1), 1)
    batas = min(max(_bulat(arg.get("batas", 20), "batas", 1), 1), 100)
    syarat, params = [], []
    if arg.get("kategori"):
        syarat.append("p.kategori_id = ?")
        params.append(_bulat(arg["kategori"], "kategori", 1))
    if arg.get("q"):
        syarat.append("(lower(p.nama) LIKE ? OR lower(p.sku) LIKE ?)")
        pola = f"%{arg['q'].lower()}%"
        params += [pola, pola]
    if arg.get("aktif", "1") not in ("0", "semua", "all"):
        syarat.append("p.aktif = 1")
    if arg.get("hanya_tersedia") in ("1", "true"):
        syarat.append("(p.stok - p.stok_reserved) > 0")
    where = ("WHERE " + " AND ".join(syarat)) if syarat else ""
    total = db.skalar(f"SELECT COUNT(*) FROM produk p {where}", params, 0)
    rows = db.q(
        f"""SELECT p.*, k.nama AS kategori FROM produk p
            LEFT JOIN kategori k ON k.id = p.kategori_id
            {where} ORDER BY p.id DESC LIMIT ? OFFSET ?""",
        params + [batas, (halaman - 1) * batas],
    )
    return daftar([_produk_ringkas(r) for r in rows], total=total, halaman=halaman, batas=batas)


@app.get("/produk/<int:pid>")
def detail_produk(pid):
    row = db.q1(
        """SELECT p.*, k.nama AS kategori FROM produk p
           LEFT JOIN kategori k ON k.id = p.kategori_id WHERE p.id = ?""",
        (pid,),
    )
    if not row:
        raise tidak_ditemukan("Produk")
    return sukses(_produk_ringkas(row))


@app.post("/produk")
@butuh_login("admin")
def buat_produk():
    body = request.get_json(silent=True) or {}
    nama = (body.get("nama") or "").strip()
    if not nama:
        raise tidak_valid("nama produk wajib diisi")
    sku = (body.get("sku") or "").strip().upper() or "SKU-" + uuid.uuid4().hex[:8].upper()
    if db.q1("SELECT id FROM produk WHERE sku = ?", (sku,)):
        raise bentrok(f"SKU '{sku}' sudah dipakai")
    kategori_id = body.get("kategori_id")
    if kategori_id is not None:
        kategori_id = _bulat(kategori_id, "kategori_id", 1)
        if not db.q1("SELECT id FROM kategori WHERE id = ?", (kategori_id,)):
            raise tidak_valid("kategori_id tidak dikenal")
    pid = db.sisip(
        """INSERT INTO produk (sku, nama, deskripsi, kategori_id, harga, stok, aktif)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (sku, nama, body.get("deskripsi"), kategori_id, _harga(body.get("harga", 0)),
         _bulat(body.get("stok", 0), "stok"), 1 if body.get("aktif", True) else 0),
    )
    return sukses(_produk_ringkas(_ambil_produk(pid)), status=201)


@app.put("/produk/<int:pid>")
@butuh_login("admin")
def ubah_produk(pid):
    row = _ambil_produk(pid)
    body = request.get_json(silent=True) or {}
    kategori_id = body.get("kategori_id", row["kategori_id"])
    if kategori_id is not None:
        kategori_id = _bulat(kategori_id, "kategori_id", 1)
        if not db.q1("SELECT id FROM kategori WHERE id = ?", (kategori_id,)):
            raise tidak_valid("kategori_id tidak dikenal")
    db.eksekusi(
        """UPDATE produk SET nama = ?, deskripsi = ?, kategori_id = ?, harga = ?, aktif = ?,
           diperbarui_at = ? WHERE id = ?""",
        (
            (body.get("nama") or row["nama"]).strip(),
            body.get("deskripsi", row["deskripsi"]),
            kategori_id,
            _harga(body.get("harga", row["harga"])),
            1 if body.get("aktif", bool(row["aktif"])) else 0,
            waktu_iso(),
            pid,
        ),
    )
    return sukses(_produk_ringkas(_ambil_produk(pid)))


@app.delete("/produk/<int:pid>")
@butuh_login("admin")
def nonaktifkan_produk(pid):
    _ambil_produk(pid)
    db.eksekusi("UPDATE produk SET aktif = 0, diperbarui_at = ? WHERE id = ?", (waktu_iso(), pid))
    return sukses({"id": pid, "aktif": False})


@app.post("/produk/<int:pid>/stok")
@butuh_login("admin")
def ubah_stok(pid):
    row = _ambil_produk(pid)
    body = request.get_json(silent=True) or {}
    tambah = body.get("tambah")
    if tambah is None:
        tambah = body.get("stok_baru", 0) - row["stok"] if "stok_baru" in body else None
    if tambah is None:
        raise tidak_valid("kirim 'tambah' (bisa negatif) atau 'stok_baru'")
    try:
        tambah = int(tambah)
    except (TypeError, ValueError):
        raise tidak_valid("tambah harus bilangan bulat")
    with db.transaksi():
        baru = row["stok"] + tambah
        if baru < row["stok_reserved"]:
            raise bentrok(
                f"Stok tidak boleh di bawah jumlah yang sedang ditahan ({row['stok_reserved']})",
            )
        db.eksekusi("UPDATE produk SET stok = ?, diperbarui_at = ? WHERE id = ?", (baru, waktu_iso(), pid))
    return sukses(_produk_ringkas(_ambil_produk(pid)))


# ------------------------------------------------------------------- reservasi
@app.post("/internal/reservasi")
@butuh_layanan()
def buat_reservasi():
    body = request.get_json(silent=True) or {}
    order_ref = (body.get("order_ref") or "").strip()
    items = body.get("items") or []
    if not order_ref:
        raise tidak_valid("order_ref wajib diisi")
    if not isinstance(items, list) or not items:
        raise tidak_valid("items wajib berupa daftar minimal satu produk")
    ttl = _bulat(body.get("ttl_detik", config.RESERVASI_TTL), "ttl_detik", 30)

    diminta = []
    for it in items:
        pid = _bulat(it.get("produk_id"), "produk_id", 1)
        qty = _bulat(it.get("qty"), "qty", 1)
        diminta.append((pid, qty))

    rid = "rsv_" + uuid.uuid4().hex[:16]
    kedaluwarsa = (datetime.now(timezone.utc) + timedelta(seconds=ttl)).isoformat(timespec="seconds")

    with db.transaksi():
        db.eksekusi(
            "INSERT INTO reservasi (id, order_ref, status, total, kedaluwarsa_at) VALUES (?, ?, 'AKTIF', 0, ?)",
            (rid, order_ref, kedaluwarsa),
        )
        total = 0
        for pid, qty in diminta:
            row = db.q1("SELECT * FROM produk WHERE id = ?", (pid,))
            if not row:
                raise tidak_ditemukan(f"Produk {pid}")
            if not row["aktif"]:
                raise bentrok(f"Produk '{row['nama']}' sedang tidak dijual")
            tersedia = row["stok"] - row["stok_reserved"]
            if tersedia < qty:
                raise ApiError(
                    409, "STOK_TIDAK_CUKUP",
                    f"Stok '{row['nama']}' tidak cukup (diminta {qty}, tersedia {max(tersedia, 0)})",
                    {"produk_id": pid, "diminta": qty, "tersedia": max(tersedia, 0)},
                )
            db.eksekusi("UPDATE produk SET stok_reserved = stok_reserved + ? WHERE id = ?", (qty, pid))
            db.eksekusi(
                """INSERT INTO reservasi_item (reservasi_id, produk_id, nama_produk, qty, harga)
                   VALUES (?, ?, ?, ?, ?)""",
                (rid, pid, row["nama"], qty, row["harga"]),
            )
            total += qty * row["harga"]
        db.eksekusi("UPDATE reservasi SET total = ? WHERE id = ?", (total, rid))
    return sukses(_detail_reservasi(rid), status=201)


@app.get("/internal/reservasi/<rid>")
@butuh_layanan()
def detail_reservasi(rid):
    return sukses(_detail_reservasi(rid))


def _tutup_reservasi(rid, target, aksi):
    head = db.q1("SELECT * FROM reservasi WHERE id = ?", (rid,))
    if not head:
        raise tidak_ditemukan("Reservasi")
    if head["status"] == target:  # idempoten
        return _detail_reservasi(rid)
    if head["status"] != "AKTIF":
        raise bentrok(f"Reservasi berstatus {head['status']}, tidak dapat di-{aksi}")
    items = db.q("SELECT produk_id, qty FROM reservasi_item WHERE reservasi_id = ?", (rid,))
    with db.transaksi():
        for it in items:
            if target == "DIKOMIT":
                db.eksekusi(
                    """UPDATE produk SET stok = stok - ?, stok_reserved = stok_reserved - ?,
                       diperbarui_at = ? WHERE id = ?""",
                    (it["qty"], it["qty"], waktu_iso(), it["produk_id"]),
                )
            else:
                db.eksekusi(
                    """UPDATE produk SET stok_reserved = stok_reserved - ?, diperbarui_at = ?
                       WHERE id = ?""",
                    (it["qty"], waktu_iso(), it["produk_id"]),
                )
        db.eksekusi("UPDATE reservasi SET status = ?, ditutup_at = ? WHERE id = ?",
                    (target, waktu_iso(), rid))
    return _detail_reservasi(rid)


@app.post("/internal/reservasi/<rid>/komit")
@butuh_layanan()
def komit_reservasi(rid):
    return sukses(_tutup_reservasi(rid, "DIKOMIT", "komit"))


@app.post("/internal/reservasi/<rid>/rilis")
@butuh_layanan()
def rilis_reservasi(rid):
    return sukses(_tutup_reservasi(rid, "DIRILIS", "rilis"))


@app.post("/internal/reservasi/bersihkan")
@butuh_layanan()
def bersihkan_reservasi():
    """Rilis reservasi AKTIF yang sudah melewati kedaluwarsa (dipanggil penjadwal)."""
    batas = request.get_json(silent=True) or {}
    menit = _bulat(batas.get("lebih_dari_menit", 0), "lebih_dari_menit", 0)
    sekarang = datetime.now(timezone.utc)
    ambang = (sekarang - timedelta(minutes=menit)).isoformat(timespec="seconds")
    rows = db.q(
        "SELECT id FROM reservasi WHERE status = 'AKTIF' AND kedaluwarsa_at <= ? LIMIT 200",
        (ambang,),
    )
    dilepas = []
    for row in rows:
        try:
            _tutup_reservasi(row["id"], "DIRILIS", "rilis")
            dilepas.append(row["id"])
        except ApiError as exc:  # lewati reservasi yang sudah berubah status
            app.logger.warning("lewatkan reservasi %s: %s", row["id"], exc.pesan)
    return sukses({"dilepas": dilepas, "jumlah": len(dilepas)})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8001"))
    app.logger.info("Katalog Service siap di http://0.0.0.0:%s", port)
    app.run(host="0.0.0.0", port=port, threaded=True)

"""
Order Service (Peserta 3) - port 8003.

Tanggung jawab:
  * Keranjang belanja per pelanggan (harga snapshot dari Katalog Service).
  * Checkout dengan saga + kompensasi:
        validasi pelanggan -> reserve stok -> simpan pesanan -> inisiasi pembayaran
    Bila salah satu langkah gagal, langkah sebelumnya dibatalkan berurutan
    (rilis stok, pesanan ditandai DIBATALKAN) dan jejaknya disimpan di saga_log.
  * Riwayat pesanan + transisi status + pembatalan manual.
  * Webhook internal dari Pembayaran Service untuk menyinkronkan status pesanan.
"""
import json
import os
import sys
import uuid
from datetime import datetime, timezone

from flask import g, request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import config, db, httpc  # noqa: E402
from common.errors import ApiError, bentrok, terlarang, tidak_ditemukan, tidak_valid  # noqa: E402
from common.responses import daftar, sukses, waktu_iso  # noqa: E402
from common.security import butuh_layanan, butuh_login  # noqa: E402
from common.service import create_app  # noqa: E402
from saga import KegagalanSaga, Saga  # noqa: E402

DISK = os.path.dirname(os.path.abspath(__file__))
SKEMA = open(os.path.join(DISK, "schema.sql"), encoding="utf-8").read()

app = create_app(__name__, db_name="order", skema=SKEMA)

INTEGRASI_PEMBAYARAN = os.environ.get("INTEGRASI_PEMBAYARAN", "1") != "0"
SIMULASI_AKTIF = os.environ.get("SIMULASI_AKTIF", "1") != "0"

ONGKIR = {"reguler": 15000, "kilat": 25000, "instan": 40000}
GRATIS_ONGKIR_MIN = 300000

ALUR_STATUS = {
    "MENUNGGU_PEMBAYARAN": {"DIBAYAR", "DIBATALKAN"},
    "DIBAYAR": {"DIKEMAS", "DIBATALKAN"},
    "DIKEMAS": {"DIKIRIM"},
    "DIKIRIM": {"SELESAI"},
    "SELESAI": set(),
    "DIBATALKAN": set(),
}


# --------------------------------------------------------------------------- util
def catat(pesanan_id, langkah, jenis, status, pesan=None):
    db.eksekusi(
        "INSERT INTO saga_log (pesanan_id, langkah, jenis, status, pesan) VALUES (?, ?, ?, ?, ?)",
        (pesanan_id, langkah, jenis, status, pesan),
    )
    app.logger.info("[saga] %s %s %s -> %s %s", pesanan_id, jenis, langkah, status, pesan or "")


def _pid():
    return int(g.pengguna["sub"])


def _nomor():
    return "ORD-" + datetime.now(timezone.utc).strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:6].upper()


def _isi_keranjang(pid):
    rows = db.q(
        "SELECT * FROM keranjang WHERE pelanggan_id = ? ORDER BY ditambahkan_at, id", (pid,)
    )
    for r in rows:
        r["subtotal"] = r["harga_satuan"] * r["qty"]
    total = sum(r["subtotal"] for r in rows)
    return rows, total


def _pesanan_lengkap(oid, pelanggan_id=None, peran=None):
    head = db.q1("SELECT * FROM pesanan WHERE id = ?", (oid,))
    if not head:
        raise tidak_ditemukan("Pesanan")
    if peran != "admin" and pelanggan_id is not None and head["pelanggan_id"] != pelanggan_id:
        raise terlarang("Pesanan ini milik pelanggan lain")
    head["items"] = db.q("SELECT produk_id, nama_produk, harga, qty, subtotal FROM pesanan_item WHERE pesanan_id = ? ORDER BY id", (oid,))
    head["alamat"] = json.loads(head["alamat_json"]) if head["alamat_json"] else None
    head.pop("alamat_json", None)
    head["jejak_saga"] = db.q(
        "SELECT langkah, jenis, status, pesan, waktu FROM saga_log WHERE pesanan_id = ? ORDER BY id", (oid,)
    )
    return head


def _ambil_pelanggan(pid, token=None):
    return httpc.get(config.PELANGGAN_URL, f"/internal/pelanggan/{pid}", service_token=True)


def _produk(pid_produk):
    return httpc.get(config.KATALOG_URL, f"/produk/{pid_produk}")


# --------------------------------------------------------------------- keranjang
@app.get("/keranjang")
@butuh_login()
def lihat_keranjang():
    rows, total = _isi_keranjang(_pid())
    return sukses({
        "items": rows,
        "jumlah_item": len(rows),
        "total": total,
        "ongkir": ONGKIR,
        "gratis_ongkir_di_atas": GRATIS_ONGKIR_MIN,
    })


@app.post("/keranjang")
@butuh_login()
def tambah_keranjang():
    body = request.get_json(silent=True) or {}
    try:
        produk_id = int(body.get("produk_id"))
        qty = int(body.get("qty", 1))
    except (TypeError, ValueError):
        raise tidak_valid("produk_id dan qty harus bilangan bulat")
    if qty < 1:
        raise tidak_valid("qty minimal 1")
    produk = _produk(produk_id)
    if not produk["aktif"]:
        raise bentrok("Produk tidak sedang dijual")
    if produk["stok_tersedia"] < qty:
        raise bentrok(f"Stok tersedia hanya {produk['stok_tersedia']}")
    pid = _pid()
    lama = db.q1("SELECT * FROM keranjang WHERE pelanggan_id = ? AND produk_id = ?", (pid, produk_id))
    if lama:
        qty_baru = lama["qty"] + qty
        if qty_baru > produk["stok_tersedia"]:
            raise bentrok(f"Total di keranjang melebihi stok tersedia ({produk['stok_tersedia']})")
        db.eksekusi("UPDATE keranjang SET qty = ?, harga_satuan = ?, nama_produk = ? WHERE id = ?",
                    (qty_baru, produk["harga"], produk["nama"], lama["id"]))
    else:
        db.sisip(
            """INSERT INTO keranjang (pelanggan_id, produk_id, nama_produk, harga_satuan, qty)
               VALUES (?, ?, ?, ?, ?)""",
            (pid, produk_id, produk["nama"], produk["harga"], qty),
        )
    return lihat_keranjang()


@app.put("/keranjang/<int:produk_id>")
@butuh_login()
def ubah_keranjang(produk_id):
    body = request.get_json(silent=True) or {}
    try:
        qty = int(body.get("qty"))
    except (TypeError, ValueError):
        raise tidak_valid("qty harus bilangan bulat")
    pid = _pid()
    if not db.q1("SELECT id FROM keranjang WHERE pelanggan_id = ? AND produk_id = ?", (pid, produk_id)):
        raise tidak_ditemukan("Item keranjang")
    if qty <= 0:
        db.eksekusi("DELETE FROM keranjang WHERE pelanggan_id = ? AND produk_id = ?", (pid, produk_id))
        return lihat_keranjang()
    produk = _produk(produk_id)
    if qty > produk["stok_tersedia"]:
        raise bentrok(f"Stok tersedia hanya {produk['stok_tersedia']}")
    db.eksekusi("UPDATE keranjang SET qty = ?, harga_satuan = ? WHERE pelanggan_id = ? AND produk_id = ?",
                (qty, produk["harga"], pid, produk_id))
    return lihat_keranjang()


@app.delete("/keranjang/<int:produk_id>")
@butuh_login()
def hapus_item(produk_id):
    db.eksekusi("DELETE FROM keranjang WHERE pelanggan_id = ? AND produk_id = ?", (_pid(), produk_id))
    return lihat_keranjang()


@app.delete("/keranjang")
@butuh_login()
def kosongkan_keranjang():
    db.eksekusi("DELETE FROM keranjang WHERE pelanggan_id = ?", (_pid(),))
    return lihat_keranjang()


# ----------------------------------------------------------------------- checkout
@app.post("/checkout")
@butuh_login()
def checkout():
    body = request.get_json(silent=True) or {}
    pid = _pid()
    simpan = (body.get("simulasi") or "").lower()

    items, subtotal = _isi_keranjang(pid)
    if not items:
        raise tidak_valid("Keranjang masih kosong")

    kurir = (body.get("kurir") or "reguler").lower()
    if kurir not in ONGKIR:
        raise tidak_valid(f"kurir harus salah satu dari: {', '.join(ONGKIR)}")
    ongkir = 0 if subtotal >= GRATIS_ONGKIR_MIN else ONGKIR[kurir]
    oid = "psn_" + uuid.uuid4().hex[:18]
    nomor = _nomor()
    token = (request.headers.get("Authorization") or "")[7:].strip()

    wadah = {"oid": oid, "pesanan": None}

    def validasi_pelanggan(k):
        profil = _ambil_pelanggan(pid, token)
        alamat = None
        if body.get("alamat_id"):
            for a in profil.get("alamat") or []:
                if int(a["id"]) == int(body["alamat_id"]):
                    alamat = a
                    break
            if not alamat:
                raise ApiError(422, "ALAMAT_TIDAK_DITEMUKAN", "alamat_id bukan milik pelanggan ini")
        else:
            alamat = profil.get("alamat_utama")
        if not alamat:
            raise ApiError(422, "ALAMAT_KOSONG", "Tambahkan alamat pengiriman sebelum checkout")
        k["pelanggan"] = profil
        k["alamat"] = alamat
        return {"alamat_json": json.dumps(alamat, ensure_ascii=False)}

    def reservasi_stok(k):
        hasil = httpc.post(
            config.KATALOG_URL, "/internal/reservasi",
            json={
                "order_ref": oid,
                "items": [{"produk_id": i["produk_id"], "qty": i["qty"]} for i in items],
                "ttl_detik": config.RESERVASI_TTL,
            },
            service_token=True,
        )
        catat(oid, "reservasi_stok", "AKSI", "INFO",
              f"reservasi {hasil['id']} total {hasil['total']}")
        return {"reservasi_id": hasil["id"], "subtotal_reservasi": hasil["total"]}

    def simpan_pesanan(k):
        with db.transaksi():
            db.eksekusi(
                """INSERT INTO pesanan (id, nomor, pelanggan_id, status, subtotal, ongkir, total,
                   kurir, catatan, alamat_json, reservasi_id)
                   VALUES (?, ?, ?, 'MENUNGGU_PEMBAYARAN', ?, ?, ?, ?, ?, ?, ?)""",
                (oid, nomor, pid, k.get("subtotal_reservasi", subtotal), ongkir,
                 k.get("subtotal_reservasi", subtotal) + ongkir, kurir, body.get("catatan"),
                 k["alamat_json"], k["reservasi_id"]),
            )
            for it in items:
                db.eksekusi(
                    """INSERT INTO pesanan_item (pesanan_id, produk_id, nama_produk, harga, qty, subtotal)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (oid, it["produk_id"], it["nama_produk"], it["harga_satuan"], it["qty"],
                     it["harga_satuan"] * it["qty"]),
                )
        return {"pesanan_tersimpan": True}

    def kompensasi_pesanan(k, hasil):
        db.eksekusi(
            "UPDATE pesanan SET status = 'DIBATALKAN', alasan_batal = ?, diperbarui_at = ? WHERE id = ?",
            ("checkout gagal pada langkah berikutnya (kompensasi saga)", waktu_iso(), oid),
        )
        return {}

    def inisiasi_pembayaran(k):
        if SIMULASI_AKTIF and simpan == "gagal_pembayaran":
            raise ApiError(502, "SIMULASI_PEMBAYARAN_GAGAL",
                           "Simulasi: Pembayaran Service menolak inisiasi (uji kompensasi)")
        if not INTEGRASI_PEMBAYARAN:
            catat(oid, "inisiasi_pembayaran", "AKSI", "DILEWATI", "integrasi pembayaran nonaktif")
            return {"pembayaran_id": None}
        bayar = httpc.post(
            config.PEMBAYARAN_URL, "/pembayaran",
            json={
                "pesanan_id": oid,
                "nomor_pesanan": nomor,
                "pelanggan_id": pid,
                "jumlah": k.get("subtotal_reservasi", subtotal) + ongkir,
                "metode": body.get("metode") or "virtual_account",
                "nama_pelanggan": (k.get("pelanggan") or {}).get("nama"),
            },
            service_token=True,
        )
        db.eksekusi("UPDATE pesanan SET pembayaran_id = ?, diperbarui_at = ? WHERE id = ?",
                    (bayar["id"], waktu_iso(), oid))
        return {"pembayaran_id": bayar["id"], "pembayaran": bayar}

    saga = Saga("checkout", catat=catat, pesanan_id=oid)
    saga.tambah("validasi_pelanggan", validasi_pelanggan, None, "ambil profil & alamat pelanggan")
    saga.tambah("reservasi_stok", reservasi_stok,
                lambda k, h: httpc.post(config.KATALOG_URL, f"/internal/reservasi/{k['reservasi_id']}/rilis",
                                        json={}, service_token=True),
                "reserve stok di Katalog Service")
    saga.tambah("simpan_pesanan", simpan_pesanan, kompensasi_pesanan, "buat pesanan status MENUNGGU_PEMBAYARAN")
    saga.tambah("inisiasi_pembayaran", inisiasi_pembayaran, None, "minta tagihan ke Pembayaran Service")

    try:
        hasil = saga.jalankan(wadah)
    except KegagalanSaga as exc:
        detail = exc.detail(saga)
        if isinstance(exc.galat, ApiError):
            # pertahankan kode galat asli, tetapi sertakan jejak kompensasi
            raise ApiError(
                exc.galat.status, exc.galat.kode, exc.galat.pesan,
                {
                    "langkah_gagal": exc.langkah,
                    "kompensasi": exc.kompensasi,
                    "jejak": detail["jejak"],
                    "pesan_langkah": str(exc.galat)[:300],
                },
            ) from exc
        status = 502 if "pembayaran" in exc.langkah else 409
        raise ApiError(
            status, "CHECKOUT_GAGAL",
            f"Checkout gagal pada langkah '{exc.langkah}' dan sudah dikompensasi",
            detail,
        ) from exc

    db.eksekusi("DELETE FROM keranjang WHERE pelanggan_id = ?", (pid,))
    pesanan = _pesanan_lengkap(oid)
    return sukses({"pesanan": pesanan, "pembayaran": hasil.get("pembayaran"), "saga": saga.jejak()}, status=201)


# ------------------------------------------------------------------------ pesanan
@app.get("/pesanan")
@butuh_login()
def riwayat_pesanan():
    halaman = max(int(request.args.get("halaman", 1) or 1), 1)
    batas = min(max(int(request.args.get("batas", 20) or 20), 1), 100)
    where = ["pelanggan_id = ?"]
    params = [_pid()]
    if request.args.get("status"):
        where.append("status = ?")
        params.append(request.args["status"])
    klausa = "WHERE " + " AND ".join(where)
    total = db.skalar(f"SELECT COUNT(*) FROM pesanan {klausa}", params, 0)
    rows = db.q(f"SELECT * FROM pesanan {klausa} ORDER BY dibuat_at DESC, rowid DESC LIMIT ? OFFSET ?",
                params + [batas, (halaman - 1) * batas])
    for r in rows:
        r["items"] = db.q("SELECT produk_id, nama_produk, harga, qty, subtotal FROM pesanan_item WHERE pesanan_id = ?", (r["id"],))
        r["alamat"] = json.loads(r["alamat_json"]) if r["alamat_json"] else None
        r.pop("alamat_json", None)
    return daftar(rows, total=total, halaman=halaman, batas=batas)


@app.get("/pesanan-admin")
@butuh_login("admin")
def semua_pesanan():
    """Daftar seluruh pesanan untuk dashboard admin."""
    halaman = max(int(request.args.get("halaman", 1) or 1), 1)
    batas = min(max(int(request.args.get("batas", 30) or 30), 1), 100)
    where, params = [], []
    if request.args.get("status"):
        where.append("status = ?")
        params.append(request.args["status"])
    if request.args.get("pelanggan_id"):
        where.append("pelanggan_id = ?")
        params.append(int(request.args["pelanggan_id"]))
    klausa = ("WHERE " + " AND ".join(where)) if where else ""
    total = db.skalar(f"SELECT COUNT(*) FROM pesanan {klausa}", params, 0)
    rows = db.q(f"SELECT * FROM pesanan {klausa} ORDER BY dibuat_at DESC, rowid DESC LIMIT ? OFFSET ?",
                params + [batas, (halaman - 1) * batas])
    for r in rows:
        r["items"] = db.q("SELECT produk_id, nama_produk, harga, qty, subtotal FROM pesanan_item WHERE pesanan_id = ?", (r["id"],))
        r["alamat"] = json.loads(r["alamat_json"]) if r["alamat_json"] else None
        r.pop("alamat_json", None)
    return daftar(rows, total=total, halaman=halaman, batas=batas)


@app.get("/pesanan/<oid>")
@butuh_login()
def detail_pesanan(oid):
    return sukses(_pesanan_lengkap(oid, pelanggan_id=_pid(), peran=g.pengguna.get("peran")))


@app.post("/pesanan/<oid>/batalkan")
@butuh_login()
def batalkan_pesanan(oid):
    head = db.q1("SELECT * FROM pesanan WHERE id = ?", (oid,))
    if not head:
        raise tidak_ditemukan("Pesanan")
    if head["pelanggan_id"] != _pid() and g.pengguna.get("peran") != "admin":
        raise terlarang("Pesanan ini milik pelanggan lain")
    if head["status"] in ("DIKIRIM", "SELESAI", "DIBATALKAN"):
        raise bentrok(f"Pesanan berstatus {head['status']} tidak dapat dibatalkan")
    body = request.get_json(silent=True) or {}
    _batalkan(oid, body.get("alasan") or "dibatalkan oleh pengguna", oleh=g.pengguna.get("email"))
    return sukses(_pesanan_lengkap(oid))


def _batalkan(oid, alasan, oleh=None):
    head = db.q1("SELECT * FROM pesanan WHERE id = ?", (oid,))
    if not head:
        raise tidak_ditemukan("Pesanan")
    if head["reservasi_id"]:
        try:
            httpc.post(config.KATALOG_URL, f"/internal/reservasi/{head['reservasi_id']}/rilis",
                       json={}, service_token=True)
            catat(oid, "rilis_stok", "KOMPENSASI", "SUKSES", f"oleh {oleh or 'sistem'}")
        except httpc.UpstreamError as exc:
            catat(oid, "rilis_stok", "KOMPENSASI", "GAGAL", str(exc)[:300])
    db.eksekusi("UPDATE pesanan SET status = 'DIBATALKAN', alasan_batal = ?, diperbarui_at = ? WHERE id = ?",
                (alasan, waktu_iso(), oid))
    return True


@app.post("/pesanan/<oid>/status")
@butuh_login("admin")
def ubah_status(oid):
    head = db.q1("SELECT * FROM pesanan WHERE id = ?", (oid,))
    if not head:
        raise tidak_ditemukan("Pesanan")
    body = request.get_json(silent=True) or {}
    tujuan = (body.get("status") or "").upper()
    if tujuan not in ALUR_STATUS:
        raise tidak_valid(f"status tidak dikenal: {tujuan}")
    if tujuan not in ALUR_STATUS[head["status"]]:
        raise bentrok(f"Transisi {head['status']} -> {tujuan} tidak diizinkan")
    db.eksekusi("UPDATE pesanan SET status = ?, diperbarui_at = ? WHERE id = ?",
                (tujuan, waktu_iso(), oid))
    catat(oid, f"status_{tujuan.lower()}", "AKSI", "SUKSES", f"oleh {g.pengguna.get('email')}")
    return sukses(_pesanan_lengkap(oid, peran="admin"))


# ----------------------------------------------------------------------- internal
@app.post("/internal/pesanan/<oid>/pembayaran")
@butuh_layanan()
def webhook_pembayaran(oid):
    """Dipanggil Pembayaran Service saat status pembayaran berubah."""
    body = request.get_json(silent=True) or {}
    status_bayar = (body.get("status") or "").upper()
    head = db.q1("SELECT * FROM pesanan WHERE id = ?", (oid,))
    if not head:
        raise tidak_ditemukan("Pesanan")
    db.eksekusi("UPDATE pesanan SET pembayaran_id = COALESCE(?, pembayaran_id), diperbarui_at = ? WHERE id = ?",
                (body.get("pembayaran_id"), waktu_iso(), oid))

    if status_bayar == "BERHASIL":
        if head["status"] != "MENUNGGU_PEMBAYARAN":
            catat(oid, "webhook_pembayaran", "AKSI", "DIABAIKAN", f"status pesanan {head['status']}")
            return sukses({"pesanan": _pesanan_lengkap(oid, peran="admin"), "diabaikan": True})
        if head["reservasi_id"]:
            try:
                httpc.post(config.KATALOG_URL, f"/internal/reservasi/{head['reservasi_id']}/komit",
                           json={}, service_token=True)
                catat(oid, "komit_stok", "AKSI", "SUKSES", "stok dikeluarkan permanen")
            except httpc.UpstreamError as exc:
                catat(oid, "komit_stok", "AKSI", "GAGAL", str(exc)[:300])
                raise ApiError(502, "KOMIT_STOK_GAGAL",
                               "Pembayaran berhasil tetapi komit stok gagal; perlu tindak manual",
                               str(exc)[:300])
        db.eksekusi("UPDATE pesanan SET status = 'DIBAYAR', diperbarui_at = ? WHERE id = ?",
                    (waktu_iso(), oid))
        catat(oid, "pembayaran_berhasil", "AKSI", "SUKSES", body.get("keterangan"))
        return sukses({"pesanan": _pesanan_lengkap(oid, peran="admin"), "diabaikan": False})

    if status_bayar in ("GAGAL", "KEDALUWARSA", "DIBATALKAN"):
        if head["status"] == "MENUNGGU_PEMBAYARAN":
            _batalkan(oid, f"pembayaran {status_bayar.lower()}", oleh="pembayaran-service")
            catat(oid, "pembayaran_gagal", "AKSI", "SUKSES", body.get("keterangan"))
        return sukses({"pesanan": _pesanan_lengkap(oid, peran="admin"), "diabaikan": False})

    raise tidak_valid(f"status pembayaran tidak dikenal: {status_bayar}")


@app.get("/internal/pesanan/<oid>")
@butuh_layanan()
def internal_pesanan(oid):
    return sukses(_pesanan_lengkap(oid, peran="admin"))


@app.get("/internal/statistik")
@butuh_layanan()
def statistik():
    per_status = {r["status"]: r["jumlah"] for r in db.q(
        "SELECT status, COUNT(*) AS jumlah FROM pesanan GROUP BY status")}
    return sukses({
        "jumlah_pesanan": db.skalar("SELECT COUNT(*) FROM pesanan", bawaan=0),
        "per_status": per_status,
        "nilai_transaksi": db.skalar(
            "SELECT COALESCE(SUM(total),0) FROM pesanan WHERE status NOT IN ('DIBATALKAN')", bawaan=0),
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8003"))
    app.logger.info("Order Service siap di http://0.0.0.0:%s", port)
    app.run(host="0.0.0.0", port=port, threaded=True)

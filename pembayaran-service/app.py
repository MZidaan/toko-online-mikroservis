"""
Pembayaran Service (Peserta 4) - port 8004.

Tanggung jawab:
  * Inisiasi tagihan untuk sebuah pesanan (idempoten per pesanan_id) dengan
    nomor virtual account simulasi.
  * Simulasi hasil pembayaran (berhasil / gagal) untuk keperluan demo & pengujian.
  * Sinkronisasi status: mengirim ulang webhook ke Order Service, dan menyapu
    pembayaran MENUNGGU yang melewati kedaluwarsa menjadi KEDALUWARSA.
  * Laporan: ringkasan agregat dan ekspor CSV transaksi.
"""
import csv
import io
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

from flask import g, request, Response

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import config, db, httpc  # noqa: E402
from common.errors import ApiError, bentrok, terlarang, tidak_ditemukan, tidak_valid  # noqa: E402
from common.responses import daftar, sukses, waktu_iso  # noqa: E402
from common.security import butuh_layanan, butuh_login  # noqa: E402
from common.service import create_app  # noqa: E402

DISK = os.path.dirname(os.path.abspath(__file__))
SKEMA = open(os.path.join(DISK, "schema.sql"), encoding="utf-8").read()

app = create_app(__name__, db_name="pembayaran", skema=SKEMA)

METODE = {"virtual_account", "transfer_bank", "e_wallet", "qris", "cod"}
STATUS_AKHIR = {"BERHASIL", "GAGAL", "KEDALUWARSA", "DIBATALKAN"}


# --------------------------------------------------------------------------- util
def catat(pembayaran_id, jenis, lama, baru, pesan=None):
    db.eksekusi(
        """INSERT INTO pembayaran_event (pembayaran_id, jenis, status_lama, status_baru, pesan)
           VALUES (?, ?, ?, ?, ?)""",
        (pembayaran_id, jenis, lama, baru, pesan),
    )


def _referensi(metode):
    angka = "".join(c for c in uuid.uuid4().hex if c.isdigit())[:12].ljust(12, "0")
    if metode == "virtual_account":
        return "8808" + angka
    if metode == "qris":
        return "QR-" + uuid.uuid4().hex[:12].upper()
    return "REF-" + uuid.uuid4().hex[:12].upper()


def _ambil(pid):
    row = db.q1("SELECT * FROM pembayaran WHERE id = ?", (pid,))
    if not row:
        raise tidak_ditemukan("Pembayaran")
    return row


def _detail(row):
    data = dict(row)
    data["event"] = db.q(
        "SELECT jenis, status_lama, status_baru, pesan, waktu FROM pembayaran_event WHERE pembayaran_id = ? ORDER BY id",
        (row["id"],),
    )
    return data


def _kirim_webhook(row):
    """Beri tahu Order Service; kegagalan dicatat, bukan menggagalkan transaksi lokal."""
    muatan = {
        "pembayaran_id": row["id"],
        "status": row["status"],
        "keterangan": row["keterangan"],
        "jumlah": row["jumlah"],
    }
    try:
        httpc.post(config.ORDER_URL, f"/internal/pesanan/{row['pesanan_id']}/pembayaran",
                   json=muatan, service_token=True)
        db.eksekusi("UPDATE pembayaran SET jumlah_webhook = jumlah_webhook + 1 WHERE id = ?", (row["id"],))
        catat(row["id"], "WEBHOOK", None, row["status"], "terkirim ke order-service")
        return {"terkirim": True}
    except httpc.UpstreamError as exc:
        catat(row["id"], "WEBHOOK", None, row["status"], f"gagal: {str(exc)[:300]}")
        app.logger.warning("webhook order gagal untuk %s: %s", row["pesanan_id"], exc)
        return {"terkirim": False, "pesan": str(exc)[:300]}


def _ubah_status(row, status, keterangan=None, kirim=True):
    if row["status"] == status:
        return _detail(row)
    if row["status"] in STATUS_AKHIR:
        raise bentrok(f"Pembayaran sudah berstatus akhir {row['status']}")
    db.eksekusi(
        """UPDATE pembayaran SET status = ?, keterangan = COALESCE(?, keterangan),
           diperbarui_at = ?, dibayar_at = CASE WHEN ? = 'BERHASIL' THEN ? ELSE dibayar_at END
           WHERE id = ?""",
        (status, keterangan, waktu_iso(), status, waktu_iso(), row["id"]),
    )
    catat(row["id"], "PERUBAHAN_STATUS", row["status"], status, keterangan)
    baru = _ambil(row["id"])
    if kirim:
        baru["_webhook"] = _kirim_webhook(baru)
    return _detail(baru)


# ---------------------------------------------------------------------- inisiasi
@app.post("/pembayaran")
@butuh_layanan()
def inisiasi():
    body = request.get_json(silent=True) or {}
    pesanan_id = (body.get("pesanan_id") or "").strip()
    if not pesanan_id:
        raise tidak_valid("pesanan_id wajib diisi")
    try:
        jumlah = int(body.get("jumlah"))
    except (TypeError, ValueError):
        raise tidak_valid("jumlah harus bilangan bulat positif")
    if jumlah <= 0:
        raise tidak_valid("jumlah harus lebih besar dari 0")
    metode = (body.get("metode") or "virtual_account").lower()
    if metode not in METODE:
        raise tidak_valid(f"metode harus salah satu dari: {', '.join(sorted(METODE))}")

    ada = db.q1("SELECT * FROM pembayaran WHERE pesanan_id = ?", (pesanan_id,))
    if ada:  # idempoten: pesanan yang sama tidak membuat tagihan ganda
        catat(ada["id"], "INISIASI_ULANG", ada["status"], ada["status"], "permintaan idempoten")
        data = _detail(ada)
        data["idempoten"] = True
        return sukses(data, status=200)

    pid = "pay_" + uuid.uuid4().hex[:16]
    kedaluwarsa = (datetime.now(timezone.utc) + timedelta(seconds=config.PEMBAYARAN_TTL)).isoformat(timespec="seconds")
    db.sisip(
        """INSERT INTO pembayaran (id, pesanan_id, nomor_pesanan, pelanggan_id, metode, jumlah,
           status, referensi, nama_pelanggan, kedaluwarsa_at)
           VALUES (?, ?, ?, ?, ?, ?, 'MENUNGGU', ?, ?, ?)""",
        (pid, pesanan_id, body.get("nomor_pesanan") or "-", int(body.get("pelanggan_id") or 0),
         metode, jumlah, _referensi(metode), body.get("nama_pelanggan"), kedaluwarsa),
    )
    catat(pid, "INISIASI", None, "MENUNGGU", f"tagihan {metode}")
    data = _detail(_ambil(pid))
    data["instruksi"] = _instruksi(data)
    data["idempoten"] = False
    return sukses(data, status=201)


def _instruksi(row):
    if row["metode"] == "virtual_account":
        return f"Transfer ke VA {row['referensi']} sebesar Rp{row['jumlah']:,}".replace(",", ".")
    if row["metode"] == "qris":
        return f"Pindai kode QRIS {row['referensi']} sebesar Rp{row['jumlah']:,}".replace(",", ".")
    if row["metode"] == "cod":
        return "Bayar tunai saat pesanan diterima."
    return f"Gunakan referensi {row['referensi']} sebesar Rp{row['jumlah']:,}".replace(",", ".")


# ------------------------------------------------------------------- baca status
@app.get("/pembayaran")
@butuh_login()
def daftar_pembayaran():
    halaman = max(int(request.args.get("halaman", 1) or 1), 1)
    batas = min(max(int(request.args.get("batas", 20) or 20), 1), 100)
    where, params = [], []
    if g.pengguna.get("peran") != "admin":
        where.append("pelanggan_id = ?")
        params.append(int(g.pengguna["sub"]))
    elif request.args.get("pelanggan_id"):
        where.append("pelanggan_id = ?")
        params.append(int(request.args["pelanggan_id"]))
    if request.args.get("status"):
        where.append("status = ?")
        params.append(request.args["status"].upper())
    if request.args.get("pesanan_id"):
        where.append("pesanan_id = ?")
        params.append(request.args["pesanan_id"])
    klausa = ("WHERE " + " AND ".join(where)) if where else ""
    total = db.skalar(f"SELECT COUNT(*) FROM pembayaran {klausa}", params, 0)
    rows = db.q(f"SELECT * FROM pembayaran {klausa} ORDER BY dibuat_at DESC, rowid DESC LIMIT ? OFFSET ?",
                params + [batas, (halaman - 1) * batas])
    return daftar(rows, total=total, halaman=halaman, batas=batas)


@app.get("/pembayaran/<pid>")
@butuh_login()
def detail_pembayaran(pid):
    row = _ambil(pid)
    if g.pengguna.get("peran") != "admin" and row["pelanggan_id"] != int(g.pengguna["sub"]):
        raise terlarang("Pembayaran ini milik pelanggan lain")
    data = _detail(row)
    data["instruksi"] = _instruksi(row)
    return sukses(data)


# -------------------------------------------------------------------- simulasi
@app.post("/pembayaran/<pid>/simulasi")
@butuh_login("admin")
def simulasi(pid):
    row = _ambil(pid)
    body = request.get_json(silent=True) or {}
    hasil = (body.get("hasil") or "berhasil").lower()
    if hasil not in ("berhasil", "gagal", "kedaluwarsa"):
        raise tidak_valid("hasil harus 'berhasil', 'gagal', atau 'kedaluwarsa'")
    peta = {"berhasil": "BERHASIL", "gagal": "GAGAL", "kedaluwarsa": "KEDALUWARSA"}
    keterangan = body.get("keterangan") or {
        "berhasil": "Pembayaran berhasil (simulasi)",
        "gagal": "Pembayaran ditolak (simulasi)",
        "kedaluwarsa": "Tagihan kedaluwarsa (simulasi)",
    }[hasil]
    data = _ubah_status(row, peta[hasil], keterangan)
    return sukses(data)


@app.post("/internal/pembayaran/<pid>/sinkronisasi")
@butuh_layanan()
def sinkronisasi_satu(pid):
    row = _ambil(pid)
    hasil = _kirim_webhook(row)
    return sukses({"pembayaran": _detail(_ambil(pid)), "webhook": hasil})


@app.post("/internal/pembayaran/<pid>/batalkan")
@butuh_layanan()
def batalkan(pid):
    row = _ambil(pid)
    body = request.get_json(silent=True) or {}
    return sukses(_ubah_status(row, "DIBATALKAN", body.get("alasan") or "dibatalkan oleh sistem"))


@app.post("/internal/sinkronisasi")
@butuh_layanan()
def sinkronisasi_massal():
    """Sapu tagihan kedaluwarsa lalu kirim ulang webhook yang belum tersampaikan."""
    sekarang = waktu_iso()
    kedaluwarsa = db.q("SELECT * FROM pembayaran WHERE status = 'MENUNGGU' AND kedaluwarsa_at <= ? LIMIT 200",
                       (sekarang,))
    ditandai = []
    for row in kedaluwarsa:
        _ubah_status(row, "KEDALUWARSA", "Melewati batas waktu pembayaran")
        ditandai.append(row["id"])
    belum = db.q("SELECT * FROM pembayaran WHERE jumlah_webhook = 0 AND status IN ('BERHASIL','GAGAL','KEDALUWARSA') LIMIT 200")
    ulang = []
    for row in belum:
        if _kirim_webhook(row)["terkirim"]:
            ulang.append(row["id"])
    return sukses({"kedaluwarsa": ditandai, "webhook_dikirim_ulang": ulang})


# ---------------------------------------------------------------------- laporan
def _rentang():
    dari = request.args.get("dari") or "0000-01-01"
    sampai = request.args.get("sampai") or "9999-12-31"
    return dari, sampai


@app.get("/laporan/ringkasan")
@butuh_login("admin")
def laporan_ringkasan():
    dari, sampai = _rentang()
    dasar = "FROM pembayaran WHERE date(dibuat_at) BETWEEN date(?) AND date(?)"
    ringkas_status = {r["status"]: r["jumlah"] for r in db.q(
        f"SELECT status, COUNT(*) AS jumlah {dasar} GROUP BY status", (dari, sampai))}
    nominal = db.skalar(f"SELECT COALESCE(SUM(jumlah),0) {dasar} AND status = 'BERHASIL'", (dari, sampai), 0)
    semua = db.skalar(f"SELECT COALESCE(SUM(jumlah),0) {dasar}", (dari, sampai), 0)
    per_metode = db.q(
        f"""SELECT metode, COUNT(*) AS transaksi,
                   COALESCE(SUM(CASE WHEN status = 'BERHASIL' THEN jumlah ELSE 0 END),0) AS nominal
            {dasar} GROUP BY metode ORDER BY nominal DESC""",
        (dari, sampai),
    )
    harian = db.q(
        f"""SELECT date(dibuat_at) AS tanggal, COUNT(*) AS transaksi,
                   COALESCE(SUM(CASE WHEN status = 'BERHASIL' THEN jumlah ELSE 0 END),0) AS nominal
            {dasar} GROUP BY date(dibuat_at) ORDER BY tanggal DESC LIMIT 30""",
        (dari, sampai),
    )
    berhasil = ringkas_status.get("BERHASIL", 0)
    total_transaksi = sum(ringkas_status.values())
    return sukses({
        "periode": {"dari": dari, "sampai": sampai},
        "jumlah_transaksi": total_transaksi,
        "per_status": ringkas_status,
        "nominal_berhasil": nominal,
        "nominal_semua": semua,
        "tingkat_keberhasilan": round(berhasil / total_transaksi * 100, 2) if total_transaksi else 0.0,
        "per_metode": per_metode,
        "harian": harian,
    })


@app.get("/laporan/transaksi.csv")
@butuh_login("admin")
def laporan_csv():
    dari, sampai = _rentang()
    rows = db.q(
        """SELECT id, pesanan_id, nomor_pesanan, pelanggan_id, metode, jumlah, status,
                  referensi, dibuat_at, dibayar_at
           FROM pembayaran WHERE date(dibuat_at) BETWEEN date(?) AND date(?)
           ORDER BY dibuat_at""",
        (dari, sampai),
    )
    buf = io.StringIO()
    penulis = csv.writer(buf, delimiter=";")
    penulis.writerow(["id", "pesanan_id", "nomor_pesanan", "pelanggan_id", "metode",
                      "jumlah", "status", "referensi", "dibuat_at", "dibayar_at"])
    for r in rows:
        penulis.writerow([r[k] if r[k] is not None else "" for k in r])
    return Response(
        "\ufeff" + buf.getvalue(),
        content_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=laporan-transaksi.csv"},
    )


@app.get("/internal/statistik")
@butuh_layanan()
def statistik():
    return sukses({
        "transaksi": db.skalar("SELECT COUNT(*) FROM pembayaran", bawaan=0),
        "per_status": {r["status"]: r["jumlah"] for r in db.q(
            "SELECT status, COUNT(*) AS jumlah FROM pembayaran GROUP BY status")},
        "nominal_berhasil": db.skalar(
            "SELECT COALESCE(SUM(jumlah),0) FROM pembayaran WHERE status = 'BERHASIL'", bawaan=0),
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8004"))
    app.logger.info("Pembayaran Service siap di http://0.0.0.0:%s", port)
    app.run(host="0.0.0.0", port=port, threaded=True)

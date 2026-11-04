"""
Kerangka saga orkestrasi untuk checkout (Peserta 3).

Pola: setiap langkah punya aksi maju dan aksi kompensasi. Bila satu langkah gagal,
seluruh langkah yang sudah berhasil dikompensasi dengan urutan terbalik, lalu
kegagalan diteruskan ke pemanggil bersama jejak lengkapnya.

Contoh pada checkout:
    1. validasi_pelanggan       (tanpa kompensasi, hanya baca)
    2. reservasi_stok           -> kompensasi: rilis reservasi di Katalog Service
    3. simpan_pesanan           -> kompensasi: tandai pesanan DIBATALKAN
    4. inisiasi_pembayaran      -> kompensasi: (opsional) batalkan pembayaran
"""
import json
import time
import traceback


class Langkah:
    def __init__(self, nama, aksi, kompensasi=None, keterangan=""):
        self.nama = nama
        self.aksi = aksi
        self.kompensasi = kompensasi
        self.keterangan = keterangan
        self.status = "BELUM"
        self.hasil = None
        self.galat = None


class Saga:
    """Eksekutor saga dengan pencatatan ke callback `catat(pesanan_id, langkah, jenis, status, pesan)`."""

    def __init__(self, nama, catat=None, pesanan_id=None):
        self.nama = nama
        self.langkah = []
        self._catat = catat or (lambda *a, **k: None)
        self.pesanan_id = pesanan_id

    def tambah(self, nama, aksi, kompensasi=None, keterangan=""):
        self.langkah.append(Langkah(nama, aksi, kompensasi, keterangan))
        return self

    # ------------------------------------------------------------------ eksekusi
    def jalankan(self, konteks=None):
        konteks = konteks if konteks is not None else {}
        for langkah in self.langkah:
            mulai = time.perf_counter()
            self._catat(self.pesanan_id, langkah.nama, "AKSI", "MULAI", langkah.keterangan)
            try:
                langkah.hasil = langkah.aksi(konteks) or {}
                if isinstance(langkah.hasil, dict):
                    konteks.update(langkah.hasil)
                langkah.status = "SUKSES"
                self._catat(self.pesanan_id, langkah.nama, "AKSI", "SUKSES",
                            f"{int((time.perf_counter() - mulai) * 1000)} ms")
            except Exception as exc:  # noqa: BLE001
                langkah.status = "GAGAL"
                langkah.galat = exc
                self._catat(self.pesanan_id, langkah.nama, "AKSI", "GAGAL", str(exc)[:500])
                jejak = self._kompensasi(konteks)
                raise KegagalanSaga(langkah.nama, exc, jejak) from exc
        return konteks

    def _kompensasi(self, konteks):
        jejak = []
        for langkah in reversed(self.langkah):
            if langkah.status != "SUKSES" or not langkah.kompensasi:
                continue
            self._catat(self.pesanan_id, langkah.nama, "KOMPENSASI", "MULAI",
                        langkah.keterangan or "membatalkan efek langkah")
            try:
                hasil = langkah.kompensasi(konteks, langkah.hasil) or {}
                if isinstance(hasil, dict):
                    konteks.update(hasil)
                langkah.status = "DIKOMPENSASI"
                self._catat(self.pesanan_id, langkah.nama, "KOMPENSASI", "SUKSES", None)
                jejak.append({"langkah": langkah.nama, "hasil": "SUKSES"})
            except Exception as exc:  # noqa: BLE001
                # Kompensasi idempoten; kegagalan dicatat untuk investigasi manual.
                self._catat(self.pesanan_id, langkah.nama, "KOMPENSASI", "GAGAL", str(exc)[:500])
                jejak.append({"langkah": langkah.nama, "hasil": "GAGAL", "pesan": str(exc)[:300]})
        return jejak

    def jejak(self):
        return [
            {
                "langkah": l.nama,
                "status": l.status,
                "keterangan": l.keterangan,
                "galat": (str(l.galat)[:300] if l.galat else None),
            }
            for l in self.langkah
        ]


class KegagalanSaga(Exception):
    def __init__(self, langkah, galat, kompensasi):
        super().__init__(f"langkah '{langkah}' gagal: {galat}")
        self.langkah = langkah
        self.galat = galat
        self.kompensasi = kompensasi
        self.ringkas_galat = str(galat)[:300]

    def detail(self, saga=None):
        return {
            "langkah_gagal": self.langkah,
            "pesan": self.ringkas_galat,
            "kompensasi": self.kompensasi,
            "jejak": saga.jejak() if saga else [],
        }


def ringkas_kegagalan(exc):
    if isinstance(exc, KegagalanSaga):
        return exc.detail()
    return {"pesan": str(exc)[:300], "tipe": type(exc).__name__}


def jaga(fn):
    """Bungkus aksi agar galat apa pun tidak menjatuhkan proses."""
    try:
        return fn()
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        raise


def json_aman(nilai, bawaan=None):
    try:
        return json.dumps(nilai, ensure_ascii=False)
    except (TypeError, ValueError):
        return bawaan

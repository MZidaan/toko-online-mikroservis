"""
Menjalankan seluruh tes. Bila layanan belum hidup, skrip ini menyalakannya sendiri
(python app.py per layanan) memakai DATA_DIR sementara, lalu mematikannya kembali.

Contoh:
    python tests/run_tests.py                # semua tahap yang tersedia
    python tests/run_tests.py -v             # verbose
    python tests/run_tests.py --tanpa-boot   # pakai layanan yang sudah berjalan
    python tests/run_tests.py --layanan katalog,pelanggan
"""
import argparse
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest

DISK = os.path.dirname(os.path.abspath(__file__))
AKAR = os.path.dirname(DISK)
sys.path.insert(0, DISK)
sys.path.insert(0, AKAR)

from base import URL, butuh_layanan  # noqa: E402

try:  # konsol Windows kadang bukan UTF-8
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


try:  # konsol Windows kadang bukan UTF-8
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


LAYANAN = [
    ("katalog", "katalog-service/app.py", 8001),
    ("pelanggan", "pelanggan-service/app.py", 8002),
    ("order", "order-service/app.py", 8003),
    ("pembayaran", "pembayaran-service/app.py", 8004),
    ("gateway", "gateway/app.py", 8000),
]


def tersedia(nama, berkas):
    return os.path.exists(os.path.join(AKAR, berkas))


def port_bebas(port):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def tunggu_health(basis, batas=30):
    mulai = time.time()
    while time.time() - mulai < batas:
        if butuh_layanan(basis, 1.0):
            return True
        time.sleep(0.4)
    return False


def boot(data_dir, hanya=None):
    proses = []
    lingkungan = os.environ.copy()
    lingkungan.update({"DATA_DIR": data_dir, "PYTHONPATH": AKAR, "PYTHONUNBUFFERED": "1"})
    # Arsip tahap 3 belum membawa layanan pembayaran: matikan integrasinya agar
    # checkout tetap berjalan (kompensasi tetap diuji lewat hook simulasi).
    if not tersedia("pembayaran", "pembayaran-service/app.py"):
        lingkungan.setdefault("INTEGRASI_PEMBAYARAN", "0")
    for nama, berkas, port in LAYANAN:
        if hanya and nama not in hanya:
            continue
        if not tersedia(nama, berkas):
            continue
        if not port_bebas(port):
            print(f"  - {nama}: port {port} sudah dipakai, memakai proses yang ada")
            continue
        log = open(os.path.join(data_dir, f"{nama}.log"), "w", encoding="utf-8")
        p = subprocess.Popen([sys.executable, os.path.join(AKAR, berkas)],
                             cwd=AKAR, env=lingkungan, stdout=log, stderr=subprocess.STDOUT)
        proses.append((nama, p, log))
        print(f"  - {nama}: dijalankan (pid {p.pid}, port {port})")
    return proses


def matikan(proses):
    for _, p, log in proses:
        try:
            p.terminate()
            p.wait(timeout=8)
        except Exception:  # noqa: BLE001
            p.kill()
        finally:
            log.close()


def main():
    parser = argparse.ArgumentParser(description="Runner tes tugas kelompok")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--tanpa-boot", action="store_true", help="jangan menyalakan layanan")
    parser.add_argument("--layanan", default="", help="daftar dipisah koma, mis. katalog,pelanggan")
    parser.add_argument("--pertahankan", action="store_true", help="biarkan layanan tetap hidup")
    arg = parser.parse_args()

    hanya = {x.strip() for x in arg.layanan.split(",") if x.strip()} or None
    data_dir = os.environ.get("DATA_DIR") or tempfile.mkdtemp(prefix="uji-toko-")
    print(f"DATA_DIR = {data_dir}")

    proses = []
    if not arg.tanpa_boot:
        proses = boot(data_dir, hanya)
        for nama, _, port in LAYANAN:
            if hanya and nama not in hanya:
                continue
            if not butuh_layanan(URL[nama], 0.5):
                continue
            siap = tunggu_health(URL[nama])
            print(f"  - {nama}: {'siap' if siap else 'TIDAK MERESPONS'} ({URL[nama]})")

    try:
        suite = unittest.defaultTestLoader.discover(DISK, pattern="test_*.py", top_level_dir=DISK)
        hasil = unittest.TextTestRunner(verbosity=2 if arg.verbose else 1).run(suite)
    finally:
        if proses and not arg.pertahankan:
            matikan(proses)
        elif proses:
            print("Layanan dibiarkan hidup; hentikan manual dengan Ctrl+C pada prosesnya.")

    jumlah = hasil.testsRun
    lompat = len(hasil.skipped)
    print(f"\nRingkasan: {jumlah} tes, {len(hasil.failures)} gagal, "
          f"{len(hasil.errors)} error, {lompat} dilewati")
    if lompat and not arg.tanpa_boot:
        print("Tes dilewati karena layanan terkait tidak berjalan (normal untuk tahap awal).")
    return 0 if hasil.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())

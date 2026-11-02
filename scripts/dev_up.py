"""
Menjalankan seluruh layanan di mesin lokal tanpa Docker.

    python scripts/dev_up.py                       # semua layanan yang ada
    python scripts/dev_up.py --layanan katalog     # hanya katalog
    python scripts/dev_up.py --data-dir data/dev   # pilih folder SQLite

Tekan Ctrl+C untuk menghentikan semuanya.
"""
import argparse
import os
import subprocess
import sys
import time

DISK = os.path.dirname(os.path.abspath(__file__))
AKAR = os.path.dirname(DISK)
sys.path.insert(0, AKAR)
sys.path.insert(0, os.path.join(AKAR, "tests"))

from base import URL, butuh_layanan  # noqa: E402

LAYANAN = [
    ("katalog", "katalog-service/app.py", 8001),
    ("pelanggan", "pelanggan-service/app.py", 8002),
    ("order", "order-service/app.py", 8003),
    ("pembayaran", "pembayaran-service/app.py", 8004),
    ("gateway", "gateway/app.py", 8000),
]


def main():
    p = argparse.ArgumentParser(description="Jalankan layanan toko secara lokal")
    p.add_argument("--layanan", default="", help="mis. katalog,pelanggan")
    p.add_argument("--data-dir", default=os.path.join(AKAR, "data", "dev"))
    p.add_argument("--tanpa-tunggu", action="store_true")
    arg = p.parse_args()

    hanya = {x.strip() for x in arg.layanan.split(",") if x.strip()} or None
    os.makedirs(arg.data_dir, exist_ok=True)
    lingkungan = os.environ.copy()
    lingkungan.update({"DATA_DIR": arg.data_dir, "PYTHONPATH": AKAR, "PYTHONUNBUFFERED": "1"})
    if not os.path.exists(os.path.join(AKAR, "pembayaran-service", "app.py")):
        lingkungan.setdefault("INTEGRASI_PEMBAYARAN", "0")

    proses = []
    print(f"DATA_DIR = {arg.data_dir}")
    for nama, berkas, port in LAYANAN:
        if hanya and nama not in hanya:
            continue
        if not os.path.exists(os.path.join(AKAR, berkas)):
            continue
        log = open(os.path.join(arg.data_dir, f"{nama}.log"), "w", encoding="utf-8")
        proses.append((nama, subprocess.Popen(
            [sys.executable, os.path.join(AKAR, berkas)],
            cwd=AKAR, env=lingkungan, stdout=log, stderr=subprocess.STDOUT), log))
        print(f"  - {nama:10s} http://127.0.0.1:{port}  (log: {arg.data_dir}/{nama}.log)")

    if not arg.tanpa_tunggu:
        for nama, _, _ in proses:
            for _ in range(40):
                if butuh_layanan(URL[nama], 0.5):
                    break
                time.sleep(0.25)

    print("\nSiap. Dashboard: http://127.0.0.1:8000  -  Admin: http://127.0.0.1:8000/admin")
    print("Seed data  : python seed/seed_data.py")
    print("Tes        : python tests/run_tests.py --tanpa-boot")
    try:
        while True:
            time.sleep(1)
            if all(pr.poll() is not None for _, pr, _ in proses):
                print("Semua proses berhenti.")
                break
    except KeyboardInterrupt:
        print("\nMenghentikan layanan...")
    finally:
        for _, pr, log in proses:
            if pr.poll() is None:
                pr.terminate()
                try:
                    pr.wait(timeout=6)
                except subprocess.TimeoutExpired:
                    pr.kill()
            log.close()


if __name__ == "__main__":
    main()

"""
Seed data (Peserta 5).

Mengisi Katalog Service (kategori + produk) dan Pelanggan Service (akun demo +
alamat), lalu opsional membuat beberapa pesanan contoh beserta pembayarannya.

    python seed/seed_data.py                    # katalog + pelanggan
    python seed/seed_data.py --pesanan 3        # tambah 3 pesanan contoh (sebagian dibayar)
    python seed/seed_data.py --reset-pesanan    # hapus keranjang demo sebelum mengisi

Skrip idempoten: data yang sudah ada akan dilewati (dicocokkan lewat SKU/email).
"""
import argparse
import json
import os
import sys

import requests

DISK = os.path.dirname(os.path.abspath(__file__))
AKAR = os.path.dirname(DISK)
sys.path.insert(0, AKAR)
sys.path.insert(0, os.path.join(AKAR, "tests"))

from base import ADMIN_EMAIL, ADMIN_SANDI, TOKEN_LAYANAN, URL  # noqa: E402

try:  # konsol Windows kadang bukan UTF-8
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


BATAS = 15


def baca(nama):
    with open(os.path.join(DISK, "data", nama), encoding="utf-8") as f:
        return json.load(f)


def admin():
    r = requests.post(
        URL["pelanggan"] + "/internal/pelanggan/buat-admin",
        json={"email": ADMIN_EMAIL, "nama": "Administrator Toko", "kata_sandi": ADMIN_SANDI},
        headers={"X-Service-Token": TOKEN_LAYANAN}, timeout=BATAS,
    )
    r.raise_for_status()
    data = r.json()["data"]
    print(f"  - admin siap: {data['pengguna']['email']} ({'baru' if data.get('dibuat') else 'sudah ada'})")
    return data["token"]


def seed_katalog(token):
    data = baca("katalog.json")
    h = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
    peta_kategori = {}
    for k in data["kategori"]:
        r = requests.post(URL["katalog"] + "/kategori", json=k, headers=h, timeout=BATAS)
        if r.status_code in (201, 200):
            peta_kategori[k["nama"]] = r.json()["data"]["id"]
            print(f"  - kategori dibuat: {k['nama']}")
        else:
            daftar = requests.get(URL["katalog"] + "/kategori", timeout=BATAS).json()["data"]
            for item in daftar:
                if item["nama"].lower() == k["nama"].lower():
                    peta_kategori[k["nama"]] = item["id"]
                    break
            print(f"  - kategori sudah ada: {k['nama']}")

    ada = {p["sku"] for p in requests.get(URL["katalog"] + "/produk?batas=100&aktif=semua",
                                          timeout=BATAS).json()["data"]}
    baru = 0
    for p in data["produk"]:
        if p["sku"] in ada:
            continue
        muatan = {"sku": p["sku"], "nama": p["nama"], "harga": p["harga"], "stok": p["stok"],
                  "kategori_id": peta_kategori.get(p["kategori"]),
                  "deskripsi": f"Produk contoh kategori {p['kategori']}"}
        r = requests.post(URL["katalog"] + "/produk", json=muatan, headers=h, timeout=BATAS)
        if r.status_code == 201:
            baru += 1
        else:
            print(f"    ! gagal membuat {p['sku']}: {r.text[:120]}")
    print(f"  - produk: {baru} baru, {len(data['produk']) - baru} sudah ada")


def seed_pelanggan():
    data = baca("pelanggan.json")
    token_pelanggan = {}
    for p in data["pelanggan"]:
        r = requests.post(URL["pelanggan"] + "/auth/registrasi",
                          json={"email": p["email"], "nama": p["nama"], "kata_sandi": p["kata_sandi"],
                                "telepon": p["telepon"]}, timeout=BATAS)
        if r.status_code == 409:
            r = requests.post(URL["pelanggan"] + "/auth/login",
                              json={"email": p["email"], "kata_sandi": p["kata_sandi"]}, timeout=BATAS)
        if r.status_code >= 400:
            print(f"    ! gagal menyiapkan {p['email']}: {r.text[:120]}")
            continue
        isi = r.json()["data"]
        token_pelanggan[p["email"]] = isi["token"]
        alamat = requests.get(URL["pelanggan"] + "/alamat", timeout=BATAS,
                              headers={"Authorization": "Bearer " + isi["token"]}).json()["data"]
        if not alamat:
            a = dict(p["alamat"])
            a.update({"penerima": p["nama"], "telepon": p["telepon"]})
            requests.post(URL["pelanggan"] + "/alamat", json=a, timeout=BATAS,
                          headers={"Authorization": "Bearer " + isi["token"]})
            print(f"  - pelanggan {p['email']}: alamat ditambahkan")
        else:
            print(f"  - pelanggan {p['email']}: sudah ada ({len(alamat)} alamat)")
    return token_pelanggan


def seed_pesanan(token_admin, token_pelanggan, jumlah):
    produk = requests.get(URL["katalog"] + "/produk?batas=20", timeout=BATAS).json()["data"]
    if not produk:
        print("  ! belum ada produk, lewati pembuatan pesanan")
        return
    daftar = list(token_pelanggan.items())
    dibuat = 0
    for i in range(jumlah):
        email, token = daftar[i % len(daftar)]
        pilihan = produk[i % len(produk)]
        h = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
        requests.post(URL["order"] + "/keranjang",
                      json={"produk_id": pilihan["id"], "qty": 1 + (i % 3)}, headers=h, timeout=BATAS)
        r = requests.post(URL["order"] + "/checkout",
                          json={"kurir": "reguler",
                                "metode": ["virtual_account", "e_wallet", "qris"][i % 3]},
                          headers=h, timeout=BATAS)
        if r.status_code >= 400:
            print(f"    ! checkout gagal: {r.text[:160]}")
            continue
        hasil = r.json()["data"]
        tagihan = hasil.get("pembayaran")
        print(f"  - pesanan {hasil['pesanan']['nomor']} untuk {email}")
        if tagihan and i % 3 != 2:  # dua dari tiga dibayar
            hasil_bayar = "berhasil" if i % 3 == 0 else "gagal"
            requests.post(URL["pembayaran"] + f"/pembayaran/{tagihan['id']}/simulasi",
                          json={"hasil": hasil_bayar},
                          headers={"Authorization": "Bearer " + token_admin}, timeout=BATAS)
            print(f"    -> simulasi pembayaran: {hasil_bayar}")
        dibuat += 1
    print(f"  - {dibuat} pesanan contoh dibuat")


def main():
    p = argparse.ArgumentParser(description="Isi data contoh toko")
    p.add_argument("--pesanan", type=int, default=0, help="jumlah pesanan contoh")
    p.add_argument("--reset-pesanan", action="store_true", help="kosongkan keranjang pelanggan demo")
    arg = p.parse_args()

    print("Menghubungi layanan...")
    for nama, url in URL.items():
        try:
            requests.get(url + "/health", timeout=3).raise_for_status()
        except Exception:  # noqa: BLE001
            print(f"  ! {nama} tidak dapat dihubungi di {url}")
            if nama in ("katalog", "pelanggan"):
                print("    jalankan dulu: python scripts/dev_up.py")
                return 1

    print("Menyiapkan admin...")
    token_admin = admin()
    print("Mengisi katalog...")
    seed_katalog(token_admin)
    print("Mengisi pelanggan...")
    token_pelanggan = seed_pelanggan()
    if arg.reset_pesanan:
        for email, token in token_pelanggan.items():
            requests.delete(URL["order"] + "/keranjang", timeout=BATAS,
                            headers={"Authorization": "Bearer " + token})
        print("  - keranjang demo dikosongkan")
    if arg.pesanan:
        print("Membuat pesanan contoh...")
        seed_pesanan(token_admin, token_pelanggan, arg.pesanan)

    print("\nSelesai. Akun demo:")
    print(f"  admin     : {ADMIN_EMAIL} / {ADMIN_SANDI}")
    for p2 in baca("pelanggan.json")["pelanggan"]:
        print(f"  pelanggan : {p2['email']} / {p2['kata_sandi']}")
    print("Buka http://localhost:8000  dan  http://localhost:8000/admin")
    return 0


if __name__ == "__main__":
    sys.exit(main())

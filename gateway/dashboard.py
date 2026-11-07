"""Halaman dashboard toko dan admin (HTML + JavaScript tanpa build step)."""
import os

DISK = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(DISK, "assets", "gaya.css"), encoding="utf-8") as f:
    GAYA = f.read()
with open(os.path.join(DISK, "assets", "app.js"), encoding="utf-8") as f:
    SKRIP = f.read()


def _bungkus(judul, isi, tambahan_js=""):
    return f"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{judul}</title>
<style>{GAYA}</style>
</head>
<body>
<div id="toast" class="toast"></div>
{isi}
<script>{SKRIP}</script>
<script>{tambahan_js}</script>
</body>
</html>"""


def halaman_toko():
    isi = """
<header>
  <div class="merek">🛍️ <span>Toko Online</span> <small>mikroservis</small></div>
  <nav>
    <a href="/">Toko</a>
    <a href="/admin">Admin</a>
    <a href="#" id="tombol-masuk">Masuk</a>
    <a href="#" id="tombol-keranjang" class="neo">Keranjang <b id="badge-keranjang">0</b></a>
  </nav>
</header>

<main>
  <section class="hero">
    <div>
      <h1>Belanja mudah, stok transparan</h1>
      <p>Katalog, pesanan, dan pembayaran berjalan di layanan terpisah - semua lewat satu gateway.</p>
    </div>
    <div class="status" id="status-layanan"></div>
  </section>

  <section class="panel">
    <div class="baris-fleks">
      <input id="cari" placeholder="Cari produk atau SKU…" oninput="toko.saring()">
      <select id="filter-kategori" onchange="toko.saring()"><option value="">Semua kategori</option></select>
      <button class="ghost" onclick="toko.muat()">Muat ulang</button>
    </div>
    <div id="daftar-produk" class="grid-produk"></div>
  </section>

  <section class="panel" id="panel-pesanan">
    <h2>Pesanan saya</h2>
    <div id="daftar-pesanan" class="tabel-bungkus"></div>
  </section>
</main>

<!-- Modal masuk / daftar -->
<div class="modal" id="modal-masuk">
  <div class="kartu">
    <h2 id="judul-masuk">Masuk</h2>
    <label>Email <input id="masuk-email" type="email" placeholder="nama@contoh.test"></label>
    <label>Kata sandi <input id="masuk-sandi" type="password" placeholder="minimal 8 karakter"></label>
    <label id="baris-nama" hidden>Nama lengkap <input id="masuk-nama" placeholder="Nama Anda"></label>
    <div class="baris-fleks">
      <button onclick="toko.masuk()">Masuk</button>
      <button class="ghost" onclick="toko.daftar()">Daftar</button>
      <button class="ghost" onclick="toko.tutup('modal-masuk')">Tutup</button>
    </div>
    <p class="ket">Akun demo: <code>siti@contoh.test</code> / <code>rahasia123</code></p>
  </div>
</div>

<!-- Panel keranjang -->
<div class="modal" id="modal-keranjang">
  <div class="kartu lebar">
    <h2>Keranjang</h2>
    <div id="isi-keranjang"></div>
    <div id="blok-checkout" hidden>
      <hr>
      <label>Alamat <select id="pilih-alamat"></select></label>
      <label>Kurir <select id="pilih-kurir">
        <option value="reguler">Reguler (Rp15.000)</option>
        <option value="kilat">Kilat (Rp25.000)</option>
        <option value="instan">Instan (Rp40.000)</option>
      </select></label>
      <label>Metode bayar <select id="pilih-metode">
        <option value="virtual_account">Virtual Account</option>
        <option value="transfer_bank">Transfer Bank</option>
        <option value="e_wallet">E-Wallet</option>
        <option value="qris">QRIS</option>
        <option value="cod">COD</option>
      </select></label>
      <div class="baris-fleks">
        <button onclick="toko.checkout()">Checkout</button>
        <button class="ghost" onclick="toko.tutup('modal-keranjang')">Tutup</button>
      </div>
    </div>
    <div id="hasil-checkout"></div>
  </div>
</div>
"""
    js = r"""
const toko = {
  token: localStorage.getItem('token') || null,
  pengguna: JSON.parse(localStorage.getItem('pengguna') || 'null'),
  produk: [], kategori: [], keranjang: null, alamat: [],
  async api(path, opsi = {}) {
    const h = { 'Content-Type': 'application/json', ...(opsi.headers || {}) };
    if (this.token) h['Authorization'] = 'Bearer ' + this.token;
    const r = await fetch('/api/' + path, { ...opsi, headers: h });
    let body = null;
    try { body = await r.json(); } catch (e) { body = {}; }
    if (!r.ok) throw new Error((body.error && body.error.pesan) || ('HTTP ' + r.status));
    return body.data;
  },
  async muat() {
    try {
      const ringkas = await fetch('/api/ringkasan/toko').then(r => r.json());
      this.produk = ringkas.data.produk || [];
      this.kategori = ringkas.data.kategori || [];
      const sel = document.getElementById('filter-kategori');
      sel.innerHTML = '<option value="">Semua kategori</option>' +
        this.kategori.map(k => `<option value="${k.id}">${k.nama}</option>`).join('');
      this.render();
    } catch (e) { toast('Gagal memuat katalog: ' + e.message, 'gagal'); }
    this.cekStatus();
    if (this.token) { this.muatKeranjang(); this.muatPesanan(); this.muatAlamat(); }
    this.renderMasuk();
  },
  async cekStatus() {
    try {
      const r = await fetch('/api/status').then(x => x.json());
      const el = document.getElementById('status-layanan');
      el.innerHTML = Object.entries(r.data.layanan)
        .map(([n, v]) => `<span class="pil ${v.status === 'ok' ? 'hijau' : 'merah'}">${n}</span>`).join('');
    } catch (e) { /* diamkan */ }
  },
  saring() {
    this.render();
  },
  render() {
    const q = (document.getElementById('cari').value || '').toLowerCase();
    const kat = document.getElementById('filter-kategori').value;
    const data = this.produk.filter(p =>
      (!kat || String(p.kategori_id) === kat) &&
      (!q || p.nama.toLowerCase().includes(q) || p.sku.toLowerCase().includes(q)));
    const el = document.getElementById('daftar-produk');
    if (!data.length) { el.innerHTML = '<p class="ket">Tidak ada produk yang cocok.</p>'; return; }
    el.innerHTML = data.map(p => `
      <article class="produk">
        <div class="ikon">📦</div>
        <h3>${p.nama}</h3>
        <p class="ket">${p.kategori || 'Tanpa kategori'} · ${p.sku}</p>
        <p class="harga">${rupiah(p.harga)}</p>
        <p class="ket">Stok tersedia: ${p.stok_tersedia}</p>
        <button ${p.stok_tersedia < 1 ? 'disabled' : ''} onclick="toko.tambah(${p.id})">
          ${p.stok_tersedia < 1 ? 'Habis' : 'Tambah ke keranjang'}
        </button>
      </article>`).join('');
  },
  renderMasuk() {
    const el = document.getElementById('tombol-masuk');
    if (this.token && this.pengguna) {
      el.textContent = this.pengguna.nama + ' (keluar)';
      el.onclick = () => { localStorage.clear(); location.reload(); };
    } else {
      el.textContent = 'Masuk';
      el.onclick = (e) => { e.preventDefault(); buka('modal-masuk'); };
    }
    document.getElementById('baris-nama').hidden = true;
    document.getElementById('judul-masuk').textContent = 'Masuk atau daftar';
  },
  async masuk() {
    try {
      const data = await this.api('pelanggan/auth/login', {
        method: 'POST',
        body: JSON.stringify({
          email: document.getElementById('masuk-email').value,
          kata_sandi: document.getElementById('masuk-sandi').value,
        }),
      });
      this.simpanSesi(data);
      toast('Selamat datang, ' + data.pengguna.nama);
    } catch (e) { toast(e.message, 'gagal'); }
  },
  async daftar() {
    try {
      const data = await this.api('pelanggan/auth/registrasi', {
        method: 'POST',
        body: JSON.stringify({
          email: document.getElementById('masuk-email').value,
          kata_sandi: document.getElementById('masuk-sandi').value,
          nama: document.getElementById('masuk-nama').value || 'Pelanggan Baru',
        }),
      });
      this.simpanSesi(data);
      toast('Pendaftaran berhasil');
    } catch (e) { toast(e.message, 'gagal'); }
  },
  simpanSesi(data) {
    this.token = data.token; this.pengguna = data.pengguna;
    localStorage.setItem('token', data.token);
    localStorage.setItem('pengguna', JSON.stringify(data.pengguna));
    tutup('modal-masuk'); this.muat();
  },
  async tambah(id) {
    if (!this.token) { buka('modal-masuk'); return; }
    try { this.keranjang = await this.api('order/keranjang', { method: 'POST', body: JSON.stringify({ produk_id: id, qty: 1 }) });
      this.renderKeranjang(); toast('Ditambahkan ke keranjang'); }
    catch (e) { toast(e.message, 'gagal'); }
  },
  async muatKeranjang() {
    try { this.keranjang = await this.api('order/keranjang'); this.renderKeranjang(); } catch (e) { /* belum login */ }
  },
  async ubahQty(pid, qty) {
    try { this.keranjang = await this.api('order/keranjang/' + pid, { method: 'PUT', body: JSON.stringify({ qty }) });
      this.renderKeranjang(); } catch (e) { toast(e.message, 'gagal'); }
  },
  renderKeranjang() {
    const k = this.keranjang || { items: [], total: 0 };
    document.getElementById('badge-keranjang').textContent = k.items.reduce((a, i) => a + i.qty, 0);
    const el = document.getElementById('isi-keranjang');
    if (!k.items.length) {
      el.innerHTML = '<p class="ket">Keranjang kosong.</p>';
      document.getElementById('blok-checkout').hidden = true;
      return;
    }
    document.getElementById('blok-checkout').hidden = false;
    el.innerHTML = `<table><thead><tr><th>Produk</th><th>Harga</th><th>Qty</th><th>Subtotal</th><th></th></tr></thead>
      <tbody>${k.items.map(i => `<tr>
        <td>${i.nama_produk}</td><td>${rupiah(i.harga_satuan)}</td>
        <td><input type="number" min="0" value="${i.qty}" style="width:70px"
             onchange="toko.ubahQty(${i.produk_id}, this.value)"></td>
        <td>${rupiah(i.subtotal)}</td>
        <td><button class="ghost" onclick="toko.ubahQty(${i.produk_id}, 0)">hapus</button></td>
      </tr>`).join('')}</tbody>
      <tfoot><tr><th colspan="3">Total</th><th colspan="2">${rupiah(k.total)}</th></tr></tfoot></table>`;
  },
  async muatAlamat() {
    try {
      this.alamat = await this.api('pelanggan/alamat');
      document.getElementById('pilih-alamat').innerHTML =
        this.alamat.map(a => `<option value="${a.id}">${a.label} - ${a.jalan}, ${a.kota}${a.utama ? ' (utama)' : ''}</option>`).join('')
        || '<option value="">Belum ada alamat</option>';
    } catch (e) { /* abaikan */ }
  },
  async checkout() {
    const alamat = document.getElementById('pilih-alamat').value;
    try {
      const hasil = await this.api('order/checkout', {
        method: 'POST',
        body: JSON.stringify({
          alamat_id: alamat ? Number(alamat) : null,
          kurir: document.getElementById('pilih-kurir').value,
          metode: document.getElementById('pilih-metode').value,
        }),
      });
      const bayar = hasil.pembayaran;
      document.getElementById('hasil-checkout').innerHTML = `
        <hr><h3>Pesanan ${hasil.pesanan.nomor} dibuat</h3>
        <p>Status: <b>${hasil.pesanan.status}</b> · Total <b>${rupiah(hasil.pesanan.total)}</b></p>
        ${bayar ? `<p>Tagihan: <code>${bayar.referensi}</code> - ${bayar.instruksi}</p>
        <p class="ket">Simulasi pembayaran dilakukan dari <a href="/admin">dashboard admin</a> (status penyelesaian:
        <span id="status-bayar">${bayar.status}</span>).</p>` : '<p class="ket">Integrasi pembayaran nonaktif pada tahap ini.</p>'}
        <div class="baris-fleks"><button class="ghost" onclick="toko.muat();toko.muatKeranjang()">Segarkan</button></div>`;
      this.muatKeranjang(); this.muatPesanan(); this.muat();
    } catch (e) { toast('Checkout gagal: ' + e.message, 'gagal'); }
  },
  async muatPesanan() {
    try {
      const data = await this.api('order/pesanan');
      const el = document.getElementById('daftar-pesanan');
      if (!data.length) { el.innerHTML = '<p class="ket">Belum ada pesanan.</p>'; return; }
      el.innerHTML = `<table><thead><tr><th>Nomor</th><th>Tanggal</th><th>Status</th><th>Total</th><th>Item</th></tr></thead>
        <tbody>${data.map(p => `<tr><td>${p.nomor}</td><td>${(p.dibuat_at || '').replace('T', ' ').slice(0, 16)}</td>
        <td><span class="pil">${p.status}</span></td><td>${rupiah(p.total)}</td>
        <td>${p.items.map(i => `${i.nama_produk} ×${i.qty}`).join(', ')}</td></tr>`).join('')}</tbody></table>`;
    } catch (e) { /* belum login */ }
  },
  tutup(id) { tutup(id); },
};
document.getElementById('tombol-keranjang').onclick = (e) => {
  e.preventDefault();
  if (!toko.token) { buka('modal-masuk'); return; }
  buka('modal-keranjang'); toko.muatKeranjang();
};
const asli = toko.muat.bind(toko);
toko.muat = async function () { await asli(); };
toko.muat();
setInterval(() => { if (toko.token) { toko.muatPesanan(); } }, 8000);
"""
    return _bungkus("Toko Online - Mikroservis", isi, js)


def halaman_admin():
    isi = """
<header>
  <div class="merek">⚙️ <span>Dashboard Admin</span> <small>mikroservis</small></div>
  <nav>
    <a href="/">Toko</a>
    <a href="/admin" class="aktif">Admin</a>
    <a href="#" id="tombol-masuk">Masuk</a>
  </nav>
</header>

<main>
  <section class="hero kecil">
    <div><h1>Operasional toko</h1><p>Pesanan, pembayaran, stok, dan laporan dalam satu layar.</p></div>
    <div id="status-layanan" class="status"></div>
  </section>

  <section class="kartu-angka" id="kartu-angka"></section>

  <section class="panel">
    <h2>Pesanan terbaru</h2>
    <div class="baris-fleks">
      <select id="filter-status" onchange="admin.muatPesanan()">
        <option value="">Semua status</option>
        <option>MENUNGGU_PEMBAYARAN</option><option>DIBAYAR</option>
        <option>DIKEMAS</option><option>DIKIRIM</option>
        <option>SELESAI</option><option>DIBATALKAN</option>
      </select>
      <button class="ghost" onclick="admin.muat()">Muat ulang</button>
    </div>
    <div id="tabel-pesanan" class="tabel-bungkus"></div>
  </section>

  <section class="panel">
    <h2>Pembayaran</h2>
    <div id="tabel-pembayaran" class="tabel-bungkus"></div>
  </section>

  <section class="panel">
    <h2>Produk & stok</h2>
    <div class="baris-fleks">
      <input id="produk-nama" placeholder="Nama produk baru">
      <input id="produk-harga" type="number" placeholder="Harga" style="width:130px">
      <input id="produk-stok" type="number" placeholder="Stok" style="width:110px">
      <select id="produk-kategori"></select>
      <button onclick="admin.tambahProduk()">Tambah</button>
    </div>
    <div id="tabel-produk" class="tabel-bungkus"></div>
  </section>

  <section class="panel">
    <h2>Laporan</h2>
    <div class="baris-fleks">
      <input id="lapor-dari" type="date"> <input id="lapor-sampai" type="date">
      <button onclick="admin.muatLaporan()">Terapkan</button>
      <button class="ghost" onclick="admin.unduhCsv()">Unduh CSV</button>
    </div>
    <div id="isi-laporan"></div>
  </section>
</main>

<div class="modal" id="modal-masuk">
  <div class="kartu">
    <h2>Masuk sebagai admin</h2>
    <label>Email <input id="masuk-email" type="email" value="admin@contoh.test"></label>
    <label>Kata sandi <input id="masuk-sandi" type="password" value="admin12345"></label>
    <div class="baris-fleks"><button onclick="admin.masuk()">Masuk</button>
      <button class="ghost" onclick="tutup('modal-masuk')">Tutup</button></div>
    <p class="ket">Akun demo dibuat oleh <code>python seed/seed_data.py</code>.</p>
  </div>
</div>

<div class="modal" id="modal-detail">
  <div class="kartu lebar"><h2 id="judul-detail">Detail</h2><div id="isi-detail"></div>
    <button class="ghost" onclick="tutup('modal-detail')">Tutup</button></div>
</div>
"""
    js = r"""
const admin = {
  token: localStorage.getItem('token_admin') || null,
  data: null,
  pesanan: [],
  async api(path, opsi = {}) {
    const h = { 'Content-Type': 'application/json', ...(opsi.headers || {}) };
    if (this.token) h['Authorization'] = 'Bearer ' + this.token;
    const r = await fetch('/api/' + path, { ...opsi, headers: h });
    let body = null; try { body = await r.json(); } catch (e) { body = {}; }
    if (!r.ok) throw new Error((body.error && body.error.pesan) || ('HTTP ' + r.status));
    return body.data;
  },
  async masuk() {
    try {
      const data = await this.api('pelanggan/auth/login', {
        method: 'POST', body: JSON.stringify({
          email: document.getElementById('masuk-email').value,
          kata_sandi: document.getElementById('masuk-sandi').value }),
      });
      if (data.pengguna.peran !== 'admin') { toast('Akun ini bukan admin', 'gagal'); return; }
      this.token = data.token; localStorage.setItem('token_admin', data.token);
      tutup('modal-masuk'); this.muat();
    } catch (e) { toast(e.message, 'gagal'); }
  },
  async muat() {
    if (!this.token) { buka('modal-masuk'); return; }
    document.getElementById('tombol-masuk').textContent = 'Keluar';
    document.getElementById('tombol-masuk').onclick = (e) => {
      e.preventDefault(); localStorage.removeItem('token_admin'); location.reload();
    };
    try {
      this.data = await this.api('ringkasan/admin');
      this.renderAngka(); this.renderProduk(); this.muatPesanan(); this.muatPembayaran(); this.muatLaporan();
    } catch (e) { toast(e.message, 'gagal'); }
    try {
      const r = await fetch('/api/status').then(x => x.json());
      document.getElementById('status-layanan').innerHTML = Object.entries(r.data.layanan)
        .map(([n, v]) => `<span class="pil ${v.status === 'ok' ? 'hijau' : 'merah'}">${n}</span>`).join('');
    } catch (e) { /* diamkan */ }
  },
  renderAngka() {
    const d = this.data || {};
    const pesanan = d.statistik_pesanan || {};
    const bayar = d.statistik_pembayaran || {};
    const kartu = [
      ['Pesanan', pesanan.jumlah_pesanan || 0],
      ['Nilai pesanan', rupiah(pesanan.nilai_transaksi || 0)],
      ['Transaksi berhasil', (bayar.per_status || {}).BERHASIL || 0],
      ['Nominal diterima', rupiah(bayar.nominal_berhasil || 0)],
      ['Pelanggan', (d.statistik_pelanggan || {}).pelanggan || 0],
      ['Stok kritis (≤5)', (d.stok_kritis || []).length],
    ];
    document.getElementById('kartu-angka').innerHTML = kartu.map(([l, v]) =>
      `<div class="angka"><small>${l}</small><b>${v}</b></div>`).join('');
  },
  async muatPesanan() {
    try {
      const status = document.getElementById('filter-status').value;
      const data = await this.api('order/pesanan-admin?batas=30' + (status ? '&status=' + status : ''));
      this.pesanan = data;
      this.renderPesanan(data);
    } catch (e) {
      document.getElementById('tabel-pesanan').innerHTML =
        `<p class="ket">Gagal memuat pesanan: ${e.message}</p>`;
    }
  },
  renderPesanan(data) {
    const el = document.getElementById('tabel-pesanan');
    if (!data || !data.length) { el.innerHTML = '<p class="ket">Belum ada pesanan.</p>'; return; }
    el.innerHTML = `<table><thead><tr><th>Nomor</th><th>Pelanggan</th><th>Status</th><th>Total</th><th>Aksi</th></tr></thead>
      <tbody>${data.map(p => `<tr><td>${p.nomor}<br><span class="ket">${(p.dibuat_at || '').replace('T', ' ').slice(0, 16)}</span></td>
      <td>#${p.pelanggan_id}</td><td><span class="pil">${p.status}</span></td>
      <td>${rupiah(p.total)}</td><td>
        <button class="ghost" onclick="admin.detail('${p.id}')">detail</button>
        ${['DIBAYAR', 'DIKEMAS', 'DIKIRIM'].includes(p.status)
          ? `<button class="ghost" onclick="admin.majukan('${p.id}','${p.status}')">majukan status</button>` : ''}
      </td></tr>`).join('')}</tbody></table>`;
  },
  async majukan(id, status) {
    const urutan = { DIBAYAR: 'DIKEMAS', DIKEMAS: 'DIKIRIM', DIKIRIM: 'SELESAI' };
    try {
      await this.api('order/pesanan/' + id + '/status', { method: 'POST',
        body: JSON.stringify({ status: urutan[status] }) });
      toast('Status menjadi ' + urutan[status]); this.muatPesanan();
    } catch (e) { toast(e.message, 'gagal'); }
  },
  async detail(id) {
    const p = (this.pesanan || []).find(x => x.id === id);
    if (p) { notifikasiDetail(p); return; }
    toast('Detail tidak tersedia, muat ulang daftar', 'gagal');
  },
  async muatPembayaran() {
    try {
      const data = await this.api('pembayaran/pembayaran?batas=30');
      const el = document.getElementById('tabel-pembayaran');
      if (!data.length) { el.innerHTML = '<p class="ket">Belum ada transaksi.</p>'; return; }
      el.innerHTML = `<table><thead><tr><th>Pesanan</th><th>Metode</th><th>Jumlah</th><th>Status</th>
        <th>Referensi</th><th>Simulasi</th></tr></thead>
        <tbody>${data.map(t => `<tr><td>${t.nomor_pesanan}</td><td>${t.metode}</td>
        <td>${rupiah(t.jumlah)}</td><td><span class="pil">${t.status}</span></td><td><code>${t.referensi}</code></td>
        <td>${t.status === 'MENUNGGU' ? `
          <button class="ghost" onclick="admin.simulasi('${t.id}','berhasil')">berhasil</button>
          <button class="ghost" onclick="admin.simulasi('${t.id}','gagal')">gagal</button>` : '-'}</td>
        </tr>`).join('')}</tbody></table>`;
    } catch (e) { /* diamkan */ }
  },
  async simulasi(id, hasil) {
    try {
      await this.api('pembayaran/pembayaran/' + id + '/simulasi',
        { method: 'POST', body: JSON.stringify({ hasil }) });
      toast('Simulasi ' + hasil + ' terkirim'); this.muat();
    } catch (e) { toast(e.message, 'gagal'); }
  },
  renderProduk() {
    const el = document.getElementById('tabel-produk');
    const data = (this.data || {}).produk || [];
    const sel = document.getElementById('produk-kategori');
    if (sel) {
      sel.innerHTML = ((this.data || {}).kategori || []).map(k => `<option value="${k.id}">${k.nama}</option>`).join('')
        || '<option value="">(tanpa kategori)</option>';
    }
    if (!data.length) { el.innerHTML = '<p class="ket">Belum ada produk.</p>'; return; }
    el.innerHTML = `<table><thead><tr><th>Nama</th><th>SKU</th><th>Harga</th><th>Stok</th>
      <th>Tersedia</th><th>Tambah stok</th></tr></thead>
      <tbody>${data.map(p => `<tr><td>${p.nama}</td><td>${p.sku}</td><td>${rupiah(p.harga)}</td>
      <td>${p.stok}</td><td>${p.stok_tersedia}</td>
      <td><input type="number" id="stok-${p.id}" placeholder="+/-" style="width:80px">
        <button class="ghost" onclick="admin.tambahStok(${p.id})">simpan</button></td></tr>`).join('')}</tbody></table>`;
  },
  async tambahStok(id) {
    const nilai = document.getElementById('stok-' + id).value;
    if (!nilai) return;
    try {
      await this.api('katalog/produk/' + id + '/stok', { method: 'POST',
        body: JSON.stringify({ tambah: Number(nilai) }) });
      toast('Stok diperbarui'); this.muat();
    } catch (e) { toast(e.message, 'gagal'); }
  },
  async tambahProduk() {
    try {
      const kategori = document.getElementById('produk-kategori').value;
      await this.api('katalog/produk', { method: 'POST', body: JSON.stringify({
        nama: document.getElementById('produk-nama').value,
        harga: Number(document.getElementById('produk-harga').value || 0),
        stok: Number(document.getElementById('produk-stok').value || 0),
        kategori_id: kategori ? Number(kategori) : null,
      }) });
      toast('Produk ditambahkan'); this.muat();
    } catch (e) { toast(e.message, 'gagal'); }
  },
  async muatLaporan() {
    const dari = document.getElementById('lapor-dari').value;
    const sampai = document.getElementById('lapor-sampai').value;
    const q = new URLSearchParams();
    if (dari) q.set('dari', dari);
    if (sampai) q.set('sampai', sampai);
    try {
      const l = await this.api('pembayaran/laporan/ringkasan?' + q.toString());
      document.getElementById('isi-laporan').innerHTML = `
        <p>Transaksi: <b>${l.jumlah_transaksi}</b> · Nominal berhasil: <b>${rupiah(l.nominal_berhasil)}</b>
           · Tingkat keberhasilan: <b>${l.tingkat_keberhasilan}%</b></p>
        <table><thead><tr><th>Metode</th><th>Transaksi</th><th>Nominal</th></tr></thead>
        <tbody>${(l.per_metode || []).map(m => `<tr><td>${m.metode}</td><td>${m.transaksi}</td>
        <td>${rupiah(m.nominal)}</td></tr>`).join('')}</tbody></table>
        <table><thead><tr><th>Tanggal</th><th>Transaksi</th><th>Nominal</th></tr></thead>
        <tbody>${(l.harian || []).map(h => `<tr><td>${h.tanggal}</td><td>${h.transaksi}</td>
        <td>${rupiah(h.nominal)}</td></tr>`).join('')}</tbody></table>`;
    } catch (e) { /* diamkan */ }
  },
  unduhCsv() {
    const dari = document.getElementById('lapor-dari').value;
    const sampai = document.getElementById('lapor-sampai').value;
    fetch('/api/pembayaran/laporan/transaksi.csv?dari=' + dari + '&sampai=' + sampai,
      { headers: { 'Authorization': 'Bearer ' + this.token } })
      .then(r => r.blob()).then(b => {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(b); a.download = 'laporan-transaksi.csv'; a.click();
      });
  },
};
function notifikasiDetail(p) {
  document.getElementById('judul-detail').textContent = 'Pesanan ' + p.nomor;
  document.getElementById('isi-detail').innerHTML = `
    <p>Status: <b>${p.status}</b> · Total: <b>${rupiah(p.total)}</b></p>
    <p>Penerima: ${p.alamat ? p.alamat.penerima + ' - ' + p.alamat.jalan + ', ' + p.alamat.kota : '-'}</p>
    <table><thead><tr><th>Produk</th><th>Qty</th><th>Harga</th><th>Subtotal</th></tr></thead>
    <tbody>${(p.items || []).map(i => `<tr><td>${i.nama_produk}</td><td>${i.qty}</td>
      <td>${rupiah(i.harga)}</td><td>${rupiah(i.subtotal)}</td></tr>`).join('')}</tbody></table>
    <h3>Jejak saga</h3>
    <table><thead><tr><th>Langkah</th><th>Jenis</th><th>Status</th><th>Waktu</th></tr></thead>
    <tbody>${(p.jejak_saga || []).map(j => `<tr><td>${j.langkah}</td><td>${j.jenis}</td>
      <td>${j.status}</td><td>${(j.waktu || '').replace('T', ' ').slice(0, 19)}</td></tr>`).join('')}</tbody></table>`;
  buka('modal-detail');
}
document.getElementById('tombol-masuk').onclick = (e) => { e.preventDefault(); buka('modal-masuk'); };
admin.muat();
"""
    return _bungkus("Dashboard Admin - Toko Online", isi, js)

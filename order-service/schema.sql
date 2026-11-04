CREATE TABLE IF NOT EXISTS keranjang (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pelanggan_id    INTEGER NOT NULL,
    produk_id       INTEGER NOT NULL,
    nama_produk     TEXT NOT NULL,
    harga_satuan    INTEGER NOT NULL,
    qty             INTEGER NOT NULL CHECK (qty > 0),
    ditambahkan_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_keranjang_unik ON keranjang(pelanggan_id, produk_id);

CREATE TABLE IF NOT EXISTS pesanan (
    id              TEXT PRIMARY KEY,
    nomor           TEXT NOT NULL UNIQUE,
    pelanggan_id    INTEGER NOT NULL,
    status          TEXT NOT NULL DEFAULT 'MENUNGGU_PEMBAYARAN',
    subtotal        INTEGER NOT NULL DEFAULT 0,
    ongkir          INTEGER NOT NULL DEFAULT 0,
    total           INTEGER NOT NULL DEFAULT 0,
    kurir           TEXT,
    catatan         TEXT,
    alamat_json     TEXT,
    reservasi_id    TEXT,
    pembayaran_id   TEXT,
    dibuat_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    diperbarui_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    alasan_batal    TEXT
);

CREATE INDEX IF NOT EXISTS idx_pesanan_pelanggan ON pesanan(pelanggan_id);
CREATE INDEX IF NOT EXISTS idx_pesanan_status ON pesanan(status);

CREATE TABLE IF NOT EXISTS pesanan_item (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pesanan_id      TEXT NOT NULL REFERENCES pesanan(id) ON DELETE CASCADE,
    produk_id       INTEGER NOT NULL,
    nama_produk     TEXT NOT NULL,
    harga           INTEGER NOT NULL,
    qty             INTEGER NOT NULL,
    subtotal        INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_item_pesanan ON pesanan_item(pesanan_id);

CREATE TABLE IF NOT EXISTS saga_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pesanan_id      TEXT,
    langkah         TEXT NOT NULL,
    jenis           TEXT NOT NULL,
    status          TEXT NOT NULL,
    pesan           TEXT,
    waktu           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_saga_pesanan ON saga_log(pesanan_id);

CREATE TABLE IF NOT EXISTS kategori (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nama        TEXT NOT NULL UNIQUE,
    deskripsi   TEXT,
    dibuat_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS produk (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sku             TEXT NOT NULL UNIQUE,
    nama            TEXT NOT NULL,
    deskripsi       TEXT,
    kategori_id     INTEGER REFERENCES kategori(id) ON DELETE SET NULL,
    harga           INTEGER NOT NULL CHECK (harga >= 0),
    stok            INTEGER NOT NULL DEFAULT 0 CHECK (stok >= 0),
    stok_reserved   INTEGER NOT NULL DEFAULT 0 CHECK (stok_reserved >= 0),
    aktif           INTEGER NOT NULL DEFAULT 1,
    dibuat_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    diperbarui_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_produk_kategori ON produk(kategori_id);
CREATE INDEX IF NOT EXISTS idx_produk_aktif ON produk(aktif);

CREATE TABLE IF NOT EXISTS reservasi (
    id              TEXT PRIMARY KEY,
    order_ref       TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'AKTIF',
    total           INTEGER NOT NULL DEFAULT 0,
    dibuat_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    kedaluwarsa_at  TEXT NOT NULL,
    ditutup_at      TEXT
);

CREATE INDEX IF NOT EXISTS idx_reservasi_order ON reservasi(order_ref);
CREATE INDEX IF NOT EXISTS idx_reservasi_status ON reservasi(status);

CREATE TABLE IF NOT EXISTS reservasi_item (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    reservasi_id    TEXT NOT NULL REFERENCES reservasi(id) ON DELETE CASCADE,
    produk_id       INTEGER NOT NULL REFERENCES produk(id),
    nama_produk     TEXT NOT NULL,
    qty             INTEGER NOT NULL CHECK (qty > 0),
    harga           INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_item_reservasi ON reservasi_item(reservasi_id);

CREATE TABLE IF NOT EXISTS pembayaran (
    id              TEXT PRIMARY KEY,
    pesanan_id      TEXT NOT NULL,
    nomor_pesanan   TEXT NOT NULL,
    pelanggan_id    INTEGER NOT NULL,
    metode          TEXT NOT NULL DEFAULT 'virtual_account',
    jumlah          INTEGER NOT NULL CHECK (jumlah > 0),
    status          TEXT NOT NULL DEFAULT 'MENUNGGU',
    referensi       TEXT,
    nama_pelanggan  TEXT,
    keterangan      TEXT,
    dibuat_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    diperbarui_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    kedaluwarsa_at  TEXT NOT NULL,
    dibayar_at      TEXT,
    jumlah_webhook  INTEGER NOT NULL DEFAULT 0
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_pembayaran_pesanan ON pembayaran(pesanan_id);
CREATE INDEX IF NOT EXISTS idx_pembayaran_status ON pembayaran(status);

CREATE TABLE IF NOT EXISTS pembayaran_event (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pembayaran_id   TEXT NOT NULL,
    jenis           TEXT NOT NULL,
    status_lama     TEXT,
    status_baru     TEXT,
    pesan           TEXT,
    waktu           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_event_pembayaran ON pembayaran_event(pembayaran_id);

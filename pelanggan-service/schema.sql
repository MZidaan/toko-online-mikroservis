CREATE TABLE IF NOT EXISTS pelanggan (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    email           TEXT NOT NULL,
    nama            TEXT NOT NULL,
    kata_sandi_hash TEXT NOT NULL,
    peran           TEXT NOT NULL DEFAULT 'pelanggan' CHECK (peran IN ('pelanggan','admin')),
    telepon         TEXT,
    aktif           INTEGER NOT NULL DEFAULT 1,
    dibuat_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    diperbarui_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_pelanggan_email ON pelanggan(lower(email));

CREATE TABLE IF NOT EXISTS alamat (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pelanggan_id    INTEGER NOT NULL REFERENCES pelanggan(id) ON DELETE CASCADE,
    label           TEXT NOT NULL DEFAULT 'Rumah',
    penerima        TEXT NOT NULL,
    telepon         TEXT NOT NULL,
    jalan           TEXT NOT NULL,
    kelurahan       TEXT,
    kecamatan       TEXT,
    kota            TEXT NOT NULL,
    provinsi        TEXT NOT NULL,
    kode_pos        TEXT NOT NULL,
    utama           INTEGER NOT NULL DEFAULT 0,
    dibuat_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_alamat_pelanggan ON alamat(pelanggan_id);

CREATE TABLE IF NOT EXISTS audit_login (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pelanggan_id    INTEGER,
    email           TEXT NOT NULL,
    berhasil        INTEGER NOT NULL,
    alasan          TEXT,
    waktu           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

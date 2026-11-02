"""Akses SQLite: satu berkas per layanan, koneksi per request, helper query."""
import os
import sqlite3
import threading
from contextlib import contextmanager

from flask import g

from . import config

_default = {"nama": None}
_lock = threading.Lock()


def set_default(nama):
    _default["nama"] = nama


def default():
    return _default["nama"]


def path_db(nama):
    os.makedirs(config.DATA_DIR, exist_ok=True)
    return os.path.join(config.DATA_DIR, f"{nama}.db")


def koneksi(nama=None):
    nama = nama or default()
    if not nama:
        raise RuntimeError("nama basis data belum ditentukan")
    conn = sqlite3.connect(path_db(nama), timeout=20, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=20000")
    return conn


def init_db(nama, skema):
    conn = sqlite3.connect(path_db(nama), timeout=20)
    conn.executescript(skema)
    conn.commit()
    conn.close()


def db(nama=None):
    """Koneksi milik request aktif (ditutup otomatis di teardown)."""
    if not hasattr(g, "_db"):
        g._db = koneksi(nama)
    return g._db


def close_db(exc=None):
    conn = getattr(g, "_db", None)
    if conn is not None:
        try:
            conn.close()
        finally:
            g._db = None


@contextmanager
def transaksi():
    """Kunci tulis eksklusif agar reserve/stok tetap atomik."""
    conn = db()
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def q(sql, params=()):
    return [dict(r) for r in db().execute(sql, params).fetchall()]


def q1(sql, params=()):
    row = db().execute(sql, params).fetchone()
    return dict(row) if row else None


def skalar(sql, params=(), bawaan=None):
    row = db().execute(sql, params).fetchone()
    if row is None or row[0] is None:
        return bawaan
    return row[0]


def eksekusi(sql, params=()):
    cur = db().execute(sql, params)
    return cur


def sisip(sql, params=()):
    return db().execute(sql, params).lastrowid

"""Pabrik aplikasi Flask: request-id, log akses, handler error, /health."""
import logging
import time
import uuid

from flask import Flask, g, jsonify, request

from . import db, responses


def create_app(nama, db_name=None, skema=None):
    app = Flask(nama)
    app.json.ensure_ascii = False
    app.json.sort_keys = False
    app.url_map.strict_slashes = False

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    app.logger.setLevel(logging.INFO)

    responses.daftarkan_handler(app)

    @app.before_request
    def _mulai():
        g.request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:12]
        g.t0 = time.perf_counter()

    @app.after_request
    def _selesai(resp):
        resp.headers["X-Request-Id"] = getattr(g, "request_id", "-")
        resp.headers["X-Layanan"] = nama
        if request.path != "/health":
            durasi = (time.perf_counter() - getattr(g, "t0", time.perf_counter())) * 1000
            app.logger.info("%s %s -> %s (%.0f ms)", request.method, request.full_path.rstrip("?"),
                            resp.status_code, durasi)
        return resp

    @app.teardown_appcontext
    def _tutup(exc):
        db.close_db(exc)

    if db_name:
        db.set_default(db_name)
        if skema:
            db.init_db(db_name, skema)

    @app.get("/health")
    def _health():
        return jsonify({"status": "ok", "layanan": nama, "waktu": responses.waktu_iso()})

    return app

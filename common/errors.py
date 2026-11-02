"""Kesalahan domain yang dipetakan menjadi respons JSON konsisten."""


class ApiError(Exception):
    """Kesalahan yang disengaja dan aman ditampilkan ke klien."""

    def __init__(self, status=400, kode="KESALAHAN", pesan="Permintaan tidak valid", detail=None):
        super().__init__(pesan)
        self.status = status
        self.kode = kode
        self.pesan = pesan
        self.detail = detail


def tidak_ditemukan(apa="Data"):
    return ApiError(404, "TIDAK_DITEMUKAN", f"{apa} tidak ditemukan")


def tidak_valid(pesan, detail=None):
    return ApiError(422, "VALIDASI_GAGAL", pesan, detail)


def terlarang(pesan="Anda tidak berhak mengakses sumber daya ini"):
    return ApiError(403, "TERLARANG", pesan)


def bentrok(pesan, detail=None):
    return ApiError(409, "BENTROK", pesan, detail)

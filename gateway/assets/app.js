function rupiah(n) {
  return 'Rp' + Number(n || 0).toLocaleString('id-ID');
}
function buka(id) { document.getElementById(id).classList.add('tampil'); }
function tutup(id) { document.getElementById(id).classList.remove('tampil'); }
let _timerToast = null;
function toast(pesan, jenis = 'sukses') {
  const el = document.getElementById('toast');
  el.textContent = pesan;
  el.className = 'toast tampil' + (jenis === 'gagal' ? ' gagal' : '');
  clearTimeout(_timerToast);
  _timerToast = setTimeout(() => { el.className = 'toast'; }, 3200);
}
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') document.querySelectorAll('.modal.tampil').forEach(m => m.classList.remove('tampil'));
});
document.addEventListener('click', (e) => {
  if (e.target.classList && e.target.classList.contains('modal')) e.target.classList.remove('tampil');
});

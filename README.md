# Media Monitoring (Live)

Dashboard monitoring media untuk Bank Artha Graha Internasional (BAGI)
beserta kompetitor: Sea Bank, Allo Bank, Bank Saqu, IBK Bank.

Buka di: **https://habibtjiu.github.io/media-monitoring/**

## Data

Data **live dari RSS gratis**:

- Google News RSS (9 query: Bank Artha Graha, Artha Graha Peduli, SeaBank,
  Allo Bank, Bank Saqu, IBK Bank, bank digital, penipuan bank, literasi keuangan)
- ANTARA (`/rss/terkini`, `/rss/ekonomi`)
- CNBC Indonesia (`/rss`)

Kolektor (`collector/collect.py`) jalan tiap 15 menit lewat GitHub Actions
(`.github/workflows/collect.yml`); kalau ada mention baru, `data.json`
di-commit dan situs di-deploy ulang otomatis. Login demo: kredensial apa pun
masuk (tombol "Masuk sebagai demo").

## Yang perlu diketahui

- **Angka mention lebih kecil daripada tools monitoring berbayar.** RSS gratis
  hanya menangkap portal berita besar — tanpa media sosial (X/Instagram) dan
  tanpa semua portal. Jadi totalnya bukan pembanding langsung dengan angka
  tools berbayar.
- **Engagement tampil "—".** RSS tidak membawa angka interaksi (like/share/
  komentar), jadi tidak ada datanya — bukan error.
- **Sentimen/emosi berbasis kata kunci Bahasa Indonesia**, bukan NLP sungguhan.
- **Spam judi difilter.** Query "SeaBank" sempat menarik halaman spam judi
  (situs yang dibajak); judul/sumber seperti itu dibuang oleh kolektor.
- **Tokoh dikenali dari daftar nama yang dikenal** (mis. Tomy Winata) plus pola
  "kata/ujar X" di judul — sisanya kosong, dan itu jujur: RSS tidak membawa
  nama tokoh.

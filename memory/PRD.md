# PRD — Kabar Buruk

## Original Problem Statement
"Build a web app: I want to create a website about bad news politics in Indonesia"
User choices: portal berita skandal/kontroversi politik Indonesia + arsip/tracker skandal + statistik peringkat dunia (ekonomi, pendidikan, kesehatan, IQ rata-rata, dll); admin login untuk mengelola konten; pencarian & filter kategori; komentar pembaca; tema TERANG seperti portal berita umum; Bahasa Indonesia.

## User Personas
- Pembaca publik: membaca liputan investigasi, memfilter kategori, bereaksi (Marah/Kecewa/Waspada), berkomentar.
- Redaksi/Admin: login ke dasbor, tulis/sunting/hapus artikel, moderasi komentar, perbarui data peringkat dunia.

## Architecture
- Frontend: React (CRA/craco) + Tailwind + framer-motion + lenis, Bahasa Indonesia UI. Pages: Home (/), ArticleDetail (/artikel/:slug), Login (/masuk), Admin (/admin).
- Backend: FastAPI + Motor (async MongoDB), JWT httpOnly-cookie auth (access 15m / refresh 7d), brute-force lockout (5 attempts → 15 min), bcrypt hashing.
- DB: MongoDB collections — users, articles, comments, scandals, rankings, login_attempts.
- Design: /app/design_guidelines.json (broadsheet editorial, Playfair Display + Plus Jakarta Sans + JetBrains Mono, paper #FAF8F5, crimson #DC2626).

## Implemented (2026-11-06)
- Public site: kinetic hero (masked-line reveal, parallax image), editorial marquee, article feed with search + category filters, world-rankings matrix (CPI, kebebasan pers, IQ, pendidikan, kesehatan, PDB, demokrasi), scandal tracker table with status filters.
- Article detail: reactions (Marah/Kecewa/Waspada), reader comments with upvotes.
- Admin: JWT login (admin@kaburburuk.id / admin123), article CRUD, comment moderation, ranking updater.
- Seed: 8 artikel investigasi (Timah 300T, RUU Pilkada, Harun Masiku, kebebasan pers, Tapera, dinasti politik, BTS 4G, IKN), 6 kasus skandal, 7 indeks peringkat.
- Logo SVG "K" mark + favicon.

## Verified
- curl: health, articles (8), rankings (7), scandals (6), login→/me→admin/comments, article create→fetch→react→comment→delete.
- Screenshots: home 1366/768/375, rankings, tracker, article detail, admin login→panel→form→comments tab, comment submission toast.

## Implemented (2026-11-06, ronde 2)
- Halaman detail per indeks peringkat (/peringkat/:key): grafik tren tahunan (recharts LineChart), badge tren (Membaik/Memburuk/Stagnan), deskripsi analisis, tautan sumber eksternal, navigasi antar-indeks. Endpoint GET /api/rankings/{key}.
- 5 kategori indeks baru (total 12): Indeks Kebahagiaan, PDB per Kapita, Indeks Inovasi Global, Pemerintahan Digital (e-Gov), Indeks Kelaparan Global. Seed rankings kini upsert (preserves nilai/rank/catatan hasil edit admin).
- Kategori artikel baru "Media Sosial" + 3 artikel influencer (Indonesia Gelap, Influencer di Istana, Ekonomi Buzzer).
- 4 artikel baru tentang pemerintahan Prabowo: kabinet gemuk, efisiensi anggaran Rp 306 T, Makan Bergizi Gratis (keracunan massal), Danantara. Total 15 artikel. Seed artikel sekarang menambahkan artikel baru tanpa menimpa yang ada.

## Implemented (2026-11-06, ronde 3)
- Kenaikan Peringkat Alert: badge kedip merah "MEMBURUK" (animate-ping) di kartu indeks bertren turun + ringkasan "N indeks memburuk" di judul seksi; bar progres ikut berdenyut.
- Edisi Mingguan: GET /api/edisi-mingguan → halaman HTML print-ready A4 (masthead, 6 liputan terbaru, tabel arsip skandal + rapor peringkat) yang otomatis membuka dialog cetak (Simpan sebagai PDF). Tautan di header ("Edisi Mingguan") dan footer.
- Konten Sosial: rubrik "Konten yang Memberitakan Kabar Buruk" — kurasi 10 kanal/influencer (Geolive, Kok Bisa, Najwa Shihab/Narasi, Tirta, Fahri Hamzah, Pijaru, Fadil Jaidi, Watchdoc, Project Multatuli, Eko Kuntadhi) dengan filter platform (Instagram/YouTube/Facebook/TikTok/X). Admin tab "Kanal Sosial" untuk CRUD kurasi.

## Implemented (2026-11-06, ronde 4)
- Preview konten sosial: tiap kanal kini menampilkan preview thumbnail besar (konten unggulan) + daftar konten pilihan (judul, jenis konten, tanggal, statistik tayangan, tautan). Tipe konten: Video, Reels, Post, Utas, Infografis, Dokumenter, Catatan.
- Admin tab "Kanal Sosial" kini bisa mengelola daftar konten per kanal (tambah/hapus/edit judul, tipe, tanggal, statistik, URL, gambar preview). Konten pertama otomatis jadi preview utama.

## Implemented (2026-11-06, ronde 5)
- Gambar nyata konten: editor konten admin kini menampilkan preview thumbnail langsung, kolom tempel URL gambar asli, dan tombol "Ambil thumbnail asli dari URL YouTube" (mengekstrak ID video dari URL watch/shorts/embed/youtu.be → img.youtube.com/vi/<id>/hqdefault.jpg).

## Implemented (2026-11-06, ronde 6)
- Kurasi konten sosial diperbarui dengan konten nyata terverifikasi web: Najwa Shihab "Presiden Prabowo Menjawab" (youtube.com/watch?v=-WLpXmnBmxo + thumbnail asli), Watchdoc "Sexy Killers" (youtube.com/watch?v=qlB7vg4I-To + thumbnail asli), Pijaru infografis dinasti politik (instagram.com/p/CydhAlcPlaE/), dr. Tirta kritik insentif MBG Rp 1 T, Geolive POLITIK series, Kok Bisa? video korupsi & rupiah klasik. Seed channels kini upsert konten tanpa menimpa edit admin.

## Implemented (2026-11-06, ronde 7)
- Fix thumbnail view: mengganti semua URL CDN Instagram/Facebook/TikTok yang kedaluwarsa/diblokir hotlink dengan URL stabil Unsplash/Pexels; YouTube tetap memakai img.youtube.com/vi/<id>/hqdefault.jpg (resmi & stabil).

## Implemented (2026-11-06, ronde 8)
- Konten pajak transaksi online 0,5% (PMK-37/2025, mulai 1 Nov 2026): ditambahkan ke Tirta (Instagram, tautan instagram.com/p/DfL8N6hyiwD/), Fadil Jaidi (TikTok, tautan tiktok.com/@geraldvincentt/video/7703064497396780306), Fahri Hamzah (X), dan Eko Kuntadhi (Facebook).
- Kanal X baru "Partai Socmed" (@partaisocmed) dengan 2 konten pajak online & Danantara.

## Implemented (2026-11-06, ronde 9)
- Preview konten asli Instagram & TikTok: konten yang URL-nya mengarah ke post/reel/video spesifik kini dirender sebagai embed iframe resmi (instagram.com/.../embed/ dan tiktok.com/player/v1/...), menampilkan thumbnail asli, judul, play button, like/comment count, dan durasi — bukan lagi gambar stock. Konten non-embeddable tetap fallback ke thumbnail gambar.

## Implemented (2026-11-06, ronde 10)
- Identitas akun diperbaiki: Gerald Vincent (@geraldvincentt, TikTok) dipisahkan dari Fadil Jaidi; kanal baru Katadata (@katatadatacoid, Instagram), Partai Socmed (@partaisocmed, X), Tempo (@tempodotco, X).
- Konten trending November 2026: pajak transaksi online 0,5%, klarifikasi Menkeu soal 9 November, reshuffle Kemenkeu (Purbaya → Suahasil).
- Preview cuitan X: karena iframe platform.twitter.com/embed tidak merender di preview environment (blank), konten X kini menampilkan thumbnail kaya dengan overlay branding X (handle, judul, tanggal, statistik) — bukan iframe rusak. Instagram/TikTok tetap memakai embed iframe resmi.

## Implemented (2026-11-06, ronde 11)
- Konten trending bad news politics: 10 item per kanal untuk Gerald Vincent (TikTok), Fahri Hamzah (X), Partai Socmed (X), Tempo (X) — total 40 konten trending November 2026 (pajak online 0,5%, reshuffle Kemenkeu, efisiensi anggaran, MBG, IKN, dinasti politik, Timah, RUU Pilkada, dll).
- Thumbnail diperbaiki: semua memakai URL stabil Unsplash/Pexels; TikTok menampilkan embed video asli, X menampilkan preview thumbnail kaya dengan branding.

## Implemented (2026-11-06, ronde 12)
- Scraper berita otomatis: RSS feed dari Kompas, Detik, Tempo, CNN Indonesia, dan Tribun dipindai setiap 6 jam (cron 0 */6 * * * Asia/Jakarta) untuk keyword politik (korupsi, skandal, Prabowo, Gibran, DPR, KPK, pajak, anggaran, demonstrasi, kontroversi, reshuffle, Danantara, IKN, MBG, kebebasan pers, dinasti politik).
- Artikel yang cocok otomatis masuk database dengan kategori Politik, severity Sedang, penulis nama portal, dan link sumber asli. Duplikat dicek via source_url.
- Endpoint POST /api/cron/scrape-news (protected WEBHOOK_CRON_SECRET) langsung ack 2xx dan enqueue scraping di background.
- Cron config: .emergent/crons.yml dengan timezone Asia/Jakarta.

## Verified (ronde 12)
- curl POST /api/cron/scrape-news → queued, total articles naik dari 15 ke 33 (18 artikel baru terscrape dari portal berita).
- Contoh artikel terscrape: "Jejak Gibran, dari Bisnis Martabak hingga Kursi Wapres" (Kompas).

## Verified (ronde 11) — oleh troubleshoot_agent
- TikTok: Gerald Vincent dengan 10 konten + embed video berfungsi. X: Fahri Hamzah, Partai Socmed, Tempo masing-masing 10 konten dengan preview thumbnail benar. Semua thumbnail termuat, konten trending November 2026 tersedia.

## Verified (ronde 10) — oleh troubleshoot_agent
- Instagram embed berfungsi untuk URL /p/…; TikTok embed berfungsi untuk URL /video/…; X menampilkan preview kaya dengan benar; semua identitas kanal benar; konten trending November 2026 tersedia.

## Verified (ronde 9) — oleh troubleshoot_agent
- Embed URL Instagram/TikTok valid (HTTP 200), FeaturedPreview merender iframe dengan fallback benar, konten "Pajak Transaksi Online" tampil sebagai preview video asli.

## Verified (ronde 8)
- Screenshots: filter Instagram (konten pajak baru tampil sebagai preview utama Tirta), TikTok (konten pajak baru tampil), X (Partai Socmed tampil sebagai kanal baru).

## Verified (ronde 7) — oleh troubleshoot_agent
- Semua filter platform (Semua, Instagram, YouTube, Facebook, TikTok) menampilkan thumbnail dengan benar; 0 URL CDN sosial yang bermasalah tersisa.

## Verified (ronde 6)
- curl: /api/channels menampilkan konten baru.
- Screenshots: preview Najwa menampilkan thumbnail asli wawancara Prabowo, Geolive preview "Prabowo Hemat Rp 750 Triliun" dari thumbnail YouTube asli; href preview mengarah ke video YouTube sebenarnya.

## Verified (ronde 5)
- Screenshots: login admin → tab Kanal Sosial → sunting Geolive → tempel URL YouTube → tombol auto-thumbnail muncul dan mengisi https://img.youtube.com/vi/.../hqdefault.jpg dengan preview gambar asli tampil di editor (URL uji tidak disimpan).

## Verified (ronde 4)
- curl: /api/channels (10 kanal, konten terisi lewat seed upsert non-destruktif).
- Screenshots: kartu kanal dengan preview besar + daftar konten (Geolive 3 konten), filter YouTube, mobile 375px.

## Verified (ronde 3)
- curl: /api/channels (10), /api/edisi-mingguan 200 OK 10.4KB HTML.
- Screenshots: badge MEMBURUK pada Kebebasan Pers & Indeks Demokrasi, grid kanal sosial, filter YouTube (4 kanal), halaman edisi mingguan print-ready, mobile 375px.

## Verified (ronde 2)
- curl: 15 artikel, 12 ranking, detail /rankings/cpi (5 titik tren + source_url).
- Screenshots: grid 12 kartu peringkat, halaman detail CPI dengan grafik, filter Media Sosial (3 artikel), mobile 375px detail peringkat.

## Backlog
- P0: (none — core shipped)
- P1: AI penulis berita (daily scandal digest dari berita terbaru), edisi mingguan PDF/email newsletter.
- P2: halaman skandal per kasus dengan timeline interaktif, pencarian teks penuh, mode gelap, share card OG image per artikel.
- Next tasks: publish/deploy when user ready; collect editorial images per artikel.

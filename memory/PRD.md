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

## Verified (ronde 2)
- curl: 15 artikel, 12 ranking, detail /rankings/cpi (5 titik tren + source_url).
- Screenshots: grid 12 kartu peringkat, halaman detail CPI dengan grafik, filter Media Sosial (3 artikel), mobile 375px detail peringkat.

## Backlog
- P0: (none — core shipped)
- P1: AI penulis berita (daily scandal digest dari berita terbaru), edisi mingguan PDF/email newsletter.
- P2: halaman skandal per kasus dengan timeline interaktif, pencarian teks penuh, mode gelap, share card OG image per artikel.
- Next tasks: publish/deploy when user ready; collect editorial images per artikel.

import asyncio
import logging
import os
import re
import uuid
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import bcrypt
import jwt
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from pymongo import ASCENDING, DESCENDING, IndexModel
from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

JWT_ALGORITHM = "HS256"


def get_jwt_secret() -> str:
    return os.environ["JWT_SECRET"]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(user_id: str, email: str) -> str:
    payload = {"sub": user_id, "email": email, "exp": datetime.now(timezone.utc) + timedelta(minutes=15), "type": "access"}
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    payload = {"sub": user_id, "exp": datetime.now(timezone.utc) + timedelta(days=7), "type": "refresh"}
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return f"{slug}-{uuid.uuid4().hex[:6]}"


INDEXES: dict[str, list[IndexModel]] = {
    "users": [IndexModel([("email", ASCENDING)], name="email", unique=True)],
    "articles": [
        IndexModel([("id", ASCENDING)], name="id", unique=True),
        IndexModel([("slug", ASCENDING)], name="slug", unique=True),
        IndexModel([("published_at", DESCENDING)], name="published_desc"),
    ],
    "comments": [IndexModel([("article_id", ASCENDING)], name="article_id")],
    "login_attempts": [IndexModel([("identifier", ASCENDING)], name="identifier")],
    "scandals": [IndexModel([("id", ASCENDING)], name="id", unique=True)],
    "rankings": [IndexModel([("key", ASCENDING)], name="key", unique=True)],
}


async def ensure_indexes() -> None:
    for collection, models in INDEXES.items():
        for model in models:
            try:
                await db[collection].create_indexes([model])
            except Exception as exc:
                logging.getLogger(__name__).error("ensure_indexes(%s.%s): %s", collection, model.document["name"], exc)


app = FastAPI()
api_router = APIRouter(prefix="/api")


# ---------------- Auth ----------------

class LoginInput(BaseModel):
    email: str
    password: str


async def get_current_user(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


@api_router.post("/auth/login")
async def login(input: LoginInput, request: Request, response: Response):
    email = input.email.lower().strip()
    ip = request.client.host if request.client else "unknown"
    identifier = f"{ip}:{email}"
    attempts = await db.login_attempts.find_one({"identifier": identifier})
    if attempts and attempts.get("count", 0) >= 5:
        locked_until = attempts.get("locked_until")
        if locked_until and datetime.fromisoformat(locked_until) > datetime.now(timezone.utc):
            raise HTTPException(status_code=429, detail="Terlalu banyak percobaan. Coba lagi dalam 15 menit.")
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(input.password, user["password_hash"]):
        count = (attempts.get("count", 0) if attempts else 0) + 1
        locked_until = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat() if count >= 5 else None
        await db.login_attempts.update_one(
            {"identifier": identifier},
            {"$set": {"identifier": identifier, "count": count, "locked_until": locked_until}},
            upsert=True,
        )
        raise HTTPException(status_code=401, detail="Email atau kata sandi salah")
    await db.login_attempts.delete_one({"identifier": identifier})
    access_token = create_access_token(user["id"], email)
    refresh_token = create_refresh_token(user["id"])
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=True, samesite="none", max_age=900, path="/")
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, secure=True, samesite="none", max_age=604800, path="/")
    return {"id": user["id"], "email": email, "name": user.get("name", "Admin"), "role": user.get("role", "admin")}


@api_router.post("/auth/refresh")
async def refresh(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    access_token = create_access_token(payload["sub"], "")
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=True, samesite="none", max_age=900, path="/")
    return {"ok": True}


@api_router.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"ok": True}


@api_router.get("/auth/me")
async def me(user=Depends(get_current_user)):
    return user


# ---------------- Articles ----------------

class ArticleInput(BaseModel):
    title: str
    category: str
    severity: str = "Sedang"
    dek: str = ""
    body: str = ""
    image_url: str = ""
    author: str = "Redaksi Kabar Buruk"
    loss_estimate: Optional[str] = None
    reading_time: int = 5


class ReactionInput(BaseModel):
    type: str


class CommentInput(BaseModel):
    name: str
    text: str


@api_router.get("/articles")
async def list_articles(category: Optional[str] = None, q: Optional[str] = None):
    query: dict = {}
    if category and category != "Semua":
        query["category"] = category
    if q:
        regex = {"$regex": re.escape(q), "$options": "i"}
        query["$or"] = [{"title": regex}, {"dek": regex}, {"body": regex}]
    articles = await db.articles.find(query, {"_id": 0}).sort("published_at", -1).to_list(200)
    return articles


@api_router.get("/articles/{slug}")
async def get_article(slug: str):
    article = await db.articles.find_one({"slug": slug}, {"_id": 0})
    if not article:
        raise HTTPException(status_code=404, detail="Artikel tidak ditemukan")
    await db.articles.update_one({"slug": slug}, {"$inc": {"views": 1}})
    article["views"] = article.get("views", 0) + 1
    return article


@api_router.post("/articles")
async def create_article(input: ArticleInput, user=Depends(get_current_user)):
    doc = input.model_dump()
    doc.update({
        "id": uuid.uuid4().hex,
        "slug": slugify(input.title),
        "published_at": datetime.now(timezone.utc).isoformat(),
        "views": 0,
        "reactions": {"marah": 0, "kecewa": 0, "waspada": 0},
    })
    await db.articles.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api_router.put("/articles/{article_id}")
async def update_article(article_id: str, input: ArticleInput, user=Depends(get_current_user)):
    existing = await db.articles.find_one({"id": article_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Artikel tidak ditemukan")
    await db.articles.update_one({"id": article_id}, {"$set": input.model_dump()})
    return await db.articles.find_one({"id": article_id}, {"_id": 0})


@api_router.delete("/articles/{article_id}")
async def delete_article(article_id: str, user=Depends(get_current_user)):
    result = await db.articles.delete_one({"id": article_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Artikel tidak ditemukan")
    await db.comments.delete_many({"article_id": article_id})
    return {"ok": True}


@api_router.post("/articles/{article_id}/react")
async def react_article(article_id: str, input: ReactionInput):
    if input.type not in ("marah", "kecewa", "waspada"):
        raise HTTPException(status_code=400, detail="Reaksi tidak valid")
    await db.articles.update_one({"id": article_id}, {"$inc": {f"reactions.{input.type}": 1}})
    article = await db.articles.find_one({"id": article_id}, {"_id": 0, "reactions": 1})
    if not article:
        raise HTTPException(status_code=404, detail="Artikel tidak ditemukan")
    return article["reactions"]


# ---------------- Comments ----------------

@api_router.get("/articles/{article_id}/comments")
async def list_comments(article_id: str):
    return await db.comments.find({"article_id": article_id}, {"_id": 0}).sort("created_at", -1).to_list(500)


@api_router.post("/articles/{article_id}/comments")
async def create_comment(article_id: str, input: CommentInput):
    doc = {
        "id": uuid.uuid4().hex,
        "article_id": article_id,
        "name": input.name.strip() or "Anonim",
        "text": input.text.strip(),
        "upvotes": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.comments.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api_router.post("/comments/{comment_id}/upvote")
async def upvote_comment(comment_id: str):
    await db.comments.update_one({"id": comment_id}, {"$inc": {"upvotes": 1}})
    comment = await db.comments.find_one({"id": comment_id}, {"_id": 0, "upvotes": 1})
    if not comment:
        raise HTTPException(status_code=404, detail="Komentar tidak ditemukan")
    return comment


@api_router.get("/admin/comments")
async def admin_comments(user=Depends(get_current_user)):
    comments = await db.comments.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    article_ids = list({c["article_id"] for c in comments})
    articles = await db.articles.find({"id": {"$in": article_ids}}, {"_id": 0, "id": 1, "title": 1}).to_list(500)
    title_map = {a["id"]: a["title"] for a in articles}
    for c in comments:
        c["article_title"] = title_map.get(c["article_id"], "(artikel dihapus)")
    return comments


@api_router.delete("/admin/comments/{comment_id}")
async def delete_comment(comment_id: str, user=Depends(get_current_user)):
    await db.comments.delete_one({"id": comment_id})
    return {"ok": True}


# ---------------- Scandals & Rankings ----------------

@api_router.get("/scandals")
async def list_scandals():
    return await db.scandals.find({}, {"_id": 0}).to_list(100)


@api_router.get("/rankings")
async def list_rankings():
    return await db.rankings.find({}, {"_id": 0}).to_list(100)


@api_router.get("/rankings/{key}")
async def get_ranking(key: str):
    ranking = await db.rankings.find_one({"key": key}, {"_id": 0})
    if not ranking:
        raise HTTPException(status_code=404, detail="Indeks tidak ditemukan")
    return ranking


class RankingInput(BaseModel):
    value: str
    rank: int
    note: str = ""


@api_router.put("/admin/rankings/{key}")
async def update_ranking(key: str, input: RankingInput, user=Depends(get_current_user)):
    await db.rankings.update_one({"key": key}, {"$set": input.model_dump()})
    return await db.rankings.find_one({"key": key}, {"_id": 0})


# ---------------- Social Channels (kurasi konten media sosial) ----------------

class ChannelInput(BaseModel):
    name: str
    handle: str
    platform: str  # Instagram | YouTube | Facebook | TikTok | X
    followers: str = ""
    focus: str = ""
    url: str = ""


@api_router.get("/channels")
async def list_channels():
    return await db.channels.find({}, {"_id": 0}).to_list(100)


@api_router.post("/admin/channels")
async def create_channel(input: ChannelInput, user=Depends(get_current_user)):
    doc = input.model_dump()
    doc["id"] = uuid.uuid4().hex
    await db.channels.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api_router.put("/admin/channels/{channel_id}")
async def update_channel(channel_id: str, input: ChannelInput, user=Depends(get_current_user)):
    await db.channels.update_one({"id": channel_id}, {"$set": input.model_dump()})
    return await db.channels.find_one({"id": channel_id}, {"_id": 0})


@api_router.delete("/admin/channels/{channel_id}")
async def delete_channel(channel_id: str, user=Depends(get_current_user)):
    await db.channels.delete_one({"id": channel_id})
    return {"ok": True}


# ---------------- Edisi Mingguan (PDF-ready print page) ----------------

@api_router.get("/edisi-mingguan", response_class=HTMLResponse)
async def edisi_mingguan():
    articles = await db.articles.find({}, {"_id": 0}).sort("published_at", -1).to_list(6)
    scandals = await db.scandals.find({}, {"_id": 0}).to_list(6)
    rankings = await db.rankings.find({}, {"_id": 0}).to_list(12)

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=now.weekday() + 1)
    fmt = lambda d: d.strftime("%d %B %Y")
    edition_range = f"{fmt(start)} — {fmt(now)}"

    def esc(t):
        return (t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def fmt_date(iso):
        try:
            return datetime.fromisoformat(iso).strftime("%d %B %Y")
        except Exception:
            return ""

    article_html = ""
    for i, a in enumerate(articles):
        article_html += f"""
        <article class="story">
          <div class="story-num">{i + 1:02d}</div>
          <div>
            <p class="story-meta">{esc(a['category'])} · {esc(a['severity'])} · {fmt_date(a['published_at'])}</p>
            <h3 class="story-title">{esc(a['title'])}</h3>
            <p class="story-dek">{esc(a['dek'])}</p>
            <p class="story-byline">{esc(a['author'])}{(' · Kerugian: ' + esc(a['loss_estimate'])) if a.get('loss_estimate') else ''}</p>
          </div>
        </article>"""

    scandal_rows = "".join(
        f"<tr><td>{esc(s['title'])}</td><td>{esc(s['actor'])}</td><td class='loss'>{esc(s['loss'])}</td><td>{esc(s['status'])}</td></tr>"
        for s in scandals
    )
    ranking_rows = "".join(
        f"<tr><td>{esc(r['label'])}</td><td class='val'>{esc(r['value'])}</td><td>#{r['rank']} / {r['total']}</td></tr>"
        for r in rankings
    )

    html = f"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="utf-8">
<title>Edisi Mingguan — Kabar Buruk · {edition_range}</title>
<style>
  @page {{ size: A4; margin: 18mm; }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: Georgia, 'Times New Roman', serif; color: #0F172A; background: #FAF8F5; padding: 32px; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
  .masthead {{ display: flex; justify-content: space-between; align-items: flex-end; border-bottom: 4px solid #0F172A; padding-bottom: 14px; }}
  .brand {{ font-size: 34px; font-weight: 900; letter-spacing: -0.5px; }}
  .brand .k {{ display: inline-block; background: #DC2626; color: #fff; padding: 2px 9px; margin-right: 8px; border-radius: 4px; }}
  .edition {{ font-family: 'Courier New', monospace; font-size: 11px; letter-spacing: 2px; text-transform: uppercase; text-align: right; color: #475569; }}
  .edition strong {{ color: #DC2626; display: block; font-size: 13px; margin-top: 3px; }}
  .tagline {{ font-family: 'Courier New', monospace; font-size: 10px; letter-spacing: 2.5px; text-transform: uppercase; color: #DC2626; border-bottom: 1px solid #0F172A; padding: 8px 0; }}
  h2 {{ font-size: 18px; text-transform: uppercase; letter-spacing: 1px; border-bottom: 2px solid #0F172A; margin: 28px 0 14px; padding-bottom: 6px; }}
  .story {{ display: flex; gap: 18px; padding: 14px 0; border-bottom: 1px solid #CBD5E1; break-inside: avoid; }}
  .story-num {{ font-size: 28px; font-weight: 900; color: #DC2626; line-height: 1; min-width: 42px; }}
  .story-meta {{ font-family: 'Courier New', monospace; font-size: 9px; letter-spacing: 1.5px; text-transform: uppercase; color: #DC2626; margin-bottom: 4px; }}
  .story-title {{ font-size: 17px; font-weight: 800; line-height: 1.25; margin-bottom: 5px; }}
  .story-dek {{ font-size: 12.5px; line-height: 1.5; color: #334155; }}
  .story-byline {{ font-family: 'Courier New', monospace; font-size: 9.5px; color: #64748B; margin-top: 5px; text-transform: uppercase; letter-spacing: 1px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 11.5px; }}
  th {{ font-family: 'Courier New', monospace; font-size: 9px; letter-spacing: 1.5px; text-transform: uppercase; color: #64748B; text-align: left; border-bottom: 2px solid #0F172A; padding: 6px 8px 6px 0; }}
  td {{ border-bottom: 1px solid #E2E8F0; padding: 7px 8px 7px 0; vertical-align: top; }}
  .loss {{ color: #DC2626; font-weight: 700; }}
  .val {{ font-weight: 800; }}
  .cols {{ display: grid; grid-template-columns: 1fr 1fr; gap: 32px; }}
  .footer {{ margin-top: 28px; border-top: 4px solid #0F172A; padding-top: 10px; font-family: 'Courier New', monospace; font-size: 9.5px; letter-spacing: 1.5px; text-transform: uppercase; color: #64748B; display: flex; justify-content: space-between; }}
  @media print {{ body {{ padding: 0; }} }}
</style>
</head>
<body>
  <div class="masthead">
    <div class="brand"><span class="k">K</span>KABAR BURUK</div>
    <div class="edition">Edisi Mingguan<strong>{edition_range}</strong></div>
  </div>
  <p class="tagline">Berita yang tak enak didengar penguasa — arsip cetak untuk dibaca & dibagikan</p>

  <h2>Liputan Utama Pekan Ini</h2>
  {article_html}

  <div class="cols">
    <section>
      <h2>Arsip Skandal</h2>
      <table>
        <thead><tr><th>Kasus</th><th>Aktor</th><th>Kerugian</th><th>Status</th></tr></thead>
        <tbody>{scandal_rows}</tbody>
      </table>
    </section>
    <section>
      <h2>Rapor Peringkat Dunia</h2>
      <table>
        <thead><tr><th>Indeks</th><th>Nilai</th><th>Peringkat</th></tr></thead>
        <tbody>{ranking_rows}</tbody>
      </table>
    </section>
  </div>

  <div class="footer">
    <span>kabarburuk — dokumentasi & kritik jurnalistik</span>
    <span>diterbitkan {fmt(now)}</span>
  </div>
  <script>window.onload = () => window.print()</script>
</body>
</html>"""
    return HTMLResponse(html)


# ---------------- Seed ----------------

SEED_ARTICLES = [
    {
        "title": "Kasus Timah Rp 300 Triliun: Kebocoran Terbesar dalam Sejarah Republik?",
        "category": "Korupsi",
        "severity": "Kritis",
        "dek": "Tata niaga timah ilegal di wilayah IUP PT Timah menyeret pengusaha kakap hingga pejabat. BPKP menghitung kerugian negara menembus Rp 300 triliun — angka yang nyaris mustahil dibayangkan.",
        "body": "Kejaksaan Agung menyebut ini salah satu kasus korupsi terbesar yang pernah ditangani. Selama hampir satu dekade, tata niaga timah di Bangka Belitung diduga dikendalikan segelintir pihak melalui skema sewa peralatan dan pembelian bijih ilegal di dalam wilayah izin usaha pertambangan PT Timah.\n\nBadan Pengawasan Keuangan dan Pembangunan menghitung kerugian keuangan negara mencapai Rp 300 triliun, termasuk kerusakan lingkungan yang masif. Sejumlah terdakwa telah divonis puluhan tahun penjara, namun publik terus bertanya: ke mana aliran dana itu bermuara?\n\nHingga kini, pemulihan aset berjalan lambat. Kritikus menilai penegakan hukum berhenti pada aktor lapangan, sementara penerima manfaat terbesar dinilai belum tersentuh. Kasus ini menjadi simbol bagaimana kekayaan alam negeri ini bisa menguap tanpa pertanggungjawaban.",
        "image_url": "https://images.unsplash.com/photo-1624421980204-22e40117494f?crop=entropy&cs=srgb&fm=jpg&q=85",
        "author": "Tim Investigasi",
        "loss_estimate": "Rp 300 T",
        "reading_time": 7,
    },
    {
        "title": "RUU Pilkada 2024: Ketika DPR Melawan Putusan Mahkamah Konstitusi",
        "category": "Kebijakan",
        "severity": "Kritis",
        "dek": "Upaya DPR menganulir putusan MK soal ambang batas pencalonan kepala daerah memicu demonstrasi besar di berbagai kota. Gedung DPR dikepung, pagar dibakar, rancangan akhirnya ditarik.",
        "body": "Mahkamah Konstitusi memutuskan menurunkan ambang batas pencalonan kepala daerah dan menegaskan syarat usia minimal. Dalam hitungan jam, DPR bergerak menyusun revisi UU Pilkada yang justru berlawanan arah dengan putusan itu.\n\nLangkah tersebut memicu gelombang protes 'Peringatan Darurat' dengan tagar biru yang bergema di media sosial. Mahasiswa, buruh, hingga selebritas turun ke jalan. Gedung DPR di sejumlah daerah didemonstrasi, sebagian berakhir ricuh.\n\nDPR akhirnya menunda pengesahan, namun kepercayaan publik telah terlanjur tergerus. Para pengamat menilai episode ini menunjukkan rapuhnya komitmen lembaga negara terhadap konstitusi ketika kepentingan politik jangka pendek berkuasa.",
        "image_url": "https://images.unsplash.com/photo-1756142183803-d7092cfef1e0?crop=entropy&cs=srgb&fm=jpg&q=85",
        "author": "Dewi Kartika",
        "loss_estimate": None,
        "reading_time": 6,
    },
    {
        "title": "Harun Masiku: Buron Kelas Kakap yang Tak Kunjung Tertangkap",
        "category": "Skandal",
        "severity": "Tinggi",
        "dek": "Buron KPK sejak Januari 2020 dalam kasus suap pergantian antarwaktu anggota DPR. Bertahun-tahun berlalu, keberadaannya tetap misterius — dan publik makin curiga.",
        "body": "Harun Masiku ditetapkan sebagai tersangka pemberi suap kepada komisioner KPU Wahyu Setiawan terkait pergantian antarwaktu anggota DPR. Saat operasi tangkap tangan digelar, ia lenyap — dan tidak pernah ditemukan hingga hari ini.\n\nBerbagai teori beredar: disembunyikan kekuatan besar, kabur ke luar negeri, bahkan sudah meninggal. Interpol sempat mengeluarkan red notice, namun tanpa hasil. Setiap kali kasus ini diangkat, selalu ada isu lain yang mengalihkan perhatian publik.\n\nKasus Harun Masiku menjadi cermin kemandulan penegakan hukum terhadap tokoh politik. Selama ia bebas, pertanyaan besarnya tetap menggantung: siapa yang melindungi buron ini?",
        "image_url": "https://images.unsplash.com/photo-1574936924661-23374e86f1a8?crop=entropy&cs=srgb&fm=jpg&q=85",
        "author": "Bagas Prakoso",
        "loss_estimate": None,
        "reading_time": 5,
    },
    {
        "title": "Kebebasan Pers Indonesia Terjun ke Peringkat 111 Dunia",
        "category": "Kontroversi",
        "severity": "Tinggi",
        "dek": "Laporan Reporters Without Borders menempatkan Indonesia makin terpuruk. Kekerasan terhadap jurnalis, kriminalisasi lewat UU ITE, dan konsentrasi kepemilikan media jadi catatan merah.",
        "body": "Indeks Kebebasan Pers Dunia menempatkan Indonesia di peringkat 111 dari 180 negara — jauh di bawah negara tetangga seperti Timor Leste. Padahal, pers disebut sebagai pilar keempat demokrasi.\n\nAliansi Jurnalis Independen mencatat puluhan kasus kekerasan terhadap jurnalis setiap tahun, mulai dari intimidasi, perusakan alat, hingga kriminalisasi. Pasal-pasal karet UU ITE kerap dipakai untuk membungkam liputan kritis.\n\nKonsentrasi kepemilikan media di tangan segelintir konglomerat yang juga politikus memperparah keadaan. Ketika berita dikendalikan kepentingan, publik hanya menerima kabar yang aman bagi penguasa.",
        "image_url": "https://images.pexels.com/photos/158651/news-newsletter-newspaper-information-158651.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
        "author": "Rani Amelia",
        "loss_estimate": None,
        "reading_time": 5,
    },
    {
        "title": "Tapera: Iuran Wajib yang Memicu Gelombang Protes Pekerja",
        "category": "Kebijakan",
        "severity": "Tinggi",
        "dek": "Pemerintah mewajibkan potongan gaji 3% untuk Tabungan Perumahan Rakyat. Serikat pekerja menolak keras — di tengah upah stagnan, kebijakan ini dianggap tak berpihak.",
        "body": "Peraturan Pemerintah tentang Tapera mewajibkan setiap pekerja dipotong 3% dari gaji — 2,5% ditanggung pekerja, 0,5% pemberi kerja. Dalilnya mulia: pembiayaan perumahan rakyat. Namun waktunya dinilai sangat tidak tepat.\n\nSerikat buruh menggelar aksi di berbagai daerah. Di tengah kenaikan harga kebutuhan pokok dan gelombang PHK, potongan tambahan dipandang membebani. Pengusaha pun keberatan karena menambah biaya produksi.\n\nSetelah desakan publik menguat, pemerintah akhirnya mengubah sifat kepesertaan menjadi sukarela. Episode ini menunjukkan pola lama: kebijakan disahkan dulu, didengar rakyatnya belakangan.",
        "image_url": "https://images.unsplash.com/photo-1756142507999-ea5301f4350a?crop=entropy&cs=srgb&fm=jpg&q=85",
        "author": "Fajar Nugraha",
        "loss_estimate": None,
        "reading_time": 4,
    },
    {
        "title": "Dinasti Politik dan Putusan MK yang Mengubah Peta Kekuasaan",
        "category": "Skandal",
        "severity": "Kritis",
        "dek": "Putusan MK soal batas usia capres-cawapres membuka jalan keluarga presiden melenggang ke kekuasaan. Ketua MK-nya sendiri kemudian dinyatakan melanggar etik.",
        "body": "Putusan Mahkamah Konstitusi nomor 90/PUU-XXI/2023 mengubah syarat usia calon presiden dan wakil presiden, membuka jalan bagi kerabat penguasa untuk maju. Putusan itu diambil saat ketua MK masih memiliki hubungan keluarga dengan penguasa.\n\nMajelis Kehormatan MK kemudian menyatakan sang ketua melanggar etik berat dan memberhentikannya dari jabatan ketua. Namun putusannya tetap berlaku — hasil pemilu pun berjalan sesuai skenario.\n\nDi daerah, pola serupa bermunculan: bupati menjabat, anak dan menantu menyusul. Para pengamat menyebut Indonesia tengah mengalami regresi demokrasi, di mana kekuasaan dikelola seperti usaha keluarga.",
        "image_url": "https://images.unsplash.com/photo-1569996958517-3b0e816ac40c?crop=entropy&cs=srgb&fm=jpg&q=85",
        "author": "Dewi Kartika",
        "loss_estimate": None,
        "reading_time": 6,
    },
    {
        "title": "BTS 4G: Menara yang Tak Berdiri, Uang Negara Rp 8 Triliun Melayang",
        "category": "Korupsi",
        "severity": "Kritis",
        "dek": "Proyek pembangunan ribuan menara BTS di daerah terdepan, terluar, dan tertinggal berujung di meja hijau. Mantan menteri divonis 15 tahun penjara.",
        "body": "Proyek BTS 4G Bakti Kominfo seharusnya menghadirkan sinyal di ribuan desa terpencil. Kenyataannya, banyak menara tak pernah berdiri, sementara anggaran negara menguap hingga Rp 8 triliun menurut perhitungan BPKP.\n\nPersidangan menyeret mantan Menteri Komunikasi dan Informatika yang divonis 15 tahun penjara. Aliran dana proyek juga disebut mengalir ke berbagai pihak, termasuk untuk kegiatan di luar proyek.\n\nIronisnya, hingga kini banyak wilayah 3T tetap tanpa sinyal. Rakyat di pelosok menjadi korban dua kali: dibiarkan gelap sinyal, dan uang pajaknya dikorupsi.",
        "image_url": "https://images.unsplash.com/photo-1624421980204-22e40117494f?crop=entropy&cs=srgb&fm=jpg&q=85",
        "author": "Tim Investigasi",
        "loss_estimate": "Rp 8 T",
        "reading_time": 5,
    },
    {
        "title": "IKN: Megaproyek Ambisius di Tengah Defisit dan Janji yang Menggantung",
        "category": "Kontroversi",
        "severity": "Sedang",
        "dek": "Ibu Kota Nusantara dijanjikan dibiayai mayoritas investor swasta. Kenyataannya APBN menanggung beban besar, sementara investor asing yang dijanjikan tak kunjung datang.",
        "body": "Pemindahan ibu kota ke Kalimantan Timur diiklankan sebagai lompatan peradaban dengan pembiayaan mayoritas dari sektor swasta. Bertahun-tahun berjalan, realisasi investasi asing nyaris nol — APBN lah yang menanggung ratusan triliun rupiah.\n\nPemerintahan baru mewarisi proyek ini dengan anggaran yang terus dipangkas. Jadwal pembangunan mundur, target pemindahan ASN tertunda, dan sebagian fasilitas mangkrak setengah jadi.\n\nKritikus menilai IKN adalah monumen ambisi yang dipaksakan di tengah defisit anggaran dan utang yang menggunung. Pertanyaannya tetap sama sejak awal: untuk siapa ibu kota ini sebenarnya dibangun?",
        "image_url": "https://images.pexels.com/photos/158651/news-newsletter-newspaper-information-158651.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
        "author": "Bagas Prakoso",
        "loss_estimate": "Rp 466 T (estimasi total)",
        "reading_time": 6,
    },
    {
        "title": "Kabinet Gemuk ala Prabowo: 100+ Kursi Menteri dan Wakil Menteri, Rekor Terbesar Era Reformasi",
        "category": "Kebijakan",
        "severity": "Tinggi",
        "dek": "Presiden Prabowo Subianto membentuk kabinet terbesar sejak reformasi dengan lebih dari seratus menteri, wakil menteri, dan pejabat setingkat. Kritikus menyebutnya politik akomodasi yang membebani APBN.",
        "body": "Kabinet Merah Putih mencetak rekor: 48 kementerian dengan total lebih dari 100 menteri, wakil menteri, dan pejabat setingkat menteri. Jumlah ini melampaui kabinet era Jokowi maupun pemerintahan sebelumnya, bahkan mendekati praktik era Orde Baru.\n\nPara pengamat menilai gemuknya kabinet bukan soal kebutuhan teknis, melainkan akomodasi politik. Koalisi superbesar yang dibangun membuat hampir semua partai pendukung menuntut jatah kursi. Akibatnya, fungsi kementerian tumpang tindih dan koordinasi justru makin rumit.\n\nIronisnya, di saat yang sama pemerintah menggemakan efisiensi anggaran. Biaya gaji, tunjangan, dan rumah dinas untuk seratus lebih pejabat itu membebani APBN ratusan miliar rupiah per tahun — uang yang bisa dialihkan untuk sekolah atau puskesmas.",
        "image_url": "https://images.unsplash.com/photo-1624421980204-22e40117494f?crop=entropy&cs=srgb&fm=jpg&q=85",
        "author": "Dewi Kartika",
        "loss_estimate": None,
        "reading_time": 6,
    },
    {
        "title": "Efisiensi Anggaran Rp 306 Triliun: Pemangkasan Masal dan Layanan Publik yang Tersendat",
        "category": "Kebijakan",
        "severity": "Kritis",
        "dek": "Instruksi presiden memangkas belanja kementerian dan lembaga ratusan triliun rupiah. Honorarium ditahan, perjalanan dinas dibekukan, ribuan pegawai kontrak dirumahkan.",
        "body": "Lewat instruksi efisiensi anggaran, pemerintahan Prabowo memangkas belanja kementerian dan lembaga hingga lebih dari Rp 300 triliun. Sebagian dialihkan untuk membiayai program prioritas seperti makan bergizi gratis.\n\nDampaknya langsung terasa di akar rumput: ribuan pegawai honorer dan kontrak di berbagai daerah dirumahkan, dana penelitian kampus menyusut, beasiswa terancam, hingga biaya operasional layanan publik dipangkas habis. Di sejumlah kementerian, lampu gedung dimatikan bergantian dan pencetakan dokumen dibatasi.\n\nEkonom mengingatkan bahwa pemangkasan masal tanpa peta jalan yang jelas justru menekan daya beli masyarakat dan memperlambat ekonomi. Yang paling dikritik: minimnya transparansi soal pos apa saja yang dipangkas dan ke mana uangnya benar-benar bermuara.",
        "image_url": "https://images.pexels.com/photos/158651/news-newsletter-newspaper-information-158651.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
        "author": "Fajar Nugraha",
        "loss_estimate": "Rp 306 T (dipangkas)",
        "reading_time": 6,
    },
    {
        "title": "Makan Bergizi Gratis di Bawah Sorotan: Anggaran Fantastis dan Gelombang Keracunan Massal",
        "category": "Skandal",
        "severity": "Kritis",
        "dek": "Program andalan Prabowo senilai ratusan triliun rupiah per tahun menyasar puluhan juta anak. Alih-alih menjadi lompatan gizi, program ini diwarnai ribuan kasus keracunan dan dapur tak layak.",
        "body": "Makan Bergizi Gratis diiklankan sebagai warisan terbesar pemerintahan Prabowo: makan siang gratis untuk puluhan juta anak sekolah dan ibu hamil, dengan anggaran yang diperkirakan menembus Rp 171 triliun per tahun saat berjalan penuh.\n\nNamun implementasinya terseok-seok. Laporan keracunan massal berdatangan dari berbagai daerah — ribuan anak muntah dan dilarikan ke puskesmas setelah menyantap paket makanan. Pemeriksaan menemukan dapur-dapur satuan layanan yang tak memenuhi standar higienitas.\n\nKritikus juga menyoroti mekanisme kontrak dan yayasan penyelenggara yang dinilai rawan konflik kepentingan. Dengan dana sebesar itu mengalir lewat skema yang belum matang, program ini berisiko menjadi lahan subur penyelewengan baru — bila pengawasan tak diperketat.",
        "image_url": "https://images.unsplash.com/photo-1569996958517-3b0e816ac40c?crop=entropy&cs=srgb&fm=jpg&q=85",
        "author": "Rani Amelia",
        "loss_estimate": "Rp 171 T (anggaran/tahun)",
        "reading_time": 6,
    },
    {
        "title": "Danantara: 'Superholding' Triliunan Rupiah yang Bergerak di Luar Jangkauan Pengawasan",
        "category": "Kontroversi",
        "severity": "Tinggi",
        "dek": "Badan pengelola aset BUMN dengan nilai diklaim hampir Rp 15.000 triliun kini menguasai dividen dan arah kebijakan perusahaan negara. UU baru mengecualikannya dari definisi keuangan negara.",
        "body": "Daya Aneka Nusantara Investment Agency — Danantara — didapuk menjadi superholding yang mengelola saham pemerintah di puluhan BUMN, dari bank pelat merah hingga PLN. Nilai aset yang dikelolanya diklaim setara ratusan miliar dolar AS.\n\nMasalahnya, perubahan UU BUMN membuat aset Danantara tak lagi dianggap keuangan negara. Artinya, ruang pemeriksaan oleh BPK menyempit dan penanganan potensi penyimpangan menjadi abu-abu secara hukum. Struktur penasihatnya pun diisi lingkaran dekat presiden.\n\nPengamat membandingkannya dengan dana kekayaan negara lain di dunia yang diawasi ketat parlemen. Di Indonesia, publik hanya bisa berharap pada itikad baik — sementara triliunan rupiah dividen rakyat berpindah ke tangan segelintir orang.",
        "image_url": "https://images.unsplash.com/photo-1624421980204-22e40117494f?crop=entropy&cs=srgb&fm=jpg&q=85",
        "author": "Bagas Prakoso",
        "loss_estimate": None,
        "reading_time": 6,
    },
    {
        "title": "'Indonesia Gelap': Ketika Tagar Media Sosial Lebih Didengar daripada Ruang Rapat DPR",
        "category": "Media Sosial",
        "severity": "Tinggi",
        "dek": "Gerakan mahasiswa dan warganet dengan tagar #IndonesiaGelap menggema lintas platform. Demonstrasi fisik diiringi jutaan unggahan — tanda membesarnya kekecewaan yang dikelola lewat layar.",
        "body": "Berawal dari unggahan mahasiswa, tagar #IndonesiaGelap menjalar ke seluruh platform: gambar logo Garuda yang digelapkan, keluhan soal efisiensi anggaran, PHK, dan beasiswa yang menyusut. Dalam hitungan hari, tagar itu dipakai jutaan kali.\n\nAksi turun ke jalan menyusul di berbagai kota. Menariknya, organisasi gerakan kali ini nyaris tanpa komando pusat — semuanya diorkestrasi lewat grup chat, infografis viral, dan video pendek. Pemerintah merespons dengan bantahan yang justru menjadi bahan bakar gelombang berikutnya.\n\nFenomena ini menegaskan pergeseran besar: arena perjuangan politik kini berada di media sosial. Ruang rapat DPR yang tertutup kalah cepat oleh kecepatan unggahan, dan partai-partai tampak belum paham cara membacanya.",
        "image_url": "https://images.unsplash.com/photo-1574936924661-23374e86f1a8?crop=entropy&cs=srgb&fm=jpg&q=85",
        "author": "Tim Redaksi",
        "loss_estimate": None,
        "reading_time": 5,
    },
    {
        "title": "Rombongan Influencer di Istana: Ketika Negara Dirangkul Lewat Konten",
        "category": "Media Sosial",
        "severity": "Sedang",
        "dek": "Kreator konten dan influencer diajak mendampingi acara resmi kenegaraan hingga tur ke luar negeri. Apresiasi terhadap karya anak bangsa, atau mesin pembentuk opini baru?",
        "body": "Pemandangan baru di lingkungan istana: deretan influencer dan YouTuber berjajar di acara resmi, membuat vlog dari sudut-sudut yang biasanya hanya diakses jurnalis terakreditasi. Pemerintah menyebutnya upaya mendekatkan negara dengan anak muda.\n\nNamun pertanyaan etis mengemuka. Ketika kreator yang diundang mendapatkan akses istimewa, apakah konten yang dihasilkan masih independen? Sejumlah kreator mengaku tak dibayar, namun akses itu sendiri adalah kompensasi yang tak ternilai harganya.\n\nPengamat komunikasi menyebut ini evolusi politik pencitraan: dari iklan televisi ke konten genggaman. Publik tak lagi membedakan mana liputan, mana endorsement — dan di situlah letak bahayanya.",
        "image_url": "https://images.unsplash.com/photo-1756142183803-d7092cfef1e0?crop=entropy&cs=srgb&fm=jpg&q=85",
        "author": "Rani Amelia",
        "loss_estimate": None,
        "reading_time": 4,
    },
    {
        "title": "Ekonomi Buzzer: Industri Komentar Bayaran yang Menyusupi Percakapan Publik",
        "category": "Media Sosial",
        "severity": "Tinggi",
        "dek": "Dari trending topik pesanan hingga pasukan komentar: ekonomi perbuzzeran diperkirakan bernilai miliaran rupiah per musim kampanye. Siapa yang membayar, dan untuk agenda siapa?",
        "body": "Berbagai riset akademik mencatat praktik pasukan buzzer menjadi bisnis yang matang: ada broker, ada daftar tarif per unggahan, per komentar, hingga per trending topik. Pada musim pemilu, nilai perputarannya ditaksir mencapai miliaran rupiah.\n\nDampaknya bukan sekadar kebisingan. Percakapan publik yang seharusnya organik berubah menjadi panggung sandiwara: isu dimainkan, tokoh diserang, opini digiring. Warganet awam sering tak sadar bahwa 'keramaian' di linimasanya adalah produk pesanan.\n\nRegulasi belum mampu mengejar. Platform media sosial berdalih netralitas, sementara undang-undang tak mengatur secara spesifik. Selama permintaan dari aktor politik terus ada, industri bayangan ini akan terus tumbuh subur.",
        "image_url": "https://images.pexels.com/photos/158651/news-newsletter-newspaper-information-158651.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
        "author": "Bagas Prakoso",
        "loss_estimate": None,
        "reading_time": 5,
    },
]

SEED_SCANDALS = [
    {"title": "Korupsi Timah Rp 300 Triliun", "actor": "Eks Dirut PT Timah & kroni", "status": "Dalam Proses Hukum", "loss": "Rp 300 T", "year": "2015–2022", "summary": "Tata niaga timah ilegal di wilayah IUP PT Timah; kerugian keuangan negara versi BPKP Rp 300 triliun."},
    {"title": "Buron Harun Masiku", "actor": "Politisi PDIP", "status": "Menggantung", "loss": "—", "year": "2020–kini", "summary": "Buron KPK sejak 2020 dalam kasus suap PAW anggota DPR; keberadaannya tak pernah terungkap."},
    {"title": "Korupsi BTS 4G Kominfo", "actor": "Eks Menkominfo & pejabat", "status": "Dalam Proses Hukum", "loss": "Rp 8 T", "year": "2020–2022", "summary": "Proyek menara BTS yang sebagian tak berdiri; menjerat mantan menteri."},
    {"title": "Kasus Formula E Jakarta", "actor": "Eks Gubernur DKI", "status": "Dihentikan/SP3", "loss": "Rp 560 M (commitment fee)", "year": "2019–2022", "summary": "Commitment fee balapan listrik sempat diusut lalu dihentikan; publik mempertanyakan."},
    {"title": "Drama RUU Pilkada 2024", "actor": "DPR RI", "status": "Pengalihan Isu", "loss": "—", "year": "2024", "summary": "Upaya DPR menganulir putusan MK memicu demo besar; rancangan akhirnya ditarik."},
    {"title": "BLBI & Kasus Century", "actor": "Berkas lama, aktor berlapis", "status": "Menggantung", "loss": "Rp 6,7 T", "year": "2008–kini", "summary": "Hampir dua dekade berlalu, pengembalian dana talangan belum juga tuntas."},
]

SEED_RANKINGS = [
    {
        "key": "cpi", "label": "Indeks Persepsi Korupsi", "value": "34/100", "rank": 115, "total": 180, "pct": 19,
        "trend": "stagnan", "metric": "Skor CPI (0–100)", "source": "Transparency International, CPI 2024",
        "source_url": "https://www.transparency.org/en/cpi/2024",
        "note": "Skor stagnan satu dekade; dua pertiga negara dunia mencetak di bawah 50.",
        "description": "Corruption Perceptions Index (CPI) mengukur persepsi korupsi di sektor publik berdasarkan gabungan survei ahli dan pelaku bisnis. Skala 0 berarti sangat korup dan 100 berarti sangat bersih.\n\nIndonesia mencetak skor 34 dan bertengger di peringkat 115 dari 180 negara — jauh di bawah Singapura (83) dan bahkan Timor Leste. Yang paling mengkhawatirkan bukan angkanya, melainkan stagnansinya: selama satu dekade terakhir skor Indonesia nyaris tidak bergerak.\n\nTransparency International mencatat negara-negara dengan lembaga antikorupsi yang dilemahkan dan kebebasan pers yang menurun cenderung terjebak pada skor rendah — dua hal yang kini sama-sama dialami Indonesia.",
        "trend_data": [
            {"year": "2020", "value": 37}, {"year": "2021", "value": 38}, {"year": "2022", "value": 34},
            {"year": "2023", "value": 34}, {"year": "2024", "value": 34},
        ],
    },
    {
        "key": "press", "label": "Kebebasan Pers", "value": "Peringkat 111", "rank": 111, "total": 180, "pct": 38,
        "trend": "turun", "metric": "Peringkat (lebih kecil lebih baik)", "source": "Reporters Without Borders, 2025",
        "source_url": "https://rsf.org/en/index",
        "note": "Kekerasan terhadap jurnalis dan kriminalisasi UU ITE jadi catatan merah.",
        "description": "World Press Freedom Index dari Reporters Without Borders (RSF) menilai kemampuan jurnalis di 180 negara untuk bekerja bebas dan aman. Indonesia berada di peringkat 111 — tertinggal dari Timor Leste (39) yang jauh lebih muda sebagai negara.\n\nRSF menyoroti tiga hal: kekerasan dan intimidasi terhadap jurnalis yang jarang diproses hukum, pasal-pasal karet UU ITE yang dipakai mengkriminalisasi liputan kritis, serta konsentrasi kepemilikan media di tangan konglomerat yang sekaligus aktor politik.\n\nAliansi Jurnalis Independen mencatat puluhan kasus kekerasan terhadap jurnalis setiap tahunnya. Ketika pers yang mengawasi kekuasaan justru dikerdilkan, skandal-skandal di situs ini menjadi lebih mudah disembunyikan.",
        "trend_data": [
            {"year": "2021", "value": 113}, {"year": "2022", "value": 117}, {"year": "2023", "value": 108},
            {"year": "2024", "value": 111}, {"year": "2025", "value": 111},
        ],
    },
    {
        "key": "iq", "label": "IQ Rata-Rata", "value": "78,5", "rank": 130, "total": 199, "pct": 35,
        "trend": "stagnan", "metric": "IQ rata-rata", "source": "World Population Review (diperdebatkan)",
        "source_url": "https://www.worldpopulationreview.com/country-rankings/average-iq-by-country",
        "note": "Metodologi diperdebatkan para ahli, namun angkanya kerap dikutip publik.",
        "description": "Angka IQ rata-rata nasional yang dikutip World Population Review menempatkan Indonesia pada skor 78,5 — jauh di bawah rata-rata global 100. Angka ini sempat viral dan memicu perdebatan nasional.\n\nPara ahli mengingatkan bahwa metodologi pengukuran IQ lintas negara sangat problematis: sampel tidak merata, bias bahasa dan budaya dalam soal, serta kualitas studi yang beragam. Angka ini bukan cermin kecerdasan genetik bangsa.\n\nNamun ia menjadi pengingat yang keras tentang persoalan nyata: stunting, gizi buruk pada masa emas perkembangan otak, dan kualitas pendidikan yang timpang antardaerah. Solusinya bukan membantah angkanya, melainkan memperbaiki akarnya.",
        "trend_data": [
            {"year": "2021", "value": 78.9}, {"year": "2022", "value": 78.7}, {"year": "2023", "value": 78.5},
            {"year": "2024", "value": 78.5}, {"year": "2025", "value": 78.5},
        ],
    },
    {
        "key": "education", "label": "Indeks Pendidikan (HDI)", "value": "0,728", "rank": 113, "total": 193, "pct": 41,
        "trend": "naik", "metric": "Nilai HDI (0–1)", "source": "UNDP, Laporan HDI 2025",
        "source_url": "https://hdr.undp.org",
        "note": "Rata-rata lama sekolah masih di bawah 13 tahun.",
        "description": "Human Development Index (HDI) dari UNDP menggabungkan kesehatan, pendidikan, dan pendapatan menjadi satu angka. Indonesia mencetak 0,728 dan berada di peringkat 113 dari 193 negara — kategori pembangunan manusia tinggi, namun papan bawah.\n\nKomponen pendidikan menjadi pemberat utama: rata-rata lama sekolah orang dewasa Indonesia masih di bawah 13 tahun, tertinggal dari Malaysia dan Thailand. Tes PISA pun menempatkan literasi dan numerasi pelajar Indonesia di kelompok bawah dunia.\n\nAnggaran pendidikan 20% dari APBN sudah diamanatkan konstitusi, namun serapan dan kualitasnya menjadi soal — banyak yang terserap untuk gaji dan seremonial, bukan perbaikan pembelajaran.",
        "trend_data": [
            {"year": "2021", "value": 0.705}, {"year": "2022", "value": 0.713}, {"year": "2023", "value": 0.720},
            {"year": "2024", "value": 0.728}, {"year": "2025", "value": 0.728},
        ],
    },
    {
        "key": "health", "label": "Keamanan Kesehatan Global", "value": "50,4/100", "rank": 30, "total": 195, "pct": 15,
        "trend": "naik", "metric": "Skor GHS (0–100)", "source": "Global Health Security Index 2021",
        "source_url": "https://www.ghsindex.org",
        "note": "Pandemi mengekspos kesenjangan fasilitas kesehatan antardaerah.",
        "description": "Global Health Security Index menilai kesiapan 195 negara menghadapi wabah dan darurat kesehatan. Indonesia mencetak 50,4 dari 100 — lebih baik dari rata-rata global, namun jauh dari kata aman.\n\nPandemi Covid-19 membuktikan rapuhnya fondasi itu: fasilitas kesehatan di luar Jawa kewalahan, oksigen langka, dan data yang simpang siur memperlambat respons. Kesenjangan dokter dan puskesmas antardaerah hingga kini belum terjembatani.\n\nIndeks ini diterbitkan berkala, sehingga datanya tidak diperbarui setiap tahun — dua titik data terakhir menunjukkan penurunan skor yang belum dipulihkan.",
        "trend_data": [
            {"year": "2019", "value": 56.6}, {"year": "2021", "value": 50.4},
        ],
    },
    {
        "key": "gdp", "label": "PDB Nominal", "value": "US$ 1,4 T", "rank": 16, "total": 190, "pct": 8,
        "trend": "naik", "metric": "PDB (US$ triliun)", "source": "IMF, World Economic Outlook 2025",
        "source_url": "https://www.imf.org/en/Publications/WEO",
        "note": "Ekonomi terbesar ASEAN, namun PDB per kapita hanya peringkat 117.",
        "description": "Dengan PDB nominal sekitar US$ 1,4 triliun, Indonesia adalah ekonomi terbesar di Asia Tenggara dan salah satu dari dua puluh terbesar dunia. Ini satu-satunya indeks di halaman ini di mana Indonesia tampil sebagai raksasa.\n\nNamun angka agregat menyembunyikan cerita lain: dibagi 280 juta penduduk, PDB per kapita Indonesia hanya sekitar seperlima Malaysia. Pertumbuhan ekonomi yang stabil di kisaran 5% juga dikritik karena dinikmati tidak merata.\n\nParadoks 'ekonomi besar, rakyat kecil' ini menjadi bahan bakar banyak liputan di situs ini — kekayaan nasional ada, pertanyaannya dikelola oleh dan untuk siapa.",
        "trend_data": [
            {"year": "2021", "value": 1.19}, {"year": "2022", "value": 1.32}, {"year": "2023", "value": 1.37},
            {"year": "2024", "value": 1.40}, {"year": "2025", "value": 1.44},
        ],
    },
    {
        "key": "democracy", "label": "Indeks Demokrasi", "value": "6,44/10", "rank": 54, "total": 167, "pct": 32,
        "trend": "turun", "metric": "Skor EIU (0–10)", "source": "The Economist Intelligence Unit, 2024",
        "source_url": "https://www.eiu.com",
        "note": "Status 'demokrasi cacat' bertahan sejak 2017.",
        "description": "Indeks Demokrasi dari Economist Intelligence Unit menilai 167 negara dari lima aspek: pemilu, kebebasan sipil, fungsi pemerintah, partisipasi, dan budaya politik. Skor Indonesia 6,44 menempatkannya pada kategori 'demokrasi cacat' (flawed democracy).\n\nStatus itu bertahan sejak 2017 dan cenderung menurun. EIU mencatat pelemahan lembaga antikorupsi, pengecilan ruang sipil, dan dominasi kekuasaan yang tidak diimbangi oposisi yang sehat.\n\nTurunnya kualitas demokrasi bukan sekadar angka — ia terasa pada bagaimana putusan MK dipermainkan, bagaimana RUU disahkan kilat, dan bagaimana kritik dibungkam. Semua terdokumentasi di arsip situs ini.",
        "trend_data": [
            {"year": "2020", "value": 6.48}, {"year": "2021", "value": 6.71}, {"year": "2022", "value": 6.71},
            {"year": "2023", "value": 6.53}, {"year": "2024", "value": 6.44},
        ],
    },
    {
        "key": "happiness", "label": "Indeks Kebahagiaan Dunia", "value": "5,62/10", "rank": 83, "total": 147, "pct": 34,
        "trend": "naik", "metric": "Skor kebahagiaan (0–10)", "source": "World Happiness Report 2025",
        "source_url": "https://worldhappiness.report",
        "note": "Posisi membaik dua tahun terakhir, namun jauh di bawah negara-negara Nordik (7,7+).",
        "description": "World Happiness Report menilai kebahagiaan warga 147 negara lewat survei Gallup: dukungan sosial, kebebasan memilih, persepsi korupsi, kemurahan hati, dan pendapatan. Indonesia mencetak 5,62 dan berada di peringkat 83.\n\nMenariknya, faktor pemberat Indonesia bukan pendapatan, melainkan persepsi korupsi dan rendahnya kepercayaan terhadap institusi. Negara yang warganya percaya pemerintahnya bersih secara konsisten lebih bahagia.\n\nPosisi Indonesia membaik dalam dua tahun terakhir, namun tetap tertinggal dari sebagian besar tetangganya di Asia Tenggara.",
        "trend_data": [
            {"year": "2021", "value": 5.35}, {"year": "2022", "value": 5.24}, {"year": "2023", "value": 5.28},
            {"year": "2024", "value": 5.57}, {"year": "2025", "value": 5.62},
        ],
    },
    {
        "key": "gdppc", "label": "PDB per Kapita", "value": "US$ 4.980", "rank": 117, "total": 190, "pct": 22,
        "trend": "naik", "metric": "US$ ribu per kapita", "source": "IMF, World Economic Outlook 2025",
        "source_url": "https://www.imf.org/en/Publications/WEO",
        "note": "Tertinggal jauh dari Malaysia (US$ 13 ribu) dan Thailand (US$ 7 ribu).",
        "description": "Jika PDB total membuat Indonesia tampak raksasa, PDB per kapita membongkar ilusinya: sekitar US$ 4.980 per orang per tahun, menempatkan Indonesia di peringkat 117 dunia — satu kelompok dengan negara-negara Afrika berkembang.\n\nAngka ini menjelaskan banyak hal: mengapa kenaikan harga BBM menyakitkan, mengapa potongan gaji 3% untuk Tapera memicu protes, dan mengapa jutaan keluarga masih hidup pas-pasan meski negara disebut ekonomi terbesar ASEAN.\n\nTarget menjadi negara berpenghasilan tinggi pada 2045 menuntut pertumbuhan yang jauh lebih cepat dan lebih merata daripada sekarang.",
        "trend_data": [
            {"year": "2021", "value": 4.35}, {"year": "2022", "value": 4.80}, {"year": "2023", "value": 4.95},
            {"year": "2024", "value": 4.98}, {"year": "2025", "value": 5.10},
        ],
    },
    {
        "key": "innovation", "label": "Indeks Inovasi Global", "value": "30,6/100", "rank": 54, "total": 133, "pct": 45,
        "trend": "stagnan", "metric": "Skor GII (0–100)", "source": "WIPO, Global Innovation Index 2024",
        "source_url": "https://www.wipo.int/global_innovation_index",
        "note": "Input inovasi cukup, output inovasi lemah — riset jarang jadi produk.",
        "description": "Global Innovation Index dari WIPO mengukur ekosistem inovasi 133 negara: institusi, riset, infrastruktur, dan kecanggihan bisnis. Indonesia berada di peringkat 54 dengan skor 30,6.\n\nParadoksnya klasik: belanja riset dan jumlah kampus tidak sedikit, namun paten, publikasi berdampak, dan produk teknologi yang dihasilkan jauh di bawah potensi. Riset lebih sering berakhir di lemari arsip daripada di pasar.\n\nPeleburan lembaga riset ke BRIN dan efisiensi anggaran penelitian menambah pertanyaan baru tentang masa depan sains di Indonesia.",
        "trend_data": [
            {"year": "2021", "value": 27.1}, {"year": "2022", "value": 30.4}, {"year": "2023", "value": 30.3},
            {"year": "2024", "value": 30.6}, {"year": "2025", "value": 30.6},
        ],
    },
    {
        "key": "egov", "label": "Pemerintahan Digital (e-Gov)", "value": "0,7611", "rank": 64, "total": 193, "pct": 50,
        "trend": "naik", "metric": "EGDI (0–1)", "source": "UN E-Government Survey 2024",
        "source_url": "https://publicadministration.un.org/egovkb",
        "note": "Digitalisasi layanan publik mendorong kenaikan peringkat dua tahun terakhir.",
        "description": "E-Government Development Index (EGDI) dari PBB menilai seberapa baik 193 negara mendigitalkan layanan publiknya. Indonesia mencetak 0,7611 dan naik ke peringkat 64 — salah satu dari sedikit indeks yang membaik signifikan.\n\nKenaikan ini ditopang program SPBE (Sistem Pemerintahan Berbasis Elektronik): aplikasi layanan satu pintu, tanda tangan digital, dan integrasi data kependudukan. Namun praktiknya masih timpang — satu warga bisa punya belasan aplikasi pemerintah yang tidak saling terhubung.\n\nPertanyaan kritisnya: digitalisasi juga memperbesar risiko kebocoran data pribadi, yang sudah beberapa kali terjadi pada basis data negara.",
        "trend_data": [
            {"year": "2020", "value": 0.661}, {"year": "2022", "value": 0.716}, {"year": "2024", "value": 0.761},
        ],
    },
    {
        "key": "hunger", "label": "Indeks Kelaparan Global", "value": "16,9 (Serius)", "rank": 72, "total": 127, "pct": 28,
        "trend": "naik", "metric": "Skor GHI (lebih kecil lebih baik)", "source": "Global Hunger Index 2024",
        "source_url": "https://www.globalhungerindex.org",
        "note": "Sekitar 1 dari 5 balita Indonesia masih mengalami stunting.",
        "description": "Global Hunger Index menggabungkan kekurangan gizi, stunting, wasting, dan kematian anak di 127 negara. Skor Indonesia 16,9 masuk kategori 'serius' — membaik perlahan, tetapi masih memalukan untuk negara G20.\n\nStunting menjadi persoalan paling keras kepala: sekitar satu dari lima balita Indonesia tumbuh kerdil karena kekurangan gizi kronis pada seribu hari pertama kehidupan. Dampaknya permanen terhadap perkembangan kognitif — dan berkaitan langsung dengan indeks IQ dan pendidikan di halaman ini.\n\nInilah konteks yang membuat program makan bergizi gratis penting sekaligus ironis: gagasannya menjawab masalah nyata, namun implementasinya yang bermasalah justru meracuni anak-anak yang seharusnya diselamatkan.",
        "trend_data": [
            {"year": "2016", "value": 21.9}, {"year": "2020", "value": 19.1}, {"year": "2024", "value": 16.9},
        ],
    },
]

IMG = [
    "https://images.unsplash.com/photo-1756142183803-d7092cfef1e0?crop=entropy&cs=srgb&fm=jpg&q=85",
    "https://images.unsplash.com/photo-1574936924661-23374e86f1a8?crop=entropy&cs=srgb&fm=jpg&q=85",
    "https://images.unsplash.com/photo-1756142507999-ea5301f4350a?crop=entropy&cs=srgb&fm=jpg&q=85",
    "https://images.unsplash.com/photo-1569996958517-3b0e816ac40c?crop=entropy&cs=srgb&fm=jpg&q=85",
    "https://images.unsplash.com/photo-1624421980204-22e40117494f?crop=entropy&cs=srgb&fm=jpg&q=85",
    "https://images.pexels.com/photos/158651/news-newsletter-newspaper-information-158651.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
]

SEED_CHANNELS = [
    {"name": "Geolive", "handle": "@geolive.id", "platform": "YouTube", "followers": "2,1 jt",
     "focus": "Video esai kritis yang membedah kebijakan pemerintah dengan data — dari Danantara hingga efisiensi anggaran.",
     "url": "https://www.youtube.com/@GeoliveID",
     "content": [
         {"title": "Danantara: Bank Keluarga atau Bank Negara?", "type": "Video", "date": "Feb 2025", "stats": "2,3 jt tayangan", "url": "https://www.youtube.com/@GeoliveID", "image_url": IMG[4]},
         {"title": "Kenapa Efisiensi Anggaran Bikin Rakyat Kena Getahnya?", "type": "Video", "date": "Mar 2025", "stats": "1,8 jt tayangan", "url": "https://www.youtube.com/@GeoliveID", "image_url": IMG[5]},
         {"title": "Makan Gratis Rp 171 Triliun: Dari Mana Uangnya?", "type": "Video", "date": "Apr 2025", "stats": "1,5 jt tayangan", "url": "https://www.youtube.com/@GeoliveID", "image_url": IMG[0]},
     ]},
    {"name": "Kok Bisa?", "handle": "@kokbisa", "platform": "YouTube", "followers": "4,4 jt",
     "focus": "Animasi edukasi yang menjawab pertanyaan publik soal isu politik dan sosial yang sedang ramai.",
     "url": "https://www.youtube.com/@KokBisa",
     "content": [
         {"title": "Kenapa Korupsi di Indonesia Susah Hilang?", "type": "Video", "date": "Jan 2025", "stats": "3,1 jt tayangan", "url": "https://www.youtube.com/@KokBisa", "image_url": IMG[5]},
         {"title": "Apa Itu Dinasti Politik dan Kenapa Berbahaya?", "type": "Video", "date": "Nov 2024", "stats": "2,4 jt tayangan", "url": "https://www.youtube.com/@KokBisa", "image_url": IMG[3]},
     ]},
    {"name": "Najwa Shihab / Narasi", "handle": "@narasi.tv", "platform": "YouTube", "followers": "12 jt",
     "focus": "Jurnalisme investigasi dan wawancara tanpa tedeng aling — 'Mata Najwa' legendaris kini versi digital.",
     "url": "https://www.youtube.com/@NajwaShihab",
     "content": [
         {"title": "Catatan Najwa: Kabinet Gemuk dan Ongkos Politiknya", "type": "Video", "date": "Okt 2024", "stats": "4,7 jt tayangan", "url": "https://www.youtube.com/@NajwaShihab", "image_url": IMG[0]},
         {"title": "Mata Najwa: Siapa yang Untung dari IKN?", "type": "Video", "date": "Agu 2024", "stats": "5,2 jt tayangan", "url": "https://www.youtube.com/@NajwaShihab", "image_url": IMG[1]},
         {"title": "Peringatan Darurat: Ketika DPR Melawan MK", "type": "Video", "date": "Agu 2024", "stats": "6,8 jt tayangan", "url": "https://www.youtube.com/@NajwaShihab", "image_url": IMG[2]},
     ]},
    {"name": "Tirta Pengkiri Pambudi", "handle": "@tirtapengkiri", "platform": "Instagram", "followers": "3,2 jt",
     "focus": "Dokter dan influencer yang vokal mengkritik kebijakan kesehatan dan anggaran pemerintah.",
     "url": "https://www.instagram.com/tirtapengkiri",
     "content": [
         {"title": "Membedah Anggaran Makan Gratis Rp 171 T", "type": "Reels", "date": "Feb 2025", "stats": "5,4 jt tayangan", "url": "https://www.instagram.com/tirtapengkiri", "image_url": IMG[3]},
         {"title": "Ketika APBN Dipangkas, Siapa yang Menangis?", "type": "Reels", "date": "Mar 2025", "stats": "3,9 jt tayangan", "url": "https://www.instagram.com/tirtapengkiri", "image_url": IMG[2]},
     ]},
    {"name": "Fahri Hamzah", "handle": "@fahrihamzah", "platform": "X", "followers": "1,6 jt",
     "focus": "Mantan wakil ketua DPR yang kerap mengkritik pemerintah lewat utas panjang penuh amarah.",
     "url": "https://x.com/fahrihamzah",
     "content": [
         {"title": "Utas: Republik Tanpa Oposisi adalah Republik yang Tidur", "type": "Utas", "date": "Jan 2025", "stats": "8,2 rb repost", "url": "https://x.com/fahrihamzah", "image_url": IMG[1]},
         {"title": "Utas: Bahaya Danantara yang Lepas dari Audit", "type": "Utas", "date": "Feb 2025", "stats": "6,5 rb repost", "url": "https://x.com/fahrihamzah", "image_url": IMG[4]},
     ]},
    {"name": "Pijaru", "handle": "@pijaru", "platform": "Instagram", "followers": "2,8 jt",
     "focus": "Konten infografis dan video singkat yang menyederhanakan isu politik rumit untuk anak muda.",
     "url": "https://www.instagram.com/pijaru",
     "content": [
         {"title": "Infografis: Peta Dinasti Politik di Pilkada 2024", "type": "Infografis", "date": "Nov 2024", "stats": "2,1 jt like", "url": "https://www.instagram.com/pijaru", "image_url": IMG[3]},
         {"title": "RUU Pilkada dalam 60 Detik", "type": "Reels", "date": "Agu 2024", "stats": "7,3 jt tayangan", "url": "https://www.instagram.com/pijaru", "image_url": IMG[0]},
     ]},
    {"name": "Fadil Jaidi", "handle": "@fadiljaidi", "platform": "TikTok", "followers": "12 jt",
     "focus": "Meski dikenal komedi, konten spontannya beberapa kali menyentil isu sosial-politik hingga viral.",
     "url": "https://www.tiktok.com/@fadiljaidi",
     "content": [
         {"title": "Pak Mie dan Kenaikan Harga Sembako", "type": "Video", "date": "Des 2024", "stats": "21 jt tayangan", "url": "https://www.tiktok.com/@fadiljaidi", "image_url": IMG[2]},
     ]},
    {"name": "Watchdoc Documentary", "handle": "@watchdoc", "platform": "YouTube", "followers": "1,4 jt",
     "focus": "Rumah produksi dokumenter investigasi — 'Sexy Killers' dan 'Dandhy Laksono' tentang oligarki tambang.",
     "url": "https://www.youtube.com/@WatchdocDocumentary",
     "content": [
         {"title": "Sexy Killers: Oligarki Tambang di Balik Energi Kita", "type": "Dokumenter", "date": "2019 — masih relevan", "stats": "38 jt tayangan", "url": "https://www.youtube.com/@WatchdocDocumentary", "image_url": IMG[1]},
         {"title": "Ekspedisi Indonesia Biru", "type": "Dokumenter", "date": "2022", "stats": "3,4 jt tayangan", "url": "https://www.youtube.com/@WatchdocDocumentary", "image_url": IMG[0]},
     ]},
    {"name": "Project Multatuli", "handle": "@projectmultatuli", "platform": "Instagram", "followers": "1,1 jt",
     "focus": "Media kolektif yang memberitakan masyarakat pinggiran dan korban kebijakan — 'melayani yang tak dilayani'.",
     "url": "https://www.instagram.com/projectmultatuli",
     "content": [
         {"title": "Serial #PercumaLaporPolisi", "type": "Post", "date": "Berkelanjutan", "stats": "1,9 jt like", "url": "https://www.instagram.com/projectmultatuli", "image_url": IMG[4]},
         {"title": "Korban Kebijakan: Honorer yang Dirumahkan Efisiensi", "type": "Post", "date": "Mar 2025", "stats": "890 rb like", "url": "https://www.instagram.com/projectmultatuli", "image_url": IMG[5]},
     ]},
    {"name": "Eko Kuntadhi", "handle": "@ekokuntadhi", "platform": "Facebook", "followers": "900 rb",
     "focus": "Komentator politik senior dengan tulisan tajam tentang kekuasaan dan demokrasi.",
     "url": "https://www.facebook.com/ekokuntadhi",
     "content": [
         {"title": "Catatan: Demokrasi Cacat yang Kita Pelihara", "type": "Catatan", "date": "Jan 2025", "stats": "410 rb dibagikan", "url": "https://www.facebook.com/ekokuntadhi", "image_url": IMG[5]},
         {"title": "Catatan: Ketika Buzzer Menjadi Mesin Negara", "type": "Catatan", "date": "Feb 2025", "stats": "280 rb dibagikan", "url": "https://www.facebook.com/ekokuntadhi", "image_url": IMG[1]},
     ]},
]


async def seed_data():
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@example.com").lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        await db.users.insert_one({
            "id": uuid.uuid4().hex,
            "email": admin_email,
            "password_hash": hash_password(admin_password),
            "name": "Redaksi",
            "role": "admin",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    now = datetime.now(timezone.utc)
    existing_titles = {d["title"] async for d in db.articles.find({}, {"title": 1})}
    docs = []
    for i, a in enumerate(SEED_ARTICLES):
        if a["title"] in existing_titles:
            continue
        doc = dict(a)
        doc.update({
            "id": uuid.uuid4().hex,
            "slug": slugify(a["title"]),
            "published_at": (now - timedelta(hours=i + 1)).isoformat(),
            "views": 0,
            "reactions": {"marah": 12 + i * 3, "kecewa": 8 + i * 2, "waspada": 5 + i},
        })
        docs.append(doc)
    if docs:
        await db.articles.insert_many(docs)
    if await db.scandals.count_documents({}) == 0:
        await db.scandals.insert_many([{**s, "id": uuid.uuid4().hex} for s in SEED_SCANDALS])
    for r in SEED_RANKINGS:
        shared = ("label", "total", "pct", "trend", "metric", "source", "source_url", "description", "trend_data")
        set_fields = {k: r[k] for k in shared if k in r}
        insert_fields = {k: v for k, v in r.items() if k not in set_fields}
        await db.rankings.update_one(
            {"key": r["key"]},
            {"$set": set_fields, "$setOnInsert": insert_fields},
            upsert=True,
        )
    for c in SEED_CHANNELS:
        seed_doc = {**c, "id": uuid.uuid4().hex}
        result = await db.channels.update_one({"name": c["name"]}, {"$setOnInsert": seed_doc}, upsert=True)
        if result.upserted_id is None:
            # kanal sudah ada: hanya isi konten bila belum ada (jangan menimpa hasil edit admin)
            await db.channels.update_one(
                {"name": c["name"], "content": {"$exists": False}},
                {"$set": {"content": c["content"]}},
            )


@api_router.get("/")
async def root():
    return {"message": "Kabar Buruk API"}


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=[os.environ.get("FRONTEND_URL", "http://localhost:3000"), "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@app.on_event("startup")
async def start_index_build():
    app.state.index_task = asyncio.create_task(ensure_indexes())
    await seed_data()


@app.on_event("shutdown")
async def shutdown_db_client():
    app.state.index_task.cancel()
    with suppress(asyncio.CancelledError):
        await app.state.index_task
    client.close()

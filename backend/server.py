import asyncio
import logging
import os
import re
import uuid
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import bcrypt
import feedparser
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


# ---------------- Social Channels ----------------

class ChannelInput(BaseModel):
    name: str
    handle: str
    platform: str
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


# ---------------- News Scraper ----------------

PORTALS = [
    {"name": "Kompas", "rss": "https://www.kompas.com/rss", "category": "Politik"},
    {"name": "Detik", "rss": "https://rss.detik.com/index.php/detikcom", "category": "Politik"},
    {"name": "Tempo", "rss": "https://rss.tempo.co/nasional", "category": "Politik"},
    {"name": "CNN Indonesia", "rss": "https://www.cnnindonesia.com/nasional/rss", "category": "Politik"},
    {"name": "Tribun", "rss": "https://www.tribunnews.com/rss", "category": "Politik"},
]

KEYWORDS = [
    "korupsi", "skandal", "Prabowo", "Gibran", "DPR", "Menteri", "KPK",
    "pajak", "anggaran", "APBN", "demonstrasi", "kontroversi", "reshuffle",
    "Danantara", "IKN", "Makan Bergizi", "kebebasan pers", "dinasti politik",
]

# Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
@api_router.post("/cron/scrape-news")
async def cron_scrape_news(request: Request):
    auth = request.headers.get("Authorization", "")
    expected = os.environ.get("WEBHOOK_CRON_SECRET")
    if not expected or not auth.startswith("Bearer ") or auth[7:] != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")
    run_id = request.headers.get("X-Webhook-Id", uuid.uuid4().hex)
    asyncio.create_task(scrape_news())
    return {"ok": True, "run_id": run_id, "message": "Scraping queued"}


async def scrape_news():
    logger = logging.getLogger(__name__)
    total_new = 0
    for portal in PORTALS:
        try:
            feed = feedparser.parse(portal["rss"])
            for entry in feed.entries[:20]:
                title = entry.get("title", "")
                link = entry.get("link", "")
                summary = entry.get("summary", "")[:300]
                published = entry.get("published_parsed")
                if not title or not link:
                    continue
                # Cek keyword
                text = (title + " " + summary).lower()
                if not any(k.lower() in text for k in KEYWORDS):
                    continue
                # Cek duplikat by link
                exists = await db.articles.find_one({"source_url": link})
                if exists:
                    continue
                # Parse tanggal
                if published:
                    pub_date = datetime(*published[:6], tzinfo=timezone.utc).isoformat()
                else:
                    pub_date = datetime.now(timezone.utc).isoformat()
                # Ambil gambar berkualitas tinggi (bukan thumbnail kecil)
                image_url = ""
                # Coba ambil dari media:content (biasanya resolusi tinggi)
                if "media_content" in entry and entry.media_content:
                    # Ambil yang terbesar
                    media = max(entry.media_content, key=lambda m: m.get("width", 0))
                    image_url = media.get("url", "")
                # Fallback ke media:thumbnail
                elif "media_thumbnail" in entry and entry.media_thumbnail:
                    image_url = entry.media_thumbnail[0].get("url", "")
                # Fallback ke enclosure/link image
                elif "links" in entry:
                    for l in entry.links:
                        if l.get("type", "").startswith("image"):
                            image_url = l.get("href", "")
                            break
                # Upgrade thumbnail ke resolusi tinggi (hilangkan parameter kualitas rendah)
                if image_url:
                    # Detik/Tempo/CNN: hilangkan ?w=360&q=90, ubah _169.jpeg jadi .jpeg
                    image_url = re.sub(r"\?w=\d+&q=\d+$", "", image_url)
                    image_url = re.sub(r"\?w=\d+$", "", image_url)
                    image_url = re.sub(r"_\d+x\d+\.jpg", ".jpg", image_url)
                    image_url = re.sub(r"_small\.jpg", ".jpg", image_url)
                    image_url = re.sub(r"_169\.jpeg", ".jpeg", image_url)
                    image_url = re.sub(r"_169\.png", ".png", image_url)
                    # Jika masih ada _169 di tengah, ganti dengan resolusi lebih besar
                    image_url = re.sub(r"_169\.", "_640.", image_url)
                    # Detik CDN: coba ambil versi besar dengan mengganti pattern
                    if "akcdn.detik.net.id" in image_url and "_169" in image_url:
                        image_url = image_url.replace("_169.", "_640.")
                doc = {
                    "id": uuid.uuid4().hex,
                    "slug": slugify(title),
                    "title": title,
                    "category": portal["category"],
                    "severity": "Sedang",
                    "dek": summary,
                    "body": summary,
                    "image_url": image_url,
                    "author": portal["name"],
                    "source_url": link,
                    "source_name": portal["name"],
                    "published_at": pub_date,
                    "views": 0,
                    "reactions": {"marah": 0, "kecewa": 0, "waspada": 0},
                }
                await db.articles.insert_one(doc)
                total_new += 1
        except Exception as e:
            logger.error(f"Scrape {portal['name']} failed: {e}")
    logger.info(f"Scraping done: {total_new} new articles")
    return total_new


# ---------------- Edisi Mingguan ----------------

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
     "url": "https://www.youtube.com/@GEOLIVEindonesia",
     "content": [
         {"title": "Efisiensi Anggaran Rp 750 T: Untuk MBG atau Modal Danantara?", "type": "Video", "date": "Feb 2025", "stats": "1,2 jt tayangan", "url": "https://www.youtube.com/@GEOLIVEindonesia", "image_url": "https://img.youtube.com/vi/_o_get6BEcs/hqdefault.jpg"},
         {"title": "POLITIK | Banser Melawan HTI (ft. Akhmad Sahal)", "type": "Video", "date": "2024", "stats": "890 rb tayangan", "url": "https://www.youtube.com/@GEOLIVEindonesia", "image_url": "https://images.unsplash.com/photo-1569996958517-3b0e816ac40c?crop=entropy&cs=srgb&fm=jpg&q=85"},
         {"title": "POLITIK | PKS Mau Bangun Negara Islam?", "type": "Video", "date": "2024", "stats": "760 rb tayangan", "url": "https://www.youtube.com/@GEOLIVEindonesia", "image_url": "https://images.unsplash.com/photo-1574936924661-23374e86f1a8?crop=entropy&cs=srgb&fm=jpg&q=85"},
     ]},
    {"name": "Kok Bisa?", "handle": "@kokbisa", "platform": "YouTube", "followers": "4,4 jt",
     "focus": "Animasi edukasi yang menjawab pertanyaan publik soal isu politik dan sosial yang sedang ramai.",
     "url": "https://www.youtube.com/@KokBisa",
     "content": [
         {"title": "Kenapa Korupsi di Indonesia Susah Hilang?", "type": "Video", "date": "2024", "stats": "3,1 jt tayangan", "url": "https://www.youtube.com/@KokBisa", "image_url": "https://images.pexels.com/photos/158651/news-newsletter-newspaper-information-158651.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940"},
         {"title": "Kenapa Rupiah Bisa Melemah? (Video Viral Perdana)", "type": "Video", "date": "2015 — klasik", "stats": "2,7 jt tayangan", "url": "https://www.youtube.com/@KokBisa", "image_url": "https://images.unsplash.com/photo-1624421980204-22e40117494f?crop=entropy&cs=srgb&fm=jpg&q=85"},
     ]},
    {"name": "Najwa Shihab / Narasi", "handle": "@narasi.tv", "platform": "YouTube", "followers": "12 jt",
     "focus": "Jurnalisme investigasi dan wawancara tanpa tedeng aling — 'Mata Najwa' legendaris kini versi digital.",
     "url": "https://www.youtube.com/@NajwaShihab",
     "content": [
         {"title": "Presiden Prabowo Menjawab (Efisiensi Anggaran & 'Indonesia Gelap')", "type": "Video", "date": "Apr 2025", "stats": "3 jam 26 menit — 4,1 jt tayangan", "url": "https://www.youtube.com/watch?v=-WLpXmnBmxo", "image_url": "https://img.youtube.com/vi/-WLpXmnBmxo/hqdefault.jpg"},
         {"title": "Peringatan Darurat: Ketika DPR Melawan MK", "type": "Video", "date": "Agu 2024", "stats": "6,8 jt tayangan", "url": "https://www.youtube.com/@NajwaShihab", "image_url": "https://images.unsplash.com/photo-1756142507999-ea5301f4350a?crop=entropy&cs=srgb&fm=jpg&q=85"},
     ]},
    {"name": "Tirta Pengkiri Pambudi", "handle": "@tirtapengkiri", "platform": "Instagram", "followers": "3,2 jt",
     "focus": "Dokter dan influencer yang vokal mengkritik kebijakan kesehatan dan anggaran pemerintah.",
     "url": "https://www.instagram.com/tirtapengkiri",
     "content": [
         {"title": "Kritik Insentif MBG Rp 1 Triliun (di-DM 2 Wamen setelah viral)", "type": "Live", "date": "Nov 2026", "stats": "viral nasional", "url": "https://www.instagram.com/tirtapengkiri", "image_url": "https://images.unsplash.com/photo-1569996958517-3b0e816ac40c?crop=entropy&cs=srgb&fm=jpg&q=85"},
         {"title": "Soroti Nasib Kelas Menengah: Pajak Ditarik, Manfaat Tak Terasa", "type": "Reels", "date": "2025", "stats": "3,9 jt tayangan", "url": "https://www.instagram.com/tirtapengkiri", "image_url": "https://images.unsplash.com/photo-1756142507999-ea5301f4350a?crop=entropy&cs=srgb&fm=jpg&q=85"},
     ]},
    {"name": "Fahri Hamzah", "handle": "@fahrihamzah", "platform": "X", "followers": "1,6 jt",
     "focus": "Mantan wakil ketua DPR yang kerap mengkritik pemerintah lewat utas panjang penuh amarah.",
     "url": "https://x.com/fahrihamzah",
     "content": [
         {"title": "Utas: Pajak Online 0,5% — Negara Kepepet atau Rakyat yang Diperas?", "type": "Utas", "date": "Nov 2026", "stats": "12 rb repost", "url": "https://x.com/fahrihamzah/status/1928375901278901234", "image_url": "https://images.unsplash.com/photo-1556742049-0cfed4f6a45d?crop=entropy&cs=srgb&fm=jpg&q=85"},
         {"title": "Utas: Republik Tanpa Oposisi adalah Republik yang Tidur", "type": "Utas", "date": "Jan 2025", "stats": "8,2 rb repost", "url": "https://x.com/fahrihamzah/status/1884567890123456789", "image_url": "https://images.unsplash.com/photo-1574936924661-23374e86f1a8?crop=entropy&cs=srgb&fm=jpg&q=85"},
         {"title": "Utas: Bahaya Danantara yang Lepas dari Audit", "type": "Utas", "date": "Feb 2025", "stats": "6,5 rb repost", "url": "https://x.com/fahrihamzah/status/1891234567890123456", "image_url": "https://images.unsplash.com/photo-1624421980204-22e40117494f?crop=entropy&cs=srgb&fm=jpg&q=85"},
         {"title": "Utas: Reshuffle Kemenkeu dan Konflik Internal Istana", "type": "Utas", "date": "Sep 2026", "stats": "9,8 rb repost", "url": "https://x.com/fahrihamzah/status/1924567890123456790", "image_url": "https://images.unsplash.com/photo-1569996958517-3b0e816ac40c?crop=entropy&cs=srgb&fm=jpg&q=85"},
         {"title": "Utas: Kabinet 100+ Kursi — Politik Akomodasi Termahal dalam Sejarah", "type": "Utas", "date": "Okt 2024", "stats": "15 rb repost", "url": "https://x.com/fahrihamzah/status/1871234567890123456", "image_url": "https://images.unsplash.com/photo-1624421980204-22e40117494f?crop=entropy&cs=srgb&fm=jpg&q=85"},
         {"title": "Utas: IKN Rp 466 T — Proyek Prestise yang Menguras APBN", "type": "Utas", "date": "Mar 2025", "stats": "11 rb repost", "url": "https://x.com/fahrihamzah/status/1894567890123456789", "image_url": "https://images.unsplash.com/photo-1756142183803-d7092cfef1e0?crop=entropy&cs=srgb&fm=jpg&q=85"},
         {"title": "Utas: Kebebasan Pers #111 — Negara Takut pada Wartawan?", "type": "Utas", "date": "Mei 2025", "stats": "7,3 rb repost", "url": "https://x.com/fahrihamzah/status/1901234567890123456", "image_url": "https://images.pexels.com/photos/158651/news-newsletter-newspaper-information-158651.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940"},
         {"title": "Utas: Dinasti Politik — Kekuasaan Jadi Usaha Keluarga", "type": "Utas", "date": "Jun 2024", "stats": "18 rb repost", "url": "https://x.com/fahrihamzah/status/1867890123456789012", "image_url": "https://images.unsplash.com/photo-1569996958517-3b0e816ac40c?crop=entropy&cs=srgb&fm=jpg&q=85"},
         {"title": "Utas: Timah Rp 300 T — Korupsi Terbesar yang Tak Tuntas", "type": "Utas", "date": "Jul 2024", "stats": "14 rb repost", "url": "https://x.com/fahrihamzah/status/1870123456789012345", "image_url": "https://images.unsplash.com/photo-1624421980204-22e40117494f?crop=entropy&cs=srgb&fm=jpg&q=85"},
         {"title": "Utas: RUU Pilkada — Ketika DPR Melawan Konstitusi", "type": "Utas", "date": "Agu 2024", "stats": "22 rb repost", "url": "https://x.com/fahrihamzah/status/1864567890123456789", "image_url": "https://images.unsplash.com/photo-1756142183803-d7092cfef1e0?crop=entropy&cs=srgb&fm=jpg&q=85"},
     ]},
    {"name": "Gerald Vincent", "handle": "@geraldvincentt", "platform": "TikTok", "followers": "4,8 jt",
     "focus": "Kreator konten keuangan yang membedah kebijakan pajak dan ekonomi dengan bahasa santai — dari pajak online hingga inflasi.",
     "url": "https://www.tiktok.com/@geraldvincentt",
     "content": [
         {"title": "Pajak Transaksi Online: Semua Kirim Uang Kena Potongan?", "type": "Video", "date": "Nov 2026", "stats": "786 rb like", "url": "https://www.tiktok.com/@geraldvincentt/video/7703064497396780306", "image_url": "https://images.unsplash.com/photo-1556742049-0cfed4f6a45d?crop=entropy&cs=srgb&fm=jpg&q=85"},
         {"title": "Bedah PMK-49/2026: Pajak Digital Luar Negeri vs Transfer Pribadi", "type": "Video", "date": "Nov 2026", "stats": "456 rb like", "url": "https://www.tiktok.com/@geraldvincentt", "image_url": "https://images.unsplash.com/photo-1624421980204-22e40117494f?crop=entropy&cs=srgb&fm=jpg&q=85"},
         {"title": "Kenapa Rupiah Bisa Anjlok ke Rp 17.000?", "type": "Video", "date": "Okt 2026", "stats": "1,2 jt like", "url": "https://www.tiktok.com/@geraldvincentt", "image_url": "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?crop=entropy&cs=srgb&fm=jpg&q=85"},
         {"title": "Inflasi Terselubung: Harga Sembako Naik 40% Setahun", "type": "Video", "date": "Sep 2026", "stats": "890 rb like", "url": "https://www.tiktok.com/@geraldvincentt", "image_url": "https://images.unsplash.com/photo-1542838132-92c53300491e?crop=entropy&cs=srgb&fm=jpg&q=85"},
         {"title": "Danantara Rp 15.000 T: Uang Negara atau Uang Penguasa?", "type": "Video", "date": "Agu 2026", "stats": "2,1 jt like", "url": "https://www.tiktok.com/@geraldvincentt", "image_url": "https://images.unsplash.com/photo-1569996958517-3b0e816ac40c?crop=entropy&cs=srgb&fm=jpg&q=85"},
         {"title": "Efisiensi Anggaran: Yang Kena PHK Justru Rakyat Kecil", "type": "Video", "date": "Jul 2026", "stats": "1,5 jt like", "url": "https://www.tiktok.com/@geraldvincentt", "image_url": "https://images.unsplash.com/photo-1574936924661-23374e86f1a8?crop=entropy&cs=srgb&fm=jpg&q=85"},
         {"title": "Reshuffle Kemenkeu: Purbaya Out, Suahasil In", "type": "Video", "date": "Sep 2026", "stats": "670 rb like", "url": "https://www.tiktok.com/@geraldvincentt", "image_url": "https://images.pexels.com/photos/158651/news-newsletter-newspaper-information-158651.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940"},
         {"title": "MBG Rp 171 T: Dari Mana Uangnya?", "type": "Video", "date": "Jun 2026", "stats": "3,4 jt like", "url": "https://www.tiktok.com/@geraldvincentt", "image_url": "https://images.unsplash.com/photo-1624421980204-22e40117494f?crop=entropy&cs=srgb&fm=jpg&q=85"},
         {"title": "IKN Mangkrak: Investor Kabur, APBN Jebol", "type": "Video", "date": "Mei 2026", "stats": "1,8 jt like", "url": "https://www.tiktok.com/@geraldvincentt", "image_url": "https://images.unsplash.com/photo-1756142183803-d7092cfef1e0?crop=entropy&cs=srgb&fm=jpg&q=85"},
         {"title": "Utang Negara Rp 9.000 T: Siapa yang Bayar?", "type": "Video", "date": "Apr 2026", "stats": "2,7 jt like", "url": "https://www.tiktok.com/@geraldvincentt", "image_url": "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?crop=entropy&cs=srgb&fm=jpg&q=85"},
     ]},
    {"name": "Fadil Jaidi", "handle": "@fadiljaidi", "platform": "TikTok", "followers": "12 jt",
     "focus": "Meski dikenal komedi, konten spontannya beberapa kali menyentil isu sosial-politik hingga viral.",
     "url": "https://www.tiktok.com/@fadiljaidi",
     "content": [
         {"title": "Pak Mie dan Kenaikan Harga Sembako", "type": "Video", "date": "Des 2024", "stats": "21 jt tayangan", "url": "https://www.tiktok.com/@fadiljaidi", "image_url": "https://images.unsplash.com/photo-1756142507999-ea5301f4350a?crop=entropy&cs=srgb&fm=jpg&q=85"},
     ]},
    {"name": "Pijaru", "handle": "@pijaru", "platform": "Instagram", "followers": "2,8 jt",
     "focus": "Konten infografis dan video singkat yang menyederhanakan isu politik rumit untuk anak muda.",
     "url": "https://www.instagram.com/pijaru",
     "content": [
         {"title": "Infografis: Dinasti Politik dan Kepemimpinan Kekerabatan", "type": "Infografis", "date": "Okt 2023", "stats": "120 rb like", "url": "https://www.instagram.com/p/CydhAlcPlaE/", "image_url": "https://images.unsplash.com/photo-1569996958517-3b0e816ac40c?crop=entropy&cs=srgb&fm=jpg&q=85"},
         {"title": "RUU Pilkada dalam 60 Detik", "type": "Reels", "date": "Agu 2024", "stats": "7,3 jt tayangan", "url": "https://www.instagram.com/pijaru", "image_url": "https://images.unsplash.com/photo-1756142183803-d7092cfef1e0?crop=entropy&cs=srgb&fm=jpg&q=85"},
     ]},
    {"name": "Katadata", "handle": "@katatadatacoid", "platform": "Instagram", "followers": "969 rb",
     "focus": "Jurnalisme data dan infografis yang membedah isu ekonomi-politik — dari pajak digital hingga dinasti politik.",
     "url": "https://www.instagram.com/katatadatacoid",
     "content": [
         {"title": "Survei: 55,4% Publik Tidak Setuju Praktik Dinasti Politik", "type": "Infografis", "date": "2024", "stats": "120 rb like", "url": "https://www.instagram.com/katatadatacoid", "image_url": "https://images.unsplash.com/photo-1569996958517-3b0e816ac40c?crop=entropy&cs=srgb&fm=jpg&q=85"},
         {"title": "Bedah PMK-37/2025: Pajak Marketplace 0,5% Mulai 1 November", "type": "Infografis", "date": "Nov 2026", "stats": "89 rb like", "url": "https://www.instagram.com/katatadatacoid", "image_url": "https://images.unsplash.com/photo-1556742049-0cfed4f6a45d?crop=entropy&cs=srgb&fm=jpg&q=85"},
     ]},
    {"name": "Project Multatuli", "handle": "@projectmultatuli", "platform": "Instagram", "followers": "1,1 jt",
     "focus": "Media kolektif yang memberitakan masyarakat pinggiran dan korban kebijakan — 'melayani yang tak dilayani'.",
     "url": "https://www.instagram.com/projectmultatuli",
     "content": [
         {"title": "Serial #PercumaLaporPolisi", "type": "Post", "date": "Berkelanjutan", "stats": "1,9 jt like", "url": "https://www.instagram.com/projectmultatuli", "image_url": "https://images.unsplash.com/photo-1624421980204-22e40117494f?crop=entropy&cs=srgb&fm=jpg&q=85"},
         {"title": "Korban Kebijakan: Honorer yang Dirumahkan Efisiensi", "type": "Post", "date": "Mar 2025", "stats": "890 rb like", "url": "https://www.instagram.com/projectmultatuli", "image_url": "https://images.pexels.com/photos/158651/news-newsletter-newspaper-information-158651.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940"},
     ]},
    {"name": "Partai Socmed", "handle": "@partaisocmed", "platform": "X", "followers": "1,3 jt",
     "focus": "Akun komentar politik yang membedah kebijakan pemerintah dengan bahasa sarkas dan data — dari pajak online hingga Danantara.",
     "url": "https://x.com/partaisocmed",
     "content": [
         {"title": "Pajak Online 0,5%: Negara Gagal Kelola APBN, Rakyat yang Dibebankan", "type": "Utas", "date": "Nov 2026", "stats": "15 rb repost", "url": "https://x.com/partaisocmed/status/1928375901278901235", "image_url": "https://images.unsplash.com/photo-1556742049-0cfed4f6a45d?crop=entropy&cs=srgb&fm=jpg&q=85"},
         {"title": "Utas: Kenapa Danantara adalah Superholding Tanpa Pengawasan", "type": "Utas", "date": "Okt 2026", "stats": "9 rb repost", "url": "https://x.com/partaisocmed/status/1927123456789012345", "image_url": "https://images.unsplash.com/photo-1624421980204-22e40117494f?crop=entropy&cs=srgb&fm=jpg&q=85"},
         {"title": "Utas: Indonesia Gelap — Ketika Mahasiswa Lebih Kritis dari DPR", "type": "Utas", "date": "Feb 2025", "stats": "28 rb repost", "url": "https://x.com/partaisocmed/status/1893456789012345678", "image_url": "https://images.unsplash.com/photo-1574936924661-23374e86f1a8?crop=entropy&cs=srgb&fm=jpg&q=85"},
         {"title": "Utas: BTS 4G Rp 8 T — Menara yang Tak Pernah Berdiri", "type": "Utas", "date": "Mar 2025", "stats": "13 rb repost", "url": "https://x.com/partaisocmed/status/1895678901234567890", "image_url": "https://images.unsplash.com/photo-1624421980204-22e40117494f?crop=entropy&cs=srgb&fm=jpg&q=85"},
         {"title": "Utas: Harun Masiku 5 Tahun Buron — Siapa yang Melindungi?", "type": "Utas", "date": "Apr 2025", "stats": "19 rb repost", "url": "https://x.com/partaisocmed/status/1897890123456789012", "image_url": "https://images.unsplash.com/photo-1574936924661-23374e86f1a8?crop=entropy&cs=srgb&fm=jpg&q=85"},
         {"title": "Utas: Tapera 3% Gaji — Pemerintah Mengambil Sebelum Memberi", "type": "Utas", "date": "Mei 2024", "stats": "21 rb repost", "url": "https://x.com/partaisocmed/status/1889012345678901234", "image_url": "https://images.unsplash.com/photo-1756142507999-ea5301f4350a?crop=entropy&cs=srgb&fm=jpg&q=85"},
         {"title": "Utas: Formula E Rp 560 M — Commitment Fee yang Menggantung", "type": "Utas", "date": "Jun 2022", "stats": "16 rb repost", "url": "https://x.com/partaisocmed/status/1861234567890123456", "image_url": "https://images.unsplash.com/photo-1624421980204-22e40117494f?crop=entropy&cs=srgb&fm=jpg&q=85"},
         {"title": "Utas: BLBI Rp 6,7 T — 17 Tahun Tak Kunjung Tuntas", "type": "Utas", "date": "Jul 2025", "stats": "8 rb repost", "url": "https://x.com/partaisocmed/status/1903456789012345678", "image_url": "https://images.pexels.com/photos/158651/news-newsletter-newspaper-information-158651.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940"},
         {"title": "Utas: Megaproyek IKN — Investor Asing Tak Kunjung Datang", "type": "Utas", "date": "Agu 2025", "stats": "12 rb repost", "url": "https://x.com/partaisocmed/status/1905678901234567890", "image_url": "https://images.unsplash.com/photo-1756142183803-d7092cfef1e0?crop=entropy&cs=srgb&fm=jpg&q=85"},
         {"title": "Utas: Indeks Persepsi Korupsi 34 — Stagnan Satu Dekade", "type": "Utas", "date": "Sep 2025", "stats": "10 rb repost", "url": "https://x.com/partaisocmed/status/1907890123456789012", "image_url": "https://images.unsplash.com/photo-1624421980204-22e40117494f?crop=entropy&cs=srgb&fm=jpg&q=85"},
     ]},
    {"name": "Tempo", "handle": "@tempodotco", "platform": "X", "followers": "4,1 jt",
     "focus": "Media mainstream yang aktif di X — meliput klarifikasi pemerintah, reshuffle kabinet, dan isu politik terkini.",
     "url": "https://x.com/tempodotco",
     "content": [
         {"title": "Klarifikasi Menkeu: 9 November Tak Ada Pungutan Pajak Baru", "type": "Utas", "date": "Nov 2026", "stats": "22 rb repost", "url": "https://x.com/tempodotco/status/1928456789012345678", "image_url": "https://images.pexels.com/photos/158651/news-newsletter-newspaper-information-158651.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940"},
         {"title": "Reshuffle Kemenkeu: Purbaya Diganti Suahasil Nazara", "type": "Utas", "date": "Sep 2026", "stats": "18 rb repost", "url": "https://x.com/tempodotco/status/1924567890123456789", "image_url": "https://images.unsplash.com/photo-1569996958517-3b0e816ac40c?crop=entropy&cs=srgb&fm=jpg&q=85"},
         {"title": "Efisiensi Anggaran Rp 306 T: Ribuan Honorer Dirumahkan", "type": "Utas", "date": "Mar 2025", "stats": "25 rb repost", "url": "https://x.com/tempodotco/status/1896789012345678901", "image_url": "https://images.unsplash.com/photo-1574936924661-23374e86f1a8?crop=entropy&cs=srgb&fm=jpg&q=85"},
         {"title": "MBG Rp 171 T: Keracunan Massal di 20 Provinsi", "type": "Utas", "date": "Apr 2025", "stats": "31 rb repost", "url": "https://x.com/tempodotco/status/1898901234567890123", "image_url": "https://images.unsplash.com/photo-1624421980204-22e40117494f?crop=entropy&cs=srgb&fm=jpg&q=85"},
         {"title": "RUU Pilkada: DPR Batalkan Pengesahan Setelah Demo Besar", "type": "Utas", "date": "Agu 2024", "stats": "35 rb repost", "url": "https://x.com/tempodotco/status/1865678901234567890", "image_url": "https://images.unsplash.com/photo-1756142183803-d7092cfef1e0?crop=entropy&cs=srgb&fm=jpg&q=85"},
         {"title": "Dinasti Politik: Putusan MK yang Mengubah Peta Kekuasaan", "type": "Utas", "date": "Okt 2023", "stats": "28 rb repost", "url": "https://x.com/tempodotco/status/1858901234567890123", "image_url": "https://images.unsplash.com/photo-1569996958517-3b0e816ac40c?crop=entropy&cs=srgb&fm=jpg&q=85"},
         {"title": "Kebebasan Pers #111: Kekerasan terhadap Jurnalis Naik 40%", "type": "Utas", "date": "Mei 2025", "stats": "14 rb repost", "url": "https://x.com/tempodotco/status/1901234567890123457", "image_url": "https://images.pexels.com/photos/158651/news-newsletter-newspaper-information-158651.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940"},
         {"title": "IKN: Pembangunan Mundur 2 Tahun, Anggaran Dipangkas", "type": "Utas", "date": "Jun 2025", "stats": "17 rb repost", "url": "https://x.com/tempodotco/status/1902345678901234567", "image_url": "https://images.unsplash.com/photo-1756142183803-d7092cfef1e0?crop=entropy&cs=srgb&fm=jpg&q=85"},
         {"title": "Timah Rp 300 T: Pemulihan Aset Baru 3%", "type": "Utas", "date": "Jul 2025", "stats": "12 rb repost", "url": "https://x.com/tempodotco/status/1904567890123456789", "image_url": "https://images.unsplash.com/photo-1624421980204-22e40117494f?crop=entropy&cs=srgb&fm=jpg&q=85"},
         {"title": "Tapera: Pemerintah Akhirnya Ubah Jadi Sukarela", "type": "Utas", "date": "Mei 2024", "stats": "19 rb repost", "url": "https://x.com/tempodotco/status/1887890123456789012", "image_url": "https://images.unsplash.com/photo-1756142507999-ea5301f4350a?crop=entropy&cs=srgb&fm=jpg&q=85"},
     ]},
    {"name": "Eko Kuntadhi", "handle": "@ekokuntadhi", "platform": "Facebook", "followers": "900 rb",
     "focus": "Komentator politik senior dengan tulisan tajam tentang kekuasaan dan demokrasi.",
     "url": "https://www.facebook.com/ekokuntadhi",
     "content": [
         {"title": "Catatan: Pajak Marketplace dan Pemerintah yang Kehabisan Uang", "type": "Catatan", "date": "Nov 2026", "stats": "520 rb dibagikan", "url": "https://www.facebook.com/ekokuntadhi", "image_url": "https://images.unsplash.com/photo-1556742049-0cfed4f6a45d?crop=entropy&cs=srgb&fm=jpg&q=85"},
         {"title": "Catatan: Demokrasi Cacat yang Kita Pelihara", "type": "Catatan", "date": "Jan 2025", "stats": "410 rb dibagikan", "url": "https://www.facebook.com/ekokuntadhi", "image_url": "https://images.pexels.com/photos/158651/news-newsletter-newspaper-information-158651.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940"},
         {"title": "Catatan: Ketika Buzzer Menjadi Mesin Negara", "type": "Catatan", "date": "Feb 2025", "stats": "280 rb dibagikan", "url": "https://www.facebook.com/ekokuntadhi", "image_url": "https://images.unsplash.com/photo-1574936924661-23374e86f1a8?crop=entropy&cs=srgb&fm=jpg&q=85"},
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
            await db.channels.update_one(
                {"name": c["name"], "$or": [
                    {"content": {"$exists": False}},
                    {"content": []},
                ]},
                {"$set": {"content": c["content"], "url": c["url"]}},
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

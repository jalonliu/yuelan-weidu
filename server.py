# -*- coding: utf-8 -*-
r"""乔木阅读 Hermes 版 —— 本地书库服务 (stdlib only)
书库根: F:\Users\Calibre 书库
端口: 8766
端点:
  /                      阅读页
  /api/books             书籍索引 JSON
  /api/rescan            重建索引
  /file/<id>             书籍文件流
  /cover/<id>            封面 (Calibre 或在线匹配下载)
  /foliate/*             foliate-js 静态文件
  /api/covers/search/<id>   在线搜索封面候选 (豆瓣)
  /api/covers/apply/<id>    应用候选封面 (POST {url})
  /api/manage/delete/<id>   移入回收站 _trash (POST {confirm: 书名}, 可恢复)
  /api/manage/trash         回收站列表
  /api/manage/restore/<key> 从回收站恢复
"""
import json
import os
import re
import shutil
import sqlite3
import sys
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LIB_ROOT = os.environ.get("QMU_LIB_ROOT", r"F:\Users\Calibre 书库")
CALIBRE_LIB = os.path.join(LIB_ROOT, "Calibre 书库")
CALIBRE_DB = os.path.join(CALIBRE_LIB, "metadata.db")
FOLIATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "foliate-js")
PORT = 8766
BOOK_EXT = {".epub", ".mobi", ".azw3", ".fb2"}
INDEX_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "books.json")
TRASH_DIR = os.path.join(LIB_ROOT, "_trash")
TRASH_META = os.path.join(TRASH_DIR, ".trash-meta.json")
SKIP_DIRS = {".calibre", ".Trash", "_trash"}
# 微信读书 Agent Gateway（参考 zhaohongxuan/dsh-weread，仅 API-Key 路径）
WEREAD_CFG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "weread.json")
WEREAD_URL = "https://i.weread.qq.com/api/agent/gateway"
WEREAD_SKILL_VERSION = "1.0.3"
# 每日增量缓存（TTL 24h，结构参考 dsh-weread store/cache）
WR_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wr_cache")
WR_TTL = 24 * 3600
# 本地阅读跟踪
TRACK_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "track.json")
# 三分书架：书库 main / 杂书架 misc / 18+ adult（手动覆盖存 shelf.json）
SHELF_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shelf.json")
FMT_RANK = {"epub": 0, "azw3": 1, "mobi": 2, "pdf": 3, "fb2": 4, "txt": 5}
ADULT_KW = re.compile(
    r"淫|乱伦|人妻|少妇|猎艳|白洁|肉欲|情色|nude|erotic|春宫|嫖|娼|妓院|婬|"
    r"淫荡|放荡|偷情|欲女|艳遇|销魂|花丛|采花|风月|房中术|素女|肉蒲团|金瓶梅|"
    r"泡妞|把妹|艳史|艳情|猎艳|迷奸|性爱|做爱|援交|夜店女|KTV经历", re.I)
# AI 总结（走本机 magpie OpenAI 兼容网关）
AI_CFG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai.json")
AI_DEFAULT = {"endpoint": "http://127.0.0.1:3425/v1", "model": "group/free", "apiKey": ""}
PROXY = {"https": "http://127.0.0.1:7897", "http": "http://127.0.0.1:7897"}
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"

NOISE = re.compile(r"\s*[\(\[（【]\s*(Z-Library|作者[:：]|1-\d+|全本|精校版|上下册|\d+)[^\)\]）】]*[\)\]）】]", re.I)
LOCK = threading.Lock()


# ---------- 三分书架 ----------
def shelf_overrides():
    try:
        return json.load(open(SHELF_FILE, encoding="utf-8"))
    except Exception:
        return {}

def save_shelf_override(book_path, shelf):
    """手动书架覆盖按**相对路径**（小写）持久化——此前按 book_id 存，
    而 id 是扫描顺序位置号，每次重扫全变，手动调整会丢失。"""
    ov = shelf_overrides()
    if shelf == "auto":
        ov.pop(str(book_path).lower(), None)
    else:
        ov[str(book_path).lower()] = shelf
    json.dump(ov, open(SHELF_FILE, "w", encoding="utf-8"), ensure_ascii=False)
    return ov

def classify_books(data):
    """给每本书标 shelf：adult=关键词命中或手动覆盖；main=封面+作者全且重名最优副本；其余 misc。"""
    books = data["books"]
    raw_ov = shelf_overrides()
    ov = {}
    by_id = {str(b["id"]): (b.get("path") or "").lower() for b in books}
    for k, v in raw_ov.items():
        # 兼容旧数据：id 键迁移到路径键；路径键直接保留
        if k.isdigit() and k in by_id:
            ov[by_id[k]] = v
        else:
            ov[k.lower()] = v
    def norm(s):
        return NOISE.sub("", s or "").strip().lower()
    groups = {}
    for b in books:
        try:
            p = os.path.join(LIB_ROOT, b.get("path") or "")
            b["mtime"] = int(os.stat(p).st_mtime) if os.path.isfile(p) else 0
        except OSError:
            b["mtime"] = 0
        b["_kw"] = bool(ADULT_KW.search(b.get("title") or ""))
        groups.setdefault(norm(b.get("title")), []).append(b)
    for rows in groups.values():
        if len(rows) > 1:
            best = sorted(rows, key=lambda x: (x["_kw"], not x.get("cover"),
                                               FMT_RANK.get(x.get("format", "").lower(), 9),
                                               -int(x.get("size") or 0)))[0]
            for r in rows:
                r["_dup"] = r is not best
        else:
            for r in rows:
                r["_dup"] = False
    counts = {"main": 0, "misc": 0, "adult": 0}
    for b in books:
        s = ov.get((b.get("path") or "").lower())
        if s not in ("main", "misc", "adult"):
            if b["_kw"]:
                s = "adult"
            elif b["_dup"] or not b.get("cover") or not (b.get("author") or "").strip():
                s = "misc"
            else:
                s = "main"
        b["shelf"] = s
        counts[s] += 1
    return books, counts

def _http_get(url, referer=None, timeout=15):
    op = urllib.request.build_opener(urllib.request.ProxyHandler(PROXY))
    headers = [("User-Agent", UA)]
    if referer:
        headers.append(("Referer", referer))
    op.addheaders = headers
    return op.open(url, timeout=timeout).read()


# ---- 播客播放记录（断点续听 + 搜索）----
LISTEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "listen.json")


def listen_history():
    try:
        return json.load(open(LISTEN_FILE, encoding="utf-8"))
    except Exception:
        return {}


def listen_record(audio_key, show, ep, pos, dur):
    """写入/更新一条播放记录：键=音频 URL，值=进度与元数据。"""
    with LOCK:
        h = listen_history()
        h[audio_key] = {
            "show": show, "ep": ep, "audio": audio_key,
            "pos": round(float(pos or 0), 1),
            "dur": round(float(dur or 0), 1),
            "updated": int(time.time()),
        }
        # 只保留最近 200 条
        if len(h) > 200:
            for k, _ in sorted(h.items(), key=lambda kv: kv[1].get("updated", 0))[: len(h) - 200]:
                h.pop(k)
        json.dump(h, open(LISTEN_FILE, "w", encoding="utf-8"), ensure_ascii=False)
    return h[audio_key]


def clean_title(fn):
    name = os.path.splitext(fn)[0]
    name = NOISE.sub("", name)
    m = re.match(r"^(.*?)\s*[\(（]([^\(）]{1,20})[\)）]\s*$", name)
    if m and len(m.group(2)) <= 20 and "书" not in m.group(2)[:2]:
        return m.group(1).strip(), m.group(2).strip()
    return name.strip(), ""


def load_calibre_meta():
    """(完整文件路径小写) -> (title, author, cover_path)"""
    meta = {}
    if not os.path.isfile(CALIBRE_DB):
        return meta
    try:
        con = sqlite3.connect(CALIBRE_DB)
        rows = con.execute(
            "SELECT b.title, GROUP_CONCAT(a.name), b.path, d.name, d.format FROM books b "
            "LEFT JOIN books_authors_link bal ON bal.book = b.id "
            "LEFT JOIN authors a ON a.id = bal.author "
            "JOIN data d ON d.book = b.id GROUP BY b.id, d.id").fetchall()
        for title, author, path, fname, fmt in rows:
            full = os.path.normpath(os.path.join(CALIBRE_LIB, path, fname + "." + fmt)).lower()
            meta[full] = (title.strip(), author or "",
                          os.path.join(CALIBRE_LIB, path, "cover.jpg") if path else "")
        con.close()
    except sqlite3.Error as e:
        print(f"[warn] metadata.db 读取失败: {e}", file=sys.stderr)
    return meta


def build_index():
    """全量重建索引并写缓存。"""
    calibre_meta = load_calibre_meta()
    books, covers, seen = [], {}, set()
    for dirpath, dirs, files in os.walk(LIB_ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in sorted(files):
            ext = os.path.splitext(f)[1].lower()
            kind = ("epub" if ext == ".epub" else
                    "pdf" if ext == ".pdf" else
                    "text" if ext == ".txt" else
                    "book" if ext in BOOK_EXT else None)
            if not kind:
                continue
            full = os.path.join(dirpath, f)
            rel = os.path.relpath(full, LIB_ROOT)
            if rel.lower() in seen:
                continue
            seen.add(rel.lower())
            title, author = clean_title(f)
            cover_path = ""
            if os.path.normpath(full).lower() in calibre_meta:
                title, author, cover_path = calibre_meta[os.path.normpath(full).lower()]
            # 在线匹配下载过的封面: 书旁 cover.jpg
            local_cover = os.path.join(dirpath, "cover.jpg")
            if not cover_path and os.path.isfile(local_cover):
                cover_path = local_cover
            books.append({
                "id": len(books),
                "title": title,
                "author": author,
                "format": ext.lstrip("."),
                "kind": kind,
                "path": rel,
                "size": os.path.getsize(full),
                "cover": bool(cover_path),
            })
            if cover_path:
                covers[str(books[-1]["id"])] = cover_path
    json.dump({"count": len(books), "books": books, "covers": covers},
              open(INDEX_CACHE, "w", encoding="utf8"), ensure_ascii=False)
    return books


def get_meta():
    with open(INDEX_CACHE, encoding="utf8") as f:
        return json.load(f)


def save_meta(data):
    json.dump(data, open(INDEX_CACHE, "w", encoding="utf8"), ensure_ascii=False)


OPENED_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "opened.json")

# ---- 播客订阅（RSS 收听栏目）----
PODCASTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "podcasts.json")
DEFAULT_PODCASTS = [
    {"title": "半拿铁 | 商业沉浮录", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/62382c1103bea1ebfffa1c00"},
    {"title": "知行小酒馆", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/6013f9f58e2f7ee375cf4216"},
    {"title": "商业就是这样", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/6022a180ef5fdaddc30bb101"},
    {"title": "纵横四海", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/62694abdb221dd5908417d1e"},
    {"title": "硅谷101", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/5e5c52c9418a84a04625e6cc"},
    {"title": "天真不天真", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/65cef9e3cace72dff8d98de3"},
    {"title": "岩中花述", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/625635587bfca4e73e990703"},
    {"title": "声动早咖啡", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/60de7c003dd577b40d5a40f3"},
    {"title": "疯投圈", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/5e280faf418a84a0461fbd39"},
    {"title": "罗永浩的十字路口", "url": "https://rsshub.bestblogs.dev/xiaoyuzhou/podcast/68981df29e7bcd326eb91d88"},
]


def podcasts_load():
    try:
        return json.load(open(PODCASTS_FILE, encoding="utf-8"))
    except Exception:
        return list(DEFAULT_PODCASTS)


def podcasts_save(subs):
    with LOCK:
        json.dump(subs, open(PODCASTS_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


FEED_CACHE = {}  # rss_url -> (ts, parsed)


def podcast_feed(rss_url, max_items=50):
    """拉取并解析播客 RSS（RSS2.0/iTunes），返回 {title, cover, episodes[]}"""
    import email.utils as eut
    cached = FEED_CACHE.get(rss_url)
    if cached and time.time() - cached[0] < 1800:
        return cached[1]
    raw = _http_get(rss_url, timeout=25)
    root = ET.fromstring(raw)
    ch = root.find("channel") or root
    title = (ch.findtext("title") or "").strip()
    cover = ""
    it_img = ch.find("image")
    if it_img is not None:
        cover = (it_img.findtext("url") or "").strip()
    eps = []
    for item in ch.findall("item")[:max_items]:
        enc = item.find("enclosure")
        audio = (enc.get("url") or "").strip() if enc is not None else ""
        if not audio:
            continue
        date = (item.findtext("pubDate") or "").strip()
        try:
            tt = eut.parsedate_tz(date)
            if tt:
                date = time.strftime("%Y-%m-%d", time.gmtime(eut.mktime_tz(tt)))
        except Exception:
            pass
        dur = (item.findtext("{http://www.itunes.com/dtds/podcast-1.0.dtd}duration") or "").strip()
        eps.append({
            "title": (item.findtext("title") or "").strip(),
            "date": date,
            "dur": dur,
            "audio": audio,
        })
    out = {"title": title, "cover": cover, "episodes": eps}
    FEED_CACHE[rss_url] = (time.time(), out)
    return out


def opened_load():
    """已打开书籍表：{相对路径小写: 首次打开时间戳}，用于「新增」角标。"""
    if os.path.isfile(OPENED_FILE):
        try:
            return json.load(open(OPENED_FILE, encoding="utf8"))
        except (OSError, ValueError):
            return {}
    return {}


def opened_save(data):
    json.dump(data, open(OPENED_FILE, "w", encoding="utf8"), ensure_ascii=False)


def load_trash_meta():
    if os.path.isfile(TRASH_META):
        return json.load(open(TRASH_META, encoding="utf8"))
    return {}


def save_trash_meta(m):
    json.dump(m, open(TRASH_META, "w", encoding="utf8"), ensure_ascii=False, indent=1)


class WereadError(Exception):
    def __init__(self, code, msg, status=502):
        super().__init__(msg)
        self.code = code
        self.status = status


def weread_cfg():
    if os.path.isfile(WEREAD_CFG):
        return json.load(open(WEREAD_CFG, encoding="utf-8"))
    return {"apiKey": "", "proxy": "http://127.0.0.1:7897"}


def save_weread_cfg(cfg):
    json.dump(cfg, open(WEREAD_CFG, "w", encoding="utf-8"), ensure_ascii=False)


def weread_call(api_name, params=None):
    cfg = weread_cfg()
    key = cfg.get("apiKey", "")
    if not key:
        raise WereadError("weread/no-key", "未配置微信读书 API Key", 401)
    body = json.dumps({"api_name": api_name, "skill_version": WEREAD_SKILL_VERSION,
                       **(params or {})}).encode()
    proxy = cfg.get("proxy") or ""
    handlers = [urllib.request.ProxyHandler({"http": proxy, "https": proxy} if proxy else {})]
    op = urllib.request.build_opener(*handlers)
    op.addheaders = [
        ("Authorization", f"Bearer {key}"),
        ("Content-Type", "application/json"),
        ("accept", "application/json, text/plain, */*"),
        ("User-Agent", UA),
    ]
    try:
        resp = op.open(urllib.request.Request(WEREAD_URL, data=body, method="POST"), timeout=30)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise WereadError("weread/unauthorized", "API Key 无效或已过期", 401)
        if e.code == 403:
            raise WereadError("weread/blocked",
                              "微信读书拒绝了当前网络出口（风控 403）。Key 可能有效，请改用可访问微信读书的代理。", 403)
        raise WereadError("weread/http", f"微信读书接口返回 HTTP {e.code}", 502)
    except Exception as e:
        raise WereadError("weread/network", f"请求微信读书失败：{e}", 502)
    try:
        data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        raise WereadError("weread/parse", f"微信读书返回非 JSON：{e}", 502)
    errcode = data.get("errcode") if isinstance(data, dict) else None
    if isinstance(errcode, int) and errcode != 0:
        raise WereadError(f"weread/{errcode}",
                          data.get("errmsg") or f"微信读书错误码 {errcode}", 200)
    return data


def weread_shelf():
    def _load():
        raw = weread_call("/shelf/sync")
        rows = raw.get("notebooks") or raw.get("books") or []
        books = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            b = row.get("book") if isinstance(row.get("book"), dict) else row
            book_id = str(b.get("bookId") or row.get("bookId") or "")
            if not book_id:
                continue
            cover = str(b.get("cover") or "")
            cover = cover.replace("/s_", "/t7_") if cover else ""
            prog = row.get("readingProgress") or 0
            books.append({
                "bookId": book_id,
                "title": str(b.get("title") or ""),
                "author": str(b.get("author") or ""),
                "cover": cover,
                "progress": min(100, max(0, prog if isinstance(prog, (int, float)) else 0)),
                "noteCount": row.get("noteCount") or 0,
                "reviewCount": row.get("reviewCount") or 0,
                "lastRead": int(row.get("readUpdateTime") or row.get("sort") or 0),
                "deepLink": str(row.get("deepLink") or b.get("deepLink") or ""),
                "readerLink": str(row.get("readerLink") or b.get("readerLink") or ""),
            })
        return {"ok": True, "count": len(books), "books": books}
    return wr_cached("shelf", _load)


def wr_cached(name, fn):
    """每日增量缓存：wr_cache/<name>.json，TTL 24h。"""
    os.makedirs(WR_CACHE, exist_ok=True)
    path = os.path.join(WR_CACHE, name + ".json")
    if os.path.isfile(path) and time.time() - os.path.getmtime(path) < WR_TTL:
        try:
            data = json.load(open(path, encoding="utf-8"))
            if isinstance(data, dict) and data.get("ok"):
                return data
        except Exception:
            pass
    data = fn()
    if isinstance(data, dict) and data.get("ok"):
        json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    return data


def weread_notebooks():
    def _load():
        raw = weread_call("/user/notebooks")
        rows = raw.get("notebooks") or raw.get("books") or []
        books = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            b = row.get("book") if isinstance(row.get("book"), dict) else {}
            cover = str(b.get("cover") or "")
            cover = cover.replace("/s_", "/t7_") if cover else ""
            books.append({
                "bookId": str(b.get("bookId") or ""),
                "title": str(b.get("title") or ""),
                "author": str(b.get("author") or ""),
                "cover": cover,
                "noteCount": row.get("noteCount") or 0,
                "reviewCount": row.get("reviewCount") or 0,
                "lastRead": (row.get("lastReadTime") or 0),
                "deepLink": str(b.get("deepLink") or ""),
            })
        books.sort(key=lambda x: x["lastRead"], reverse=True)
        return {"ok": True, "count": len(books), "books": books}
    return wr_cached("notebooks", _load)


def weread_notes(book_id):
    raw_marks = weread_call("/book/bookmarklist", {"bookId": book_id})
    marks = raw_marks.get("updated") or []
    items = [{"type": "highlight", "chapter": m.get("chapterName") or "",
              "text": m.get("markText") or "", "time": m.get("createTime")} for m in marks]
    try:
        raw_rev = weread_call("/review/list/mine", {"bookId": book_id})
        for r in (raw_rev.get("reviews") or []):
            r = r.get("review") or r
            items.append({"type": "review", "chapter": (r.get("chapterName") or ""),
                          "text": r.get("content") or "", "time": r.get("createTime")})
    except Exception:
        pass
    items.sort(key=lambda x: x.get("time") or 0, reverse=True)
    return {"ok": True, "items": items}


def weread_today():
    now = time.localtime()
    month_start = int(time.mktime((now.tm_year, now.tm_mon, 1, 0, 0, 0, 0, 0, -1)))
    raw = weread_call("/readdata/detail", {"mode": "monthly", "baseTime": month_start})
    today_key = str(int(time.mktime((now.tm_year, now.tm_mon, now.tm_mday, 0, 0, 0, 0, 0, -1))))
    today = (raw.get("readTimes") or {}).get(today_key, 0)
    return {"ok": True, "todaySec": today, "date": time.strftime("%Y-%m-%d")}


def weread_heatmap(year):
    def _load():
        daily = {}
        for m in range(1, 13):
            base = int(time.mktime((year, m, 1, 0, 0, 0, 0, 0, -1)))
            try:
                raw = weread_call("/readdata/detail", {"mode": "monthly", "baseTime": base})
                for k, v in (raw.get("readTimes") or {}).items():
                    daily[k] = daily.get(k, 0) + v
            except Exception:
                pass
        return {"ok": True, "year": year, "daily": daily}
    return wr_cached(f"heatmap-{year}", _load)


def weread_bookwall():
    shelf = weread_shelf()
    wall = {}
    for b in shelf.get("books", []):
        if not b.get("lastRead"):
            continue
        t = time.localtime(b["lastRead"])
        y, m = t.tm_year, t.tm_mon
        wall.setdefault(y, {}).setdefault(m, []).append(b)
    return {"ok": True, "wall": {str(y): {str(m): v for m, v in mm.items()}
                                 for y, mm in sorted(wall.items(), reverse=True)}}


def weread_stats(params):
    return {"ok": True, "stats": weread_call("/readdata/detail", params)}


def ai_config():
    if os.path.isfile(AI_CFG):
        try:
            cfg = json.load(open(AI_CFG, encoding="utf-8"))
            return {**AI_DEFAULT, **cfg}
        except Exception:
            pass
    return AI_DEFAULT


def ai_cache_read(key):
    path = os.path.join(WR_CACHE, f"ai-{key}.json")
    if os.path.isfile(path):
        try:
            return json.load(open(path, encoding="utf-8"))
        except Exception:
            return None
    return None


def ai_cache_write(key, data):
    os.makedirs(WR_CACHE, exist_ok=True)
    json.dump(data, open(os.path.join(WR_CACHE, f"ai-{key}.json"), "w", encoding="utf-8"),
              ensure_ascii=False)


def ai_summary(title, highlights):
    cfg = ai_config()
    text = "\n".join(f"- {h['text']}" for h in highlights[:40] if h.get("text")) or title
    prompt = (f"这是我在微信读书读《{title}》时的划线笔记：\n{text}\n\n"
              "请用中文输出：1) 一段 150 字左右的核心主题总结；2) 3 条给我自己的行动启发。"
              "直接输出，不要客套。")
    body = json.dumps({"model": cfg["model"], "stream": False,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(cfg["endpoint"].rstrip("/") + "/chat/completions",
                                 data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if cfg.get("apiKey"):
        req.add_header("Authorization", "Bearer " + cfg["apiKey"])
    resp = urllib.request.urlopen(req, timeout=120)
    data = json.loads(resp.read().decode("utf-8"))
    content = data["choices"][0]["message"]["content"]
    return content


def track_load():
    if os.path.isfile(TRACK_FILE):
        try:
            return json.load(open(TRACK_FILE, encoding="utf-8"))
        except Exception:
            pass
    return {}


# ---------- 笔记索引（今日 / 回顾） ----------
def notes_index():
    """聚合微信读书全部划线与想法：notebooks -> 每本 bookmarklist/review（24h 缓存）。"""
    nb = weread_notebooks()
    items, books = [], []
    for b in nb.get("books", []):
        books.append(b)
        try:
            d = wr_cached("notes-" + b["bookId"], lambda bid=b["bookId"]: weread_notes(bid))
        except Exception:
            continue
        for n in d.get("items", []):
            items.append({**n, "bookId": b["bookId"], "title": b["title"],
                          "author": b.get("author", ""), "cover": b.get("cover", "")})
    items.sort(key=lambda x: x.get("time") or 0, reverse=True)
    return {"ok": True, "items": items, "books": books}


def today_brief():
    """今日总览：阅读/收听时长、今日读过的书、今日划线与想法、旧句重逢。"""
    import random
    today = time.strftime("%Y-%m-%d")
    t0 = int(time.mktime(time.strptime(today, "%Y-%m-%d")))
    t1 = t0 + 86400
    tr = track_load().get(today, {})
    today_books = [{"title": v.get("title") or k, "seconds": v.get("seconds", 0),
                    "percent": v.get("percent", 0)} for k, v in tr.items()]
    local_sec = sum(b["seconds"] for b in today_books)
    wr_sec = 0
    try:
        wr_sec = weread_today().get("todaySec", 0)
    except Exception:
        pass
    try:
        idx = notes_index()
        items = idx["items"]
    except Exception:
        items = []
    today_notes = [n for n in items if n.get("time") and t0 <= n["time"] < t1]
    lt = time.localtime()
    onthisday = [n for n in items if n.get("time") and n["time"] < t0
                 and time.localtime(n["time"]).tm_mon == lt.tm_mon
                 and time.localtime(n["time"]).tm_mday == lt.tm_mday]
    older = [n for n in items if n.get("time") and n["time"] < t0]
    if onthisday:
        pick, mode = random.choice(onthisday), "onthisday"
    elif older:
        pick, mode = random.choice(older), "random"
    else:
        pick, mode = None, ""
    return {"ok": True, "date": today, "localSec": local_sec, "listenSec": 0,
            "wereadSec": wr_sec, "todayBooks": today_books,
            "todayNotes": today_notes, "resurface": pick, "resurfaceMode": mode}


def track_summary():
    data = track_load()
    days = {k: sum(v2.get("seconds", 0) for v2 in v.values()) for k, v in data.items()}
    books = {}
    for v in data.values():
        for bid, b in v.items():
            t = books.setdefault(bid, {"title": b.get("title") or bid,
                                       "seconds": 0, "lastPercent": 0, "days": 0})
            t["seconds"] += b.get("seconds", 0)
            t["lastPercent"] = max(t["lastPercent"], b.get("percent") or 0)
            t["days"] += 1
    top = sorted(books.values(), key=lambda x: -x["seconds"])[:10]
    today = time.strftime("%Y-%m-%d")
    return {"ok": True, "todaySec": days.get(today, 0),
            "days": {k: v for k, v in sorted(days.items())},
            "totalSec": sum(days.values()), "dayCount": len(days),
            "topBooks": top, "bookCount": len(books)}


def cover_queries(title, author):
    """豆瓣搜索词清洗：去书名号/括号注记（精校版全本等）/噪声词，超长截断。"""
    t = re.sub(r"[《》「」〖〗\[\]]", "", title or "")
    t = re.split(r"[（(【\[]", t)[0]
    t = re.sub(r"(精校|精排|全本|全集|校对|典藏|扫描|高清|文字|完整|插图|修订|珍藏|双语|注释|注音|软精装|套装|珍藏版?|纪念版?|新版?|原版?|第?\s*\d+\s*版?|上|下|Ⅰ|Ⅱ|Ⅲ).{0,8}$", "", t)
    t = t.strip(" -_·，,。;；:：!！?？")
    queries = []
    if t:
        queries.append(t)                                  # 先只搜清洗后的书名
        if len(t) > 14:
            queries.append(t[:14])                         # 超长教材名截断
    a = re.split(r"[/，,、]", author or "")[0].strip()
    if t and a and len(t) <= 12:
        queries.append(t + " " + a)                        # 书名+作者兜底
    return queries


def cover_search(queries):
    """豆瓣 suggest 接口 -> 候选列表；逐个查询词回退，返回首个有结果的。"""
    if isinstance(queries, str):
        queries = [queries]
    tried = []
    for q in queries:
        if not q:
            continue
        tried.append(q)
        try:
            data = json.loads(_http_get(
                "https://book.douban.com/j/subject_suggest?q=" + urllib.parse.quote(q),
                timeout=12).decode("utf-8"))
        except Exception as e:
            return {"ok": False, "error": str(e), "candidates": [], "tried": tried}
        cands = []
        for it in data:
            if it.get("type") == "b" and it.get("pic"):
                cands.append({
                    "title": it.get("title", ""),
                    "author": it.get("author_name", ""),
                    "year": it.get("year", ""),
                    "url": it.get("pic", ""),
                })
        if cands:
            return {"ok": True, "candidates": cands[:6], "tried": tried}
    return {"ok": True, "candidates": [], "tried": tried}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        # HTML 页面禁缓存：reader.html 迭代频繁，避免浏览器用旧版样式（如窄 tab 固定宽度）
        if ctype.startswith("text/html"):
            self.send_header("Cache-Control", "no-cache")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode())

    def _read_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except ValueError:
            return {}

    def do_GET(self):
        path = unquote_path(self.path)
        if path in ("/", "/index.html"):
            body = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "reader.html"), "rb").read()
            self._send(200, body, "text/html; charset=utf-8")
        elif path.split("?")[0] == "/api/books":
            qs = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            want = (qs.get("shelf") or ["main"])[0]
            data = get_meta()
            books, counts = classify_books(data)
            order = {"main": 0, "adult": 1, "misc": 2}
            rows = [b for b in books if want == "all" or b["shelf"] == want]
            rows.sort(key=lambda b: (-b.get("mtime", 0), order.get(b["shelf"], 9), str(b["title"])))
            opened = opened_load()
            for b in rows:
                b["opened"] = (b.get("path") or "").lower() in opened
            self._json(200, {"count": len(rows), "total": data["count"], "shelves": counts,
                             "books": [{k: v for k, v in b.items() if not k.startswith("_")} for b in rows]})
        elif path == "/api/rescan":
            with LOCK:
                books = build_index()
            self._json(200, {"ok": True, "count": len(books)})
        elif path == "/api/health":
            self._send(200, b'{"ok":true}')
        elif path == "/api/podcasts":
            subs = podcasts_load()
            self._json(200, {"ok": True, "podcasts": subs})
        elif path == "/api/listen/history":
            self._json(200, {"ok": True, "history": listen_history()})
        elif path == "/api/podcast/feed":
            qs = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            url = (qs.get("url") or [""])[0]
            if not url:
                self._json(400, {"ok": False, "error": "missing url"})
                return
            try:
                self._json(200, {"ok": True, **podcast_feed(url)})
            except Exception as e:
                self._json(502, {"ok": False, "error": str(e)})
        elif path == "/api/podcast/audio":
            # 音频代理：透传 Range 以支持拖动进度
            qs = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            url = (qs.get("url") or [""])[0]
            if not url.startswith(("http://", "https://")):
                self._json(400, {"ok": False, "error": "bad url"})
                return
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA, **({"Range": self.headers.get("Range")} if self.headers.get("Range") else {})})
                op = urllib.request.build_opener(urllib.request.ProxyHandler(PROXY))
                resp = op.open(req, timeout=30)
                self.send_response(resp.status)
                self.send_header("Content-Type", resp.headers.get("Content-Type", "audio/mpeg"))
                for h in ("Content-Length", "Content-Range", "Accept-Ranges"):
                    if resp.headers.get(h):
                        self.send_header(h, resp.headers[h])
                self.end_headers()
                while True:
                    chunk = resp.read(64 * 1024)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
            except Exception as e:
                try:
                    self._json(502, {"ok": False, "error": str(e)})
                except Exception:
                    pass
        elif path.startswith("/api/covers/search/"):
            self._cover_search(path.rsplit("/", 1)[1])
        elif path == "/api/manage/trash":
            meta = load_trash_meta()
            items = [{"key": t, **m} for t, m in sorted(meta.items(), reverse=True)
                     if os.path.isfile(os.path.join(TRASH_DIR, t))]
            self._json(200, {"items": items})
        elif path == "/api/weread/config":
            cfg = weread_cfg()
            key = cfg.get("apiKey", "")
            self._json(200, {"apiKey": (key[:3] + "****" + key[-4:]) if len(key) > 7 else ("已配置" if key else ""), "proxy": cfg.get("proxy", "")})
        elif path == "/api/weread/shelf":
            try:
                self._json(200, weread_shelf())
            except WereadError as e:
                self._json(e.status, {"ok": False, "code": e.code, "error": str(e)})
        elif path == "/api/weread/notebooks":
            try:
                self._json(200, weread_notebooks())
            except WereadError as e:
                self._json(e.status, {"ok": False, "code": e.code, "error": str(e)})
        elif path == "/api/weread/today":
            try:
                self._json(200, weread_today())
            except WereadError as e:
                self._json(e.status, {"ok": False, "code": e.code, "error": str(e)})
        elif path == "/api/weread/bookwall":
            try:
                self._json(200, weread_bookwall())
            except WereadError as e:
                self._json(e.status, {"ok": False, "code": e.code, "error": str(e)})
        elif path.startswith("/api/weread/heatmap/"):
            year = int(path.rsplit("/", 1)[1])
            try:
                self._json(200, weread_heatmap(year))
            except WereadError as e:
                self._json(e.status, {"ok": False, "code": e.code, "error": str(e)})
        elif path.startswith("/api/weread/notes/"):
            bid = path.rsplit("/", 1)[1]
            try:
                self._json(200, weread_notes(bid))
            except WereadError as e:
                self._json(e.status, {"ok": False, "code": e.code, "error": str(e)})
        elif path == "/api/notes/all":
            try:
                self._json(200, notes_index())
            except WereadError as e:
                self._json(e.status, {"ok": False, "code": e.code, "error": str(e)})
            except Exception as e:
                self._json(500, {"ok": False, "error": str(e)})
        elif path == "/api/today":
            try:
                self._json(200, today_brief())
            except WereadError as e:
                self._json(e.status, {"ok": False, "code": e.code, "error": str(e)})
            except Exception as e:
                self._json(500, {"ok": False, "error": str(e)})
        elif path == "/api/track":
            self._json(200, track_summary())
        elif path.startswith("/api/weread/stats"):
            qs = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            mode = (qs.get("mode") or ["overall"])[0]
            params = {"mode": mode}
            if qs.get("baseTime"):
                params["baseTime"] = int(qs["baseTime"][0])
            try:
                self._json(200, weread_stats(params))
            except WereadError as e:
                self._json(e.status, {"ok": False, "code": e.code, "error": str(e)})
        elif path.startswith("/file/"):
            self._serve_book(path[len("/file/"):])
        elif path.startswith("/cover/"):
            self._serve_cover(path[len("/cover/"):])
        elif path.startswith("/foliate/"):
            fp = os.path.normpath(os.path.join(FOLIATE_DIR, path[len("/foliate/"):]))
            if not fp.startswith(os.path.normpath(FOLIATE_DIR)) or not os.path.isfile(fp):
                self._send(404, b"not found", "text/plain")
                return
            body = open(fp, "rb").read()
            ct = "text/javascript" if fp.endswith(".js") else "text/html" if fp.endswith(".html") else "application/octet-stream"
            self._send(200, body, ct)
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self):
        path = unquote_path(self.path)
        if path == "/api/podcasts":
            # 添加订阅 {url, title?}（title 缺省时从 feed 取）
            body = self._read_body()
            url = (body.get("url") or "").strip()
            if not url.startswith(("http://", "https://")):
                self._json(400, {"ok": False, "error": "bad url"})
                return
            subs = podcasts_load()
            if any(p["url"] == url for p in subs):
                self._json(200, {"ok": True, "podcasts": subs, "duplicate": True})
                return
            title = (body.get("title") or "").strip()
            if not title:
                try:
                    title = podcast_feed(url, max_items=5).get("title") or url
                except Exception as e:
                    self._json(502, {"ok": False, "error": "feed 拉取失败: " + str(e)})
                    return
            subs.append({"title": title, "url": url})
            podcasts_save(subs)
            self._json(200, {"ok": True, "podcasts": subs})
            return
        if path == "/api/podcasts/delete":
            body = self._read_body()
            url = (body.get("url") or "").strip()
            subs = [p for p in podcasts_load() if p["url"] != url]
            podcasts_save(subs)
            self._json(200, {"ok": True, "podcasts": subs})
            return
        if path == "/api/rescan":
            # 前端「重新扫描书库」走 POST；此前只在 do_GET 实现，POST 一直 404
            # 导致「显示扫描了但加不上书」。
            with LOCK:
                books = build_index()
            self._json(200, {"ok": True, "count": len(books)})
            return
        if path.startswith("/api/book/opened/"):
            # 打开即消除「新增」角标：以相对路径为键，避免重建索引后 id 漂移。
            data = get_meta()
            bid = path.rsplit("/", 1)[1]
            b = next((x for x in data.get("books", []) if str(x.get("id")) == bid), None)
            if b:
                op = opened_load()
                op[(b.get("path") or "").lower()] = int(time.time())
                opened_save(op)
            self._json(200, {"ok": True})
            return
        if path == "/api/open-libfolder":
            # 「添加书籍」口子：打开书库根目录，把书文件放进去后点重新扫描。
            try:
                os.startfile(LIB_ROOT)
                self._json(200, {"ok": True})
            except Exception as e:
                self._json(500, {"ok": False, "error": str(e)})
            return
        if path == "/api/ai/chat":
            # AI 流式输出：SSE 逐行转发 OpenAI 兼容网关（magpie / hermes ctx.llm 等价后端）
            body = self._read_body()
            msgs = body.get("messages") or []
            cfg = ai_config()
            if not msgs:
                self._json(400, {"ok": False, "error": "messages required"})
                return
            payload = json.dumps({"model": cfg["model"], "stream": True,
                                  "messages": msgs}).encode()
            req = urllib.request.Request(cfg["endpoint"].rstrip("/") + "/chat/completions",
                                         data=payload, method="POST")
            req.add_header("Content-Type", "application/json")
            if cfg.get("apiKey"):
                req.add_header("Authorization", "Bearer " + cfg["apiKey"])
            try:
                resp = urllib.request.urlopen(req, timeout=300)
            except Exception as e:
                self._json(502, {"ok": False, "error": f"AI 网关连接失败：{e}"})
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            try:
                for raw in resp:
                    line = raw.strip()
                    if line:
                        self.wfile.write(line + b"\n\n")
                        self.wfile.flush()
            except Exception:
                pass
            return
        if path == "/api/track":
            body = self._read_body()
            data = track_load()
            today = time.strftime("%Y-%m-%d")
            day = data.setdefault(today, {})
            bid = str(body.get("bookId") or "unknown")
            rec = day.setdefault(bid, {"title": body.get("title") or bid,
                                       "seconds": 0, "percent": 0})
            rec["seconds"] += max(0, int(body.get("delta") or 0))
            rec["percent"] = max(rec["percent"], int(body.get("percent") or 0))
            json.dump(data, open(TRACK_FILE, "w", encoding="utf-8"), ensure_ascii=False)
            self._json(200, {"ok": True})
        elif path == "/api/ai/summary":
            body = self._read_body()
            key = str(body.get("key") or "")
            title = str(body.get("title") or "")
            if not key or not title:
                self._json(400, {"ok": False, "error": "key/title required"})
                return
            cached = ai_cache_read(key)
            if cached:
                self._json(200, cached)
                return
            try:
                content = ai_summary(title, body.get("highlights") or [])
                out = {"ok": True, "summary": content, "cachedAt": int(time.time())}
                ai_cache_write(key, out)
                self._json(200, out)
            except Exception as e:
                self._json(502, {"ok": False, "error": f"AI 调用失败：{e}"})
        elif path == "/api/shelf":
            body = self._read_body()
            shelf = str(body.get("shelf") or "")
            if shelf not in ("main", "misc", "adult", "auto"):
                self._json(400, {"ok": False, "error": "shelf required (main|misc|adult|auto)"})
                return
            # 兼容旧入参 {id}：解析成稳定路径再存
            bpath = str(body.get("path") or "")
            if not bpath and body.get("id") is not None:
                data = get_meta()
                books = data["books"]
                for b in books:
                    if str(b["id"]) == str(body["id"]):
                        bpath = b["path"]
                        break
            if not bpath:
                self._json(400, {"ok": False, "error": "id/path required"})
                return
            ov = save_shelf_override(bpath, shelf)
            self._json(200, {"ok": True, "overrides": len(ov)})
        elif path == "/api/shelf/batch":
            # 管理模式批量移动：{paths: [...], shelf}
            body = self._read_body()
            shelf = str(body.get("shelf") or "")
            paths = body.get("paths") or []
            if shelf not in ("main", "misc", "adult", "auto") or not paths:
                self._json(400, {"ok": False, "error": "paths/shelf required"})
                return
            ov = shelf_overrides()
            for p in paths:
                ov = save_shelf_override(p, shelf)
            self._json(200, {"ok": True, "moved": len(paths), "overrides": len(ov)})
        elif path == "/api/weread/refresh":
            # 清空每日缓存，强制重新拉取
            for f in os.listdir(WR_CACHE) if os.path.isdir(WR_CACHE) else []:
                if f.endswith(".json") and not f.startswith("ai-"):
                    try:
                        os.remove(os.path.join(WR_CACHE, f))
                    except Exception:
                        pass
            self._json(200, {"ok": True, "cleared": True})
        if path == "/api/weread/config":
            body = self._read_body()
            cfg = weread_cfg()
            if body.get("apiKey"):
                cfg["apiKey"] = str(body["apiKey"]).strip()
            if "proxy" in body:
                cfg["proxy"] = str(body["proxy"]).strip()
            save_weread_cfg(cfg)
            self._json(200, {"ok": True, "masked": (cfg["apiKey"][:3] + "****" + cfg["apiKey"][-4:]) if len(cfg["apiKey"]) > 7 else bool(cfg["apiKey"])})
        elif path.startswith("/api/covers/apply/"):
            self._cover_apply(path.rsplit("/", 1)[1])
        elif path.startswith("/api/covers/upload/"):
            self._cover_upload(path.rsplit("/", 1)[1])
        elif path == "/api/listen/progress":
            body = self._read_body()
            key = str(body.get("audio") or "")
            if not key:
                self._json(400, {"ok": False, "error": "audio required"})
                return
            rec = listen_record(key, str(body.get("show") or ""), str(body.get("ep") or ""),
                                body.get("pos") or 0, body.get("dur") or 0)
            self._json(200, {"ok": True, "record": rec})
        elif path == "/api/listen/clear":
            with LOCK:
                json.dump({}, open(LISTEN_FILE, "w", encoding="utf-8"))
            self._json(200, {"ok": True})
        elif path.startswith("/api/manage/delete/"):
            self._delete_book(path.rsplit("/", 1)[1])
        elif path.startswith("/api/manage/restore/"):
            self._restore(path.rsplit("/", 1)[1])
        elif path == "/api/open-browser":
            # 用系统默认浏览器打开书库页（从桌面插件 iframe 跳出到全窗口阅读）
            try:
                os.startfile("http://127.0.0.1:8766/")
                self._json(200, {"ok": True})
            except Exception as e:
                self._json(500, {"ok": False, "error": str(e)})
        elif path == "/api/manage/purge":
            self._purge(None)
        elif path.startswith("/api/manage/purge/"):
            self._purge(path.rsplit("/", 1)[1])
        else:
            self._send(404, b"not found", "text/plain")

    # ---------- 封面 ----------
    def _cover_search(self, bid):
        data = get_meta()
        book = next((b for b in data["books"] if str(b["id"]) == bid), None)
        if not book:
            self._json(404, {"ok": False, "error": "book not found"})
            return
        q = book["title"] + ((" " + book["author"]) if book["author"] else "")
        self._json(200, dict(query=q, **cover_search(cover_queries(book["title"], book["author"]))))

    def _cover_apply(self, bid):
        body = self._read_body()
        url = body.get("url", "")
        if not url:
            self._json(400, {"ok": False, "error": "missing url"})
            return
        data = get_meta()
        book = next((b for b in data["books"] if str(b["id"]) == bid), None)
        if not book:
            self._json(404, {"ok": False, "error": "book not found"})
            return
        full = os.path.join(LIB_ROOT, book["path"])
        dest = os.path.join(os.path.dirname(full), "cover.jpg")
        try:
            img = None
            big = url.replace("/view/subject/s/public/", "/view/subject/l/public/")
            for u in (big, url):
                try:
                    img = _http_get(u, referer="https://book.douban.com/")
                    if img and len(img) > 1000:
                        break
                except Exception:
                    continue
            if not img:
                raise RuntimeError("封面下载失败")
            with LOCK:
                open(dest, "wb").write(img)
                data["covers"][bid] = dest
                book["cover"] = True
                save_meta(data)
            self._json(200, {"ok": True, "cover": dest, "bytes": len(img)})
        except Exception as e:
            self._json(500, {"ok": False, "error": str(e)})

    def _cover_upload(self, bid):
        """手动上传本地图片作为封面（multipart 或裸图片字节均可）。"""
        data = get_meta()
        book = next((b for b in data["books"] if str(b["id"]) == bid), None)
        if not book:
            self._json(404, {"ok": False, "error": "book not found"})
            return
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        # 若是 multipart 表单，截取第一个文件部分的字节
        ctype = self.headers.get("Content-Type", "")
        if "multipart/form-data" in ctype and raw.startswith(b"--"):
            import re as _re
            m = _re.search(rb"\\r\\n\\r\\n(.*?)\\r\\n--", raw, _re.S)
            if not m:
                self._json(400, {"ok": False, "error": "multipart 解析失败"})
                return
            raw = m.group(1)
        if len(raw) < 500:
            self._json(400, {"ok": False, "error": "图片内容过小或为空"})
            return
        full = os.path.join(LIB_ROOT, book["path"])
        dest = os.path.join(os.path.dirname(full), "cover.jpg")
        with LOCK:
            open(dest, "wb").write(raw)
            data["covers"][bid] = dest
            book["cover"] = True
            save_meta(data)
        self._json(200, {"ok": True, "cover": dest, "bytes": len(raw)})

    # ---------- 管理 ----------
    def _delete_book(self, bid):
        body = self._read_body()
        data = get_meta()
        book = next((b for b in data["books"] if str(b["id"]) == bid), None)
        if not book:
            self._json(404, {"ok": False, "error": "book not found"})
            return
        full = os.path.join(LIB_ROOT, book["path"])
        if body.get("confirm") != book["title"]:
            self._json(400, {"ok": False, "error": "confirm 不匹配", "need": book["title"]})
            return
        if not os.path.isfile(full):
            self._json(410, {"ok": False, "error": "文件已不存在"})
            return
        ts = time.strftime("%Y%m%d-%H%M%S")
        os.makedirs(TRASH_DIR, exist_ok=True)
        tname = f"{ts}_{os.path.basename(full)}"
        shutil.move(full, os.path.join(TRASH_DIR, tname))
        meta = load_trash_meta()
        meta[tname] = {"orig": book["path"], "deleted_at": ts,
                       "title": book["title"], "author": book["author"], "format": book["format"]}
        save_trash_meta(meta)
        with LOCK:
            data["books"] = [b for b in data["books"] if str(b["id"]) != bid]
            data["covers"].pop(bid, None)
            data["count"] = len(data["books"])
            save_meta(data)
        self._json(200, {"ok": True, "trash_name": tname, "restorable": True})

    def _restore(self, key):
        meta = load_trash_meta()
        m = meta.get(key)
        if not m:
            self._json(404, {"ok": False, "error": "trash item not found"})
            return
        src = os.path.join(TRASH_DIR, key)
        dest = os.path.join(LIB_ROOT, m["orig"])
        if not os.path.isfile(src):
            self._json(410, {"ok": False, "error": "回收站文件已不存在"})
            return
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.move(src, dest)
        meta.pop(key)
        save_trash_meta(meta)
        with LOCK:
            build_index()
        self._json(200, {"ok": True, "restored_to": m["orig"]})

    def _purge(self, key):
        """彻底删除回收站条目：key=None 清空全部。删除后索引重建，本地文件一并清除。"""
        body = self._read_body()
        meta = load_trash_meta()
        if key is None:
            if body.get("confirm") != "清空回收站":
                self._json(400, {"ok": False, "error": "confirm 不匹配", "need": "清空回收站"})
                return
            targets = list(meta.keys())
        else:
            m = meta.get(key)
            if not m:
                self._json(404, {"ok": False, "error": "trash item not found"})
                return
            if body.get("confirm") != m.get("title"):
                self._json(400, {"ok": False, "error": "confirm 不匹配", "need": m.get("title")})
                return
            targets = [key]
        removed, failed = 0, []
        for k in targets:
            p = os.path.join(TRASH_DIR, k)
            try:
                if os.path.isdir(p):
                    shutil.rmtree(p)
                elif os.path.isfile(p):
                    os.remove(p)
                meta.pop(k, None)
                removed += 1
            except Exception as e:
                failed.append({"key": k, "error": str(e)})
        save_trash_meta(meta)
        with LOCK:
            build_index()
        self._json(200, {"ok": not failed, "removed": removed, "failed": failed})

    # ---------- 原有 ----------
    def _serve_book(self, bid):
        try:
            data = get_meta()
            book = next(b for b in data["books"] if str(b["id"]) == bid)
        except (StopIteration, OSError):
            self._send(404, b"book not found", "text/plain")
            return
        full = os.path.join(LIB_ROOT, book["path"])
        try:
            body = open(full, "rb").read()
        except OSError as e:
            self._send(500, str(e).encode(), "text/plain")
            return
        ct = {"epub": "application/epub+zip", "pdf": "application/pdf",
              "mobi": "application/x-mobipocket-ebook", "azw3": "application/x-mobipocket-ebook",
              "fb2": "application/x-fictionbook+xml", "txt": "text/plain; charset=utf-8"}.get(book["format"], "application/octet-stream")
        self._send(200, body, ct)

    def _serve_cover(self, bid):
        try:
            data = get_meta()
            cov = data["covers"][bid]
        except (KeyError, OSError):
            self._send(404, b"no cover", "text/plain")
            return
        full = cov if os.path.isabs(cov) else os.path.join(LIB_ROOT, cov)
        try:
            body = open(full, "rb").read()
        except OSError:
            self._send(404, b"no cover", "text/plain")
            return
        self._send(200, body, "image/jpeg")


def unquote_path(p):
    return urllib.parse.unquote(urllib.parse.urlsplit(p).path)


if __name__ == "__main__":
    books = build_index()
    print(f"书库索引: {len(books)} 本，缓存 {INDEX_CACHE}")
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"乔木阅读服务: http://127.0.0.1:{PORT}/")
    srv.serve_forever()

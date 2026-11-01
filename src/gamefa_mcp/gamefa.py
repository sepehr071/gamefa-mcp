"""Gamefa tools: articles and scored reviews (WordPress REST API), game and film profiles, upcoming releases."""

from __future__ import annotations

import html as html_lib
import re
from datetime import date
from typing import Annotated, Any, Literal
from urllib.parse import unquote

from pydantic import Field

from .http import REST, SITE, ApiError, fetch
from .registry import tool

# Category ids of gamefa.com's WordPress categories (checked 2026-10-31). Sub-categories are included by the API.
CATS = {
    "game": 1,
    "news": 3,
    "analysis": 4,
    "reviews": 9,
    "trailers": 1999,
    "training": 2299,
    "music": 2073,
    "best-lists": 43745,
    "scores": 107703,  # Metacritic/OpenCritic score roundups
    "playstation": 62716,
    "pc": 50,
    "xbox": 50227,
    "nintendo": 23433,
    "mobile": 2728,
    "cinema": 75295,
    "cinema-news": 75649,
    "film-reviews": 75657,
    "anime": 89951,
    "iran-cinema": 75658,
    "film-scores": 107704,
    "best-movies": 97058,
    "film-trailers": 75660,
    "tech": 75663,
    "tech-news": 2854,
}
CAT_NAMES = {v: k for k, v in CATS.items()}
Category = Literal[
    "game", "news", "analysis", "reviews", "trailers", "training", "music", "best-lists", "scores", "playstation", "pc",
    "xbox", "nintendo", "mobile", "cinema", "cinema-news", "film-reviews", "anime", "iran-cinema", "film-scores",
    "best-movies", "film-trailers", "tech", "tech-news",
]  # fmt: skip
CategoryArg = Annotated[
    Category | None,
    Field(description="Limit to one section: news, reviews, analysis, trailers, training, scores (Metacritic roundups), best-lists, pc, playstation, xbox, nintendo, mobile, cinema, film-reviews, anime, tech... Omit for everything."),
]  # fmt: skip
Page = Annotated[int, Field(description="Page number, starting at 1.", ge=1, le=500)]
Limit = Annotated[int, Field(description="Results per page.", ge=1, le=30)]
Slug = Annotated[str, Field(pattern=r"^[A-Za-z0-9._-]{1,120}$", max_length=120)]
Year = Annotated[int, Field(description="Calendar year (Gregorian), e.g. 2025.", ge=1950, le=2100)]
TagArg = Annotated[
    str | None,
    Field(
        description="Topic tag slug or id (a game, franchise, studio or person) from gf_terms(kind='tag'), e.g. elden-ring.",
        pattern=r"^[A-Za-z0-9%_.-]{1,200}$",
    ),
]  # fmt: skip

SORTS = {
    "default": None,
    "top_rated": "score-desc",  # Gamefa score; for films the IMDb score
    "top_users": "user-score-desc",
    "lowest_rated": "score-asc",
    "upcoming": "publish",  # release date ascending, from today on
    "newest": "publish-desc",
    "oldest": "publish-asc",
}
Sort = Annotated[
    Literal["default", "top_rated", "top_users", "lowest_rated", "upcoming", "newest", "oldest"],
    Field(description="Order of the list. upcoming = not yet released, soonest first; newest = by release date, latest first (includes unreleased). top_rated = Gamefa editors' score."),
]  # fmt: skip

_FA = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
MONTHS = "فروردین اردیبهشت خرداد تیر مرداد شهریور مهر آبان آذر دی بهمن اسفند".split()
LABELS = {  # row label of a profile page -> (key, is_list)
    "پلتفرم": ("platforms", True),
    "ژانر": ("genres", True),
    "سازنده": ("developers", True),
    "ناشر": ("publishers", True),
    "تاریخ انتشار": ("release", False),
    "امتیاز متاکریتیک": ("metacritic", False),
    "وبسایت رسمی": ("website", False),  # the page spells it with a ZWNJ; labels are compared without
    "میانگین ساعت بازی": ("avg_hours", False),
    "سال": ("year", False),
    "کشور": ("countries", True),
    "زبان": ("languages", True),
    "کارگردان": ("directors", True),
    "بازیگران": ("cast", True),
    "نویسنده": ("writers", True),
    "کمپانی": ("companies", True),
    "امتیاز IMDb": ("imdb", False),
    "امتیاز Metacritic": ("metacritic", False),
    "مدت زمان": ("runtime_min", False),
    "درجه سنی": ("age_rating", False),
    "هزینه ساخت": ("budget", False),
    "تعداد فصلها": ("seasons", False),
}


SCAN_PAGES = 8  # site pages of 36 scanned when a filter is combined with a sort


def _norm(s: str) -> str:
    """'PlayStation 5' / 'playstation-5' -> 'playstation5'."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _en(s: str) -> str:
    return s.translate(_FA)


def _text(h: str) -> str:
    """HTML fragment -> plain text with paragraph breaks."""
    h = re.sub(r"<(script|style|svg)\b.*?</\1>", "", h, flags=re.S)
    h = re.sub(r"</(p|div|li|h\d|tr|figure)>|<br\s*/?>", "\n", h)
    t = html_lib.unescape(re.sub(r"<[^>]+>", "", h))
    return re.sub(r"\n\s*\n+", "\n\n", re.sub(r"[^\S\n]+", " ", t)).strip()


def _line(h: str) -> str:
    return " ".join(_text(h).split())


def _greg(jy: int, jm: int, jd: int) -> str:
    """Jalali date -> ISO Gregorian date."""
    jy += 1595
    days = (
        -355668
        + 365 * jy
        + (jy // 33) * 8
        + (jy % 33 + 3) // 4
        + jd
        + ((jm - 1) * 31 if jm < 7 else (jm - 7) * 30 + 186)
    )
    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    leap = gy % 4 == 0 and gy % 100 != 0 or gy % 400 == 0
    mdays = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 0
    while gd > mdays[gm]:
        gd -= mdays[gm]
        gm += 1
    return f"{gy:04d}-{gm + 1:02d}-{gd:02d}"


def _release(s: str) -> dict[str, str] | None:
    """'1405/06/13' or '13 شهریور 1405' -> {jalali, date}; None if it is neither."""
    s = _en(s).strip()
    m = re.fullmatch(r"(\d{4})/(\d{1,2})/(\d{1,2})", s)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.fullmatch(r"(\d{1,2}) (\S+) (\d{4})", s)
        if not m or m.group(2) not in MONTHS:
            return None
        d, y, mo = int(m.group(1)), int(m.group(3)), MONTHS.index(m.group(2)) + 1
    try:
        return {"jalali": f"{y}/{mo:02d}/{d:02d}", "date": _greg(y, mo, d)}
    except IndexError:
        return None


def _num(s: str | None) -> float | int | None:
    s = _en(s or "").replace(",", "").replace("٫", ".").strip()
    if not re.fullmatch(r"\d+(\.\d+)?", s):
        return None  # e.g. "نامشخص" (unknown) or empty
    return float(s) if "." in s else int(s)


def _count(s: str) -> int | None:
    """'6.4k' / '۱۰,۲۰۰' -> int."""
    s = _en(s).replace(",", "").strip().lower()
    m = re.match(r"(\d+(?:\.\d+)?)(k?)", s)
    return round(float(m.group(1)) * (1000 if m.group(2) else 1)) if m else None


def _date(s: str) -> str:
    return s[:10]


# ---- articles (WordPress REST API) ----------------------------------------------------------------------------


def _post(p: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": p["id"],
        "title": _line(p["title"]["rendered"]),
        "date": _date(p["date"]),
        "url": p["link"],
        "sections": [CAT_NAMES[c] for c in p.get("categories", []) if c in CAT_NAMES],
        "summary": _line(p["excerpt"]["rendered"]) if p.get("excerpt") else None,
    }


async def _tag_id(tag: str) -> int:
    """Tag slug (or id) -> id."""
    if tag.isdigit():
        return int(tag)
    found = await fetch(f"{REST}/tags", {"slug": unquote(tag), "_fields": "id"})
    if not found:
        raise ApiError(f"No tag {tag!r}. Find slugs with gf_terms(kind='tag', query=...).", 404)
    return found[0]["id"]


async def _articles(
    query: str | None,
    category: str | None,
    page: int,
    limit: int,
    tag: str | None = None,
    year: int | None = None,
) -> dict[str, Any]:
    params = {
        "per_page": limit,
        "page": page,
        "search": query,
        "categories": CATS[category] if category else None,
        "tags": await _tag_id(tag) if tag else None,
        "after": f"{year}-01-01T00:00:00" if year else None,
        "before": f"{year + 1}-01-01T00:00:00" if year else None,
        "_fields": "id,title,date,link,excerpt,categories",
    }
    try:
        posts = await fetch(f"{REST}/posts", params)
    except ApiError as e:
        if e.status != 400:
            raise
        posts = []  # page past the end
    return {"page": page, "count": len(posts), "articles": [_post(p) for p in posts]}


@tool("Search articles")
async def gf_search_articles(
    query: Annotated[
        str,
        Field(
            description="Words to find, Persian or English (e.g. GTA 6, نقد، Elden Ring).", min_length=1, max_length=100
        ),
    ],
    category: CategoryArg = None,
    page: Page = 1,
    limit: Limit = 10,
    tag: TagArg = None,
    year: Year | None = None,
) -> dict[str, Any]:
    """Search Gamefa's news, reviews and features by keyword, newest matches first.

    Use for "what has Gamefa written about X". Returns id, title, date, url and a short summary per article.
    `tag` narrows to one topic tag, `year` to one publishing year. Call gf_article with an id to read the full
    text. For the score of a reviewed game use gf_game or gf_reviews.
    """
    return await _articles(query, category, page, limit, tag, year)


@tool("Latest articles")
async def gf_latest_articles(
    category: CategoryArg = None,
    page: Page = 1,
    limit: Limit = 10,
    tag: TagArg = None,
    year: Year | None = None,
) -> dict[str, Any]:
    """List the newest Gamefa articles, optionally for one section such as news, reviews, trailers or pc.

    Use for "what is new at Gamefa" or "latest PlayStation news". Returns id, title, date, url and a short summary.
    For yearly top lists use category best-lists (or scores for Metacritic roundups) with `year`; for everything
    about one game use `tag` (find it with gf_terms). Call gf_article to read one; gf_popular ranks by views.
    """
    return await _articles(None, category, page, limit, tag, year)


def _verdict(h: str) -> dict[str, Any] | None:
    """The score box Gamefa's editors put at the end of a review (class gft-verdict)."""
    i = h.find("gft-verdict")
    if i < 0:
        return None
    part = h[i:]

    def one(cls: str) -> str | None:
        m = re.search(rf'class="gft-verdict__{cls}[^"]*"[^>]*>(.*?)</p>', part, flags=re.S)
        return _line(m.group(1)) if m else None

    def items(cls: str) -> list[str]:
        m = re.search(rf'gft-verdict__{cls}"(.*?)</ul>', part, flags=re.S)
        return [_line(x) for x in re.findall(r"<li>(.*?)</li>", m.group(1), flags=re.S)] if m else []

    return {
        "score": _num(one("score")),
        "label": one("label"),
        "reviewed_on": one("meta"),
        "verdict": one("summary"),
        "pros": items("pros"),
        "cons": items("cons"),
    }


@tool("Read an article")
async def gf_article(
    article: Annotated[
        str,
        Field(
            description="Article id (digits, from the search/latest tools) or the slug from its URL.",
            min_length=1,
            max_length=150,
        ),
    ],
    max_chars: Annotated[
        int, Field(description="Cut the text at this length; truncated=true tells you more exists.", ge=500, le=30000)
    ] = 8000,
) -> dict[str, Any]:
    """Read one Gamefa article as plain text, with the editors' score box when it is a review.

    Use after gf_search_articles, gf_latest_articles or gf_popular. Reviews carry `review` with score (out of 10),
    label, verdict, pros and cons. `tags` are the topic tags (pass a slug to the `tag` filter of the search tools, or
    use the article id with gf_comments). Images and videos are dropped; the text is Persian.
    """
    fields = {"_fields": "id,title,date,modified,link,content,categories,tags"}
    if article.isdigit():
        p = await fetch(f"{REST}/posts/{article}", fields)
    else:
        found = await fetch(f"{REST}/posts", {**fields, "slug": article})
        if not found:
            raise ApiError(f"No article with slug {article!r}.", 404)
        p = found[0]
    h = p["content"]["rendered"]
    cut = h.find('<div style="--gft-score')
    text = _text(h[:cut] if cut > 0 else h)
    tags = []
    if p.get("tags"):
        found = await fetch(f"{REST}/tags", {"include": ",".join(map(str, p["tags"][:20])), "_fields": "slug,name"})
        tags = [{"name": t["name"], "slug": t["slug"]} for t in found]
    return {
        **_post({**p, "excerpt": None}),
        "modified": _date(p["modified"]),
        "tags": tags,
        "review": _verdict(h),
        "text": text[:max_chars],
        "truncated": len(text) > max_chars,
    }


@tool("Game reviews with scores")
async def gf_reviews(
    page: Page = 1,
    limit: Annotated[int, Field(description="Reviews per page.", ge=1, le=15)] = 8,
    query: Annotated[
        str | None, Field(description="Optional words to narrow to one game, e.g. Elden Ring.", max_length=100)
    ] = None,
    year: Year | None = None,
    min_score: Annotated[float | None, Field(description="Keep only reviews scoring at least this (0-10).", ge=0, le=10)] = None,
) -> dict[str, Any]:  # fmt: skip
    """List Gamefa's game reviews (نقد و بررسی) newest first, each with the editors' score out of 10, label, pros and cons.

    Use for "how did Gamefa rate X" or "latest reviews"; `year` limits to one publishing year and `min_score` keeps
    only the high scorers (filtered after paging, so a page may return fewer than `limit`).
    Older reviews may have no score box (score is then missing).
    Call gf_article with the id for the full review text. For a game's profile score use gf_game.
    """
    params = {
        "per_page": limit,
        "page": page,
        "categories": CATS["reviews"],
        "search": query,
        "after": f"{year}-01-01T00:00:00" if year else None,
        "before": f"{year + 1}-01-01T00:00:00" if year else None,
        "_fields": "id,title,date,link,content",
    }
    try:
        posts = await fetch(f"{REST}/posts", params)
    except ApiError as e:
        if e.status != 400:
            raise
        posts = []
    out = []
    for p in posts:
        v = _verdict(p["content"]["rendered"]) or {}
        if min_score is not None and (v.get("score") or 0) < min_score:
            continue
        out.append(
            {
                "id": p["id"],
                "title": _line(p["title"]["rendered"]),
                "date": _date(p["date"]),
                "url": p["link"],
                "score": v.get("score"),
                "label": v.get("label"),
                "reviewed_on": v.get("reviewed_on"),
                "pros": v.get("pros"),
                "cons": v.get("cons"),
            }
        )
    return {"page": page, "count": len(out), "reviews": out}


# ---- popular (server-rendered list) -----------------------------------------------------------------------------

POP_CATS = {"all": "0", "game": "1", "cinema": "75295", "tech": "75663", "video": "1999,75660"}


@tool("Most read articles")
async def gf_popular(
    period: Annotated[
        Literal["week", "month", "season", "year"], Field(description="Time window for the view counts.")
    ] = "week",
    section: Annotated[Literal["all", "game", "cinema", "tech", "video"], Field(description="Site section.")] = "game",
    limit: Limit = 15,
) -> dict[str, Any]:
    """List the most viewed Gamefa articles of the past week, month, season or year, most viewed first.

    Use for "what is trending at Gamefa". Returns id, title, url and view/comment/like counts; read one with gf_article.
    """
    page = await fetch(f"{SITE}/popular/", {"cat": POP_CATS[section], "time": period}, html=True)
    out = []
    for m in re.finditer(r'<article class="vertical-post-article">(.*?)</article>', page, flags=re.S):
        b = m.group(1)
        href = re.search(r'href="([^"]+)"', b)
        title = re.search(r'class="title[^"]*" title="([^"]*)"', b)
        nums = re.findall(
            r'class="(view|comment|like)-count[^"]*">(?:<svg.*?</svg>|\s)*<span>([^<]*)</span>', b, flags=re.S
        )
        counts = {k: _count(v) for k, v in nums}
        if href and title:
            pid, slug = re.search(r"/(\d+)/([^/]+)/?$", href.group(1)).groups()
            out.append(
                {
                    "id": int(pid),
                    "title": html_lib.unescape(title.group(1)),
                    "slug": slug,
                    "url": href.group(1),
                    "views": counts.get("view"),
                    "comments": counts.get("comment"),
                    "likes": counts.get("like"),
                }
            )
    return {"period": period, "section": section, "articles": out[:limit]}


# ---- game and film profiles (server-rendered pages) -----------------------------------------------------------------

_CARD = re.compile(
    r'<a href="(https://gamefa\.com/(games|film)/([^"/]+)/)" class="d-block game-content-box-comp">(.*?)</a>', re.S
)


def _cards(page: str) -> list[dict[str, Any]]:
    out = []
    for m in _CARD.finditer(page):
        url, kind, slug, b = m.groups()

        def g(p: str, b: str = b) -> str | None:
            r = re.search(p, b, flags=re.S)
            return r.group(1) if r else None

        def spans(cls: str, b: str = b) -> list[str]:
            r = re.search(rf'class="{cls}[^"]*"[^>]*>(.*?)</div>', b, flags=re.S)
            return [html_lib.unescape(x) for x in re.findall(r"<span>([^<]*)</span>", r.group(1))] if r else []

        us = _en(g(r'title="امتیاز کاربران: ([^"]*)"') or "")
        um = re.match(r"([\d.]+) از 10 - (\d+) رای", us)
        cat = re.search(r'class="category[^"]*">(.*?)</div>', b, flags=re.S)
        rel = g(r'class="publish-time[^>]*>.*?<span>([^<]*)</span>')
        director = g(r'class="director[^>]*>(.*?)</div>')
        out.append(
            {
                "slug": slug,
                "url": url,
                "type": "game" if kind == "games" else "film",
                "title": html_lib.unescape(g(r'class="title mb-0" title="([^"]*)"') or slug),
                "gamefa_score": _num(g(r'class="gamefa-score"[^>]*>([^<]*)<')),
                "user_score": float(um.group(1)) if um else None,
                "user_votes": int(um.group(2)) if um else None,
                "imdb": _num(_line(g(r'class="imdb_rating[^>]*>(.*?)</div>') or "")),
                "genres": [html_lib.unescape(x) for x in re.findall(r"<span>([^<]*)</span>", cat.group(1))]
                if cat
                else [],
                "platforms": spans("platform"),
                "publisher": (spans("publisher") or [None])[0],
                "director": _line(director) if director else None,
                "release": _release(rel) if rel else None,
            }
        )
    return out


# filter name -> (URL prefix of the term archive, REST base of the taxonomy)
GAME_TERMS = {
    "platform": ("platform", "platform"),
    "genre": ("genre", "genre"),
    "developer": ("developer", "developer"),
    "publisher": ("publisher", "publisher"),
}
FILM_TERMS = {
    "type": ("films", "film_category"),
    "genre": ("films/genre", "film_genre"),
    "person": ("films/person", "film_person"),
    "company": ("films/company", "film_company"),
    "country": ("films/country", "film_country"),
    "language": ("films/language", "film_language"),
    "year": ("films/year", "film_year"),
}
SCANNABLE = {"games": ("platform", "genre", "publisher"), "film": ("genre",)}  # filters a card shows


def _ymd(c: dict[str, Any]) -> str:
    return (c.get("release") or {}).get("date") or ""


def _local_sort(items: list[dict[str, Any]], sort: str, kind: str) -> list[dict[str, Any]]:
    """Sort cards the way the site's `orderby` would; cards without the value go last."""
    score = "gamefa_score" if kind == "games" else "imdb"
    key, rev = {
        "top_rated": (lambda c: c.get(score), True),
        "lowest_rated": (lambda c: c.get(score), False),
        "top_users": (lambda c: c.get("user_score"), True),
        "newest": (lambda c: _ymd(c) or None, True),
        "oldest": (lambda c: _ymd(c) or None, False),
        "upcoming": (lambda c: _ymd(c) or None, False),
    }.get(sort, (lambda c: 0, False))
    if sort == "upcoming":
        items = [c for c in items if _ymd(c) >= date.today().isoformat()]
    return sorted((c for c in items if key(c) is not None), key=key, reverse=rev) + [c for c in items if key(c) is None]


def _has_term(c: dict[str, Any], arg: str, slug: str) -> bool:
    names = {"platform": c["platforms"], "genre": c["genres"], "publisher": [c["publisher"] or ""]}[arg]
    return _norm(slug) in map(_norm, names)


async def _term_count(rest_base: str, slug: str) -> int | None:
    try:
        r = await fetch(f"{REST}/{rest_base}", {"slug": slug, "_fields": "count"})
    except ApiError:
        return None
    return r[0]["count"] if r else None


def _paged(path: str, n: int) -> str:
    return path + (f"page/{n}/" if n > 1 else "")


async def _profiles(
    kind: str,
    sort: str,
    query: str | None,
    taxonomy: tuple[str, str] | None,
    page: int,
    limit: int,
    *,
    year: int | None = None,
    month: str | None = None,
    depth: int = SCAN_PAGES,
) -> dict[str, Any]:
    if taxonomy and query:
        raise ApiError("Use either `query` or a filter (platform, genre, ...), not both: the site cannot combine them.")
    flt = bool(year or month)  # a release-date filter on game cards (film years are an archive)
    prefix, rest = ("", "")
    if taxonomy:
        arg, slug = taxonomy
        prefix, rest = (GAME_TERMS if kind == "games" else FILM_TERMS)[arg]
        if arg == "type":
            slug = {"series": "tvseries"}.get(slug, slug)
        archive = f"{SITE}/{prefix}/{slug}/"
    if not taxonomy and not flt:
        items = _cards(await fetch(_paged(f"{SITE}/{kind}/", page), {"orderby": SORTS[sort], "q": query}, html=True))
        return {"page": page, "count": len(items[:limit]), "items": items[:limit]}
    if taxonomy and sort == "default" and not flt:  # the site's own term archive: no sorting, but real paging
        items = _cards(await fetch(_paged(archive, page), html=True))[:limit]
        return {"page": page, "count": len(items), "items": items}

    def keep(c: dict[str, Any]) -> bool:
        d = _ymd(c)
        return (not year or d[:4] == str(year)) and (not month or d[:7] == month)

    total = await _term_count(rest, slug) if taxonomy else None
    if taxonomy and total is not None and total <= depth * 36:
        # small archive: read all of it and sort here, so the answer is complete
        cards: list[dict[str, Any]] = []
        for n in range(1, -(-max(total, 1) // 36) + 1):
            cards += _cards(await fetch(_paged(archive, n), html=True))
        cards = [c for c in _local_sort(cards, sort, kind) if keep(c)]
        items = cards[(page - 1) * limit : page * limit]
        return {"page": page, "count": len(items), "total": len(cards), "complete": True, "items": items}
    if taxonomy and arg not in SCANNABLE[kind]:
        # shortcut: a big archive nobody can sort, so only its first `depth` pages are read and sorted here.
        cards = []
        for n in range(1, depth + 1):
            batch = _cards(await fetch(_paged(archive, n), html=True))
            cards += batch
            if len(batch) < 36:
                break
        cards = [c for c in _local_sort(cards, sort, kind) if keep(c)]
        items = cards[(page - 1) * limit : page * limit]
        return {"page": page, "count": len(items), "partial": True, "scanned_pages": n, "items": items}
    # shortcut: scan the sorted site-wide list and keep matches; matches deeper than depth * 36 cards are not seen.
    order = SORTS[sort] if sort != "default" else ("publish-desc" if flt else None)
    found: list[dict[str, Any]] = []
    for n in range(1, depth + 1):
        batch = _cards(await fetch(_paged(f"{SITE}/{kind}/", n), {"orderby": order, "q": query}, html=True))
        found += [c for c in batch if keep(c) and (not taxonomy or _has_term(c, arg, slug))]
        dates = [_ymd(c) for c in batch if _ymd(c)]
        past = month and dates and sort in ("upcoming", "oldest") and dates[-1][:7] > month
        if len(found) >= page * limit or len(batch) < 36 or past:
            break
    items = found[(page - 1) * limit : page * limit]
    return {"page": page, "count": len(items), "scanned_pages": n, "items": items}


def _tax(allowed: tuple[str, ...], **given: Any) -> tuple[str, str] | None:
    given = {k: v for k, v in given.items() if v}
    if len(given) > 1:
        raise ApiError(f"Give only one of {', '.join(allowed)}: the site cannot combine them.")
    return next(iter(given.items())) if given else None


TermArg = Annotated[str | None, Field(description="URL slug from gf_game output.", pattern=r"^[a-z0-9-]{1,80}$")]
Depth = Annotated[
    int,
    Field(
        description="Only when a filter is combined with a sort or year: site pages of 36 to scan (one request each).",
        ge=1,
        le=25,
    ),
]  # fmt: skip


@tool("Game profiles")
async def gf_games(
    query: Annotated[
        str | None,
        Field(
            description="Part of a game title, e.g. elden ring. Not combinable with the filters below.", max_length=100
        ),
    ] = None,
    sort: Sort = "default",
    platform: Annotated[
        str | None,
        Field(
            description="Platform slug: pc, playstation-5, playstation-4, xbox-series-x-s, nintendo-switch, ...",
            pattern=r"^[a-z0-9-]{1,80}$",
        ),
    ] = None,
    genre: Annotated[
        str | None,
        Field(description="Genre slug, e.g. action, rpg, platformer, shooter.", pattern=r"^[a-z0-9-]{1,80}$"),
    ] = None,
    developer: TermArg = None,
    publisher: TermArg = None,
    page: Page = 1,
    limit: Annotated[int, Field(description="Games per page (the site sends 36).", ge=1, le=36)] = 12,
    year: Annotated[int | None, Field(description="Only games released in this Gregorian year.", ge=1970, le=2100)] = None,
    depth: Depth = SCAN_PAGES,
) -> dict[str, Any]:  # fmt: skip
    """Browse or search Gamefa's game profiles with the editors' score, user score, genres, platforms and release date.

    Use for "best rated PS5 games", "games by Capcom", "best games of 2024" or finding one game's slug. Sort
    top_rated lists the highest Gamefa scores. Give at most one of platform, genre, developer, publisher; query
    works alone. Small filters (up to 288 games, e.g. most developers and publishers) are read completely and
    sorted here (`complete`: true); for big ones a sort or `year` scans the first `depth` pages (default 8 = 288
    games) of the sorted site list, so raise `depth` for deeper results. Find slugs with gf_terms. Release dates
    come as Jalali plus ISO. Call gf_game with a slug for the full profile; gf_upcoming_games lists unreleased ones.
    """
    tax = _tax(
        ("platform", "genre", "developer", "publisher"),
        platform=platform,
        genre=genre,
        developer=developer,
        publisher=publisher,
    )
    return await _profiles("games", sort, query, tax, page, limit, year=year, depth=depth)  # fmt: skip


@tool("Upcoming game releases")
async def gf_upcoming_games(
    platform: Annotated[
        str | None,
        Field(
            description="Optional platform slug: pc, playstation-5, xbox-series-x-s, nintendo-switch, ...",
            pattern=r"^[a-z0-9-]{1,80}$",
        ),
    ] = None,
    page: Page = 1,
    limit: Annotated[int, Field(description="Games per page (the site sends 36).", ge=1, le=36)] = 15,
    month: Annotated[
        str | None,
        Field(description="Only releases in this month, ISO form YYYY-MM, e.g. 2026-12.", pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    ] = None,
    genre: Annotated[str | None, Field(description="Optional genre slug (not together with platform).", pattern=r"^[a-z0-9-]{1,80}$")] = None,
    depth: Depth = SCAN_PAGES,
) -> dict[str, Any]:  # fmt: skip
    """List games that have not been released yet, soonest first (Gamefa's release calendar), with ISO release dates.

    Use for "what comes out next", "upcoming PS5 games" or "games releasing in December 2026" (`month`). Dates are
    what Gamefa has; a far-off date may be a placeholder. Months far ahead scan up to `depth` pages.
    Call gf_game with a slug for details, or gf_search_articles for the news about it.
    """
    tax = _tax(("platform", "genre"), platform=platform, genre=genre)
    return await _profiles("games", "upcoming", None, tax, page, limit, month=month, depth=depth)


@tool("Film and series profiles")
async def gf_films(
    query: Annotated[
        str | None, Field(description="Part of a title, in English, e.g. breaking bad.", max_length=100)
    ] = None,
    sort: Sort = "default",
    page: Page = 1,
    limit: Annotated[int, Field(description="Titles per page (the site sends 36).", ge=1, le=36)] = 12,
    type: Annotated[Literal["movie", "series"] | None, Field(description="Only films or only TV series.")] = None,
    genre: Annotated[str | None, Field(description="Film genre slug, e.g. drama, horror, sci-fi.", pattern=r"^[a-z0-9-]{1,80}$")] = None,
    person: Annotated[str | None, Field(description="Actor/director slug, e.g. christopher-nolan.", pattern=r"^[a-z0-9-]{1,80}$")] = None,
    company: Annotated[str | None, Field(description="Studio slug, e.g. warner-bros.", pattern=r"^[a-z0-9-]{1,80}$")] = None,
    country: Annotated[str | None, Field(description="Country slug, e.g. usa.", pattern=r"^[a-z0-9-]{1,80}$")] = None,
    language: Annotated[str | None, Field(description="Language slug, e.g. english.", pattern=r"^[a-z0-9-]{1,80}$")] = None,
    year: Annotated[int | None, Field(description="Release year of the film or series.", ge=1900, le=2100)] = None,
    depth: Depth = SCAN_PAGES,
) -> dict[str, Any]:  # fmt: skip
    """Browse or search Gamefa's film and TV series profiles with IMDb score, user score, genres, director and release date.

    Use for "top rated films on Gamefa", "best TV series" (type=series), "Nolan films" or finding a slug. top_rated
    sorts by IMDb score; there is no Gamefa editors' score for films. Give at most one of type, genre, person,
    company, country, language, year; query works alone. Small sets are read completely (`complete`: true),
    big ones only through their first `depth` pages (`partial`: true). Find slugs with gf_terms. Call gf_film with a
    slug for cast, runtime and more.
    """
    tax = _tax(
        ("type", "genre", "person", "company", "country", "language", "year"),
        type=type, genre=genre, person=person, company=company, country=country, language=language,
        year=str(year) if year else None,
    )  # fmt: skip
    return await _profiles("film", sort, query, tax, page, limit, depth=depth)


async def _profile(kind: str, slug: str) -> dict[str, Any]:
    page = await fetch(f"{SITE}/{kind}/{slug}/", html=True)
    h1 = re.search(r'<h1 class="(?:game|film)-title[^>]*>(.*?)</h1>', page, flags=re.S)
    if not h1:
        raise ApiError(f"No {kind} profile {slug!r}.", 404)
    out: dict[str, Any] = {"slug": slug, "url": f"{SITE}/{kind}/{slug}/", "title": _line(h1.group(1))}
    pid = re.search(r'data-post-id="(\d+)"', page)
    if pid:
        out["post_id"] = int(pid.group(1))  # for gf_comments
    box = re.search(
        r'score-box diginoy-score[^>]*>\s*<span class="title">[^<]*</span>\s*<div class="score-number">\s*<span>([^<]*)</span>',
        page,
        flags=re.S,
    )
    if kind == "games":  # films have no editors' score box value
        out["gamefa_score"] = _num(box.group(1)) if box else None
    ld = re.search(r'"ratingValue":\s*"([\d.]+)".*?"ratingCount":\s*(\d+)', page, flags=re.S)
    if ld:
        out["user_score"], out["user_votes"] = float(ld.group(1)), int(ld.group(2))
    table = re.search(r'<table class="property-table.*?</table>', page, flags=re.S)
    if table:
        desc = re.search(r'<div class="content">(.*?)</div>\s*$', page[: table.start()], flags=re.S)
        out["description"] = _text(desc.group(1)) if desc else None
        for row in re.findall(r"<tr><th>(.*?)</th><td>(.*?)</td></tr>", table.group(0), flags=re.S):
            label, val = _line(row[0]).replace(chr(0x200C), ""), row[1]
            if label.startswith("صفحه بررسی"):
                link = re.search(r'href="([^"]+)"', val)
                out["review_url"] = link.group(1) if link else None
                continue
            key, many = LABELS.get(label, (label, False))
            if kind == "film" and key == "developers":  # a series page calls its creator "developer"
                key = "creators"
            items = [_line(x) for x in re.split(r'<span class="seprator">', val) if _line(x).strip("| ")]
            items = [x.strip("| ") for x in items]
            if key in ("platforms", "genres", "developers", "publishers"):
                slugs = re.findall(r'href="https://gamefa\.com/[a-z]+/([^"/]+)/"', val)
                out[key] = (
                    [{"name": n, "slug": s} for n, s in zip(items, slugs, strict=True)]
                    if len(slugs) == len(items)
                    else items
                )
            elif key == "release":
                out[key] = _release(items[0]) if items else None
            elif many:
                out[key] = items
            else:
                out[key] = (
                    _num(items[0])
                    if key in ("metacritic", "imdb", "avg_hours", "runtime_min", "year", "seasons")
                    else (items[0] if items else None)
                )
    return out


@tool("Game profile")
async def gf_game(
    slug: Annotated[Slug, Field(description="Game slug from gf_games or gf_upcoming_games, e.g. elden-ring.")],
) -> dict[str, Any]:
    """Get one game's Gamefa profile: editors' score, user score and votes, Metacritic, release date, description.

    Also platforms, genres, developers and publishers with slugs you can pass to gf_games as filters, the official
    website, average playtime and the URL of Gamefa's review article (read it with gf_article).
    """
    return await _profile("games", slug)


@tool("Film profile")
async def gf_film(
    slug: Annotated[
        Slug, Field(description="Film or series slug from gf_films, e.g. killers-of-the-flower-moon-2023.")
    ],
) -> dict[str, Any]:
    """Get one film or series profile: IMDb and user score, genres, cast, director, writers, countries, runtime, release date.

    Slugs come from gf_films. Text is as Gamefa has it (mostly English names, Persian description).
    """
    return await _profile("film", slug)


# ---- slugs, comments and related items --------------------------------------------------------------------------

TERM_KINDS = {  # gf_terms kind -> REST base
    "platform": "platform",
    "genre": "genre",
    "developer": "developer",
    "publisher": "publisher",
    "film_type": "film_category",
    "film_genre": "film_genre",
    "film_person": "film_person",
    "film_company": "film_company",
    "film_country": "film_country",
    "film_language": "film_language",
    "tag": "tags",
}


@tool("Find filter slugs")
async def gf_terms(
    kind: Annotated[
        Literal[
            "platform", "genre", "developer", "publisher", "film_type", "film_genre", "film_person", "film_company",
            "film_country", "film_language", "tag",
        ],
        Field(description="What to look up: game platform/genre/developer/publisher, film_* equivalents, or tag (article topics)."),
    ],  # fmt: skip
    query: Annotated[str | None, Field(description="Name or part of it, e.g. capcom, nolan, elden.", max_length=60)] = None,
    limit: Annotated[int, Field(description="Results to return.", ge=1, le=50)] = 15,
) -> dict[str, Any]:  # fmt: skip
    """Find the slug of a platform, genre, developer, publisher, film person or studio, or an article topic tag.

    Use before gf_games, gf_films or the `tag` filter of the article tools when you only know a name. Each hit has
    slug, name and the number of games/films/articles under it; without `query` the biggest ones come first.
    """
    params = {
        "per_page": limit,
        "search": query,
        "orderby": None if query else "count",
        "order": None if query else "desc",
    }
    found = await fetch(f"{REST}/{TERM_KINDS[kind]}", {**params, "_fields": "id,slug,name,count"})  # fmt: skip
    return {
        "kind": kind,
        "terms": [{"slug": t["slug"], "name": html_lib.unescape(t["name"]), "count": t["count"]} for t in found],
    }


@tool("Comments on an article or profile")
async def gf_comments(
    post_id: Annotated[
        int, Field(description="Article id (from the article tools) or a game/film `post_id` from gf_game / gf_film.", ge=1)
    ],
    sort: Annotated[Literal["newest", "oldest"], Field(description="Order by date.")] = "newest",
    page: Page = 1,
    limit: Annotated[int, Field(description="Comments per page.", ge=1, le=50)] = 15,
) -> dict[str, Any]:  # fmt: skip
    """Read the public reader comments under a Gamefa article or a game/film profile, with likes and dislikes.

    Use for "what do readers think of X". On a game or film profile the comments are where users post their own
    verdicts and ratings. Replies carry `reply_to`, the parent comment id. Persian text, newest first by default.
    `author` is the name stored with the comment; a user may have renamed since.
    """
    params = {
        "post": post_id,
        "per_page": limit,
        "page": page,
        "orderby": "date",
        "order": "desc" if sort == "newest" else "asc",
        "_fields": "id,parent,date,author_name,content",
    }
    try:
        rows = await fetch(f"{REST}/comments", params)
    except ApiError as e:
        if e.status != 400:
            raise
        rows = []  # page past the end
    out = []
    for c in rows:
        h = c["content"]["rendered"]
        votes = {
            k: re.search(rf'wp_ulike_counter_{k}"[^>]*data-ulike-counter-value="(\d*)"', h) for k in ("up", "down")
        }
        out.append(
            {
                "id": c["id"],
                "reply_to": c["parent"] or None,
                "date": _date(c["date"]),
                "author": c["author_name"],
                "text": _text(h.split('<div class="comment-shortcode"')[0]),
                "likes": int(votes["up"].group(1) or 0) if votes["up"] else None,
                "dislikes": int(votes["down"].group(1) or 0) if votes["down"] else None,
            }
        )
    return {"post_id": post_id, "page": page, "count": len(out), "comments": out}


@tool("Related articles or titles")
async def gf_related(
    slug: Annotated[Slug, Field(description="Game or film slug, e.g. elden-ring.")],
    what: Annotated[
        Literal["articles", "similar"], Field(description="articles = Gamefa posts about it; similar = other games/films.")
    ] = "articles",
    type: Annotated[Literal["game", "film"], Field(description="Whether the slug is a game or a film/series.")] = "game",
) -> dict[str, Any]:  # fmt: skip
    """List the articles Gamefa links to a game or film profile, or the games/films it shows as similar.

    Use for "news and reviews about X" after gf_games or gf_films gave you the slug, or for "games like X". Articles
    carry id, title, date and counts (read one with gf_article); similar titles are profiles like gf_games returns.
    """
    kind = "games" if type == "game" else "film"
    section = "related-posts" if what == "articles" else f"related-{kind if kind == 'games' else 'films'}"
    page = await fetch(f"{SITE}/{kind}/{slug}/", {"section": section}, html=True)
    if "js-entity-tab-content" not in page:
        raise ApiError(f"No {type} profile {slug!r}.", 404)
    body = page[page.index("js-entity-tab-content") :]
    if what == "similar":
        return {"slug": slug, "similar": _cards(body)}
    out = []
    for m in re.finditer(r'<article class="post-horizontal-article">(.*?)</article>', body, flags=re.S):
        b = m.group(1)
        href = re.search(r'href="https://gamefa\.com/(\d+)/([^"/]+)/?"', b)
        title = re.search(r'<div class="title">(.*?)</div>', b, flags=re.S)
        when = re.search(r'datetime="([^"]+)"', b)
        nums = {
            k: re.search(rf'class="{k}-count">(?:<svg.*?</svg>|\s)*<span>([^<]*)</span>', b, flags=re.S)
            for k in ("comment", "like")
        }
        if href and title:
            out.append(
                {
                    "id": int(href.group(1)),
                    "title": _line(title.group(1)),
                    "url": href.group(0)[6:-1],
                    "date": _date(when.group(1)) if when else None,
                    "comments": _count(nums["comment"].group(1)) if nums["comment"] else None,
                    "likes": _count(nums["like"].group(1)) if nums["like"] else None,
                }
            )
    return {"slug": slug, "articles": out}

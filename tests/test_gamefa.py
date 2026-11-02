import httpx
import pytest
from conftest import FIXTURES, fixture, page

from gamefa_mcp import gamefa

pytestmark = pytest.mark.anyio


def page_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


TOOLS = {
    "gf_search_articles",
    "gf_latest_articles",
    "gf_article",
    "gf_reviews",
    "gf_popular",
    "gf_games",
    "gf_upcoming_games",
    "gf_game",
    "gf_films",
    "gf_film",
    "gf_terms",
    "gf_comments",
    "gf_related",
}


async def test_all_tools_are_read_only_and_described(client):
    tools = (await client.list_tools()).tools
    assert {t.name for t in tools} == TOOLS
    for t in tools:
        assert t.annotations.read_only_hint is True, t.name
        assert t.title and t.description.splitlines()[0].endswith("."), t.name


def test_jalali_to_iso():
    assert gamefa._release("۱۴۰۵/۰۸/۰۹") == {"jalali": "1405/08/09", "date": "2026-10-31"}
    assert gamefa._release("۲۸ فروردین ۱۳۹۸")["date"] == "2019-04-17"
    assert gamefa._release("نامشخص") is None


def test_numbers():
    assert gamefa._num("۹.۳") == 9.3 and gamefa._num("۸") == 8 and gamefa._num("نامشخص") is None
    assert gamefa._count("6.4k") == 6400 and gamefa._count("۱۰,۲۰۰") == 10200


async def test_search_articles_maps_sections(client, api):
    api["/wp-json/wp/v2/posts"] = fixture("posts.json")
    r = (await client.call_tool("gf_search_articles", {"query": "gta", "category": "news"})).structured_content
    assert r["count"] == 2 and r["articles"][0]["url"].startswith("https://gamefa.com/")
    q = api.calls[0].url.params
    assert q["search"] == "gta" and q["categories"] == "3"


async def test_article_without_known_sections_still_has_the_key(client, api):
    posts = fixture("posts.json")
    posts[0]["categories"] = [999999]
    api["/wp-json/wp/v2/posts"] = posts
    r = (await client.call_tool("gf_latest_articles", {})).structured_content
    assert r["articles"][0]["sections"] == []


async def test_article_has_review_box_and_truncates(client, api):
    api["/wp-json/wp/v2/posts/1624276"] = fixture("article.json")
    r = (await client.call_tool("gf_article", {"article": "1624276", "max_chars": 500})).structured_content
    assert r["review"]["score"] == 8.5 and r["review"]["pros"] and r["review"]["cons"]
    assert len(r["text"]) <= 500 and "gft-verdict" not in r["text"]


async def test_article_by_slug_not_found(client, api):
    api["/wp-json/wp/v2/posts"] = []
    assert (await client.call_tool("gf_article", {"article": "nope"})).is_error


async def test_reviews_scores(client, api):
    api["/wp-json/wp/v2/posts"] = fixture("reviews.json")
    r = (await client.call_tool("gf_reviews", {"limit": 3})).structured_content
    assert r["reviews"][0]["score"] == 8.5 and r["reviews"][0]["label"]
    assert api.calls[0].url.params["categories"] == "9"


async def test_reviews_past_last_page_is_empty(client, api):
    api["/wp-json/wp/v2/posts"] = lambda req: httpx.Response(400, json={"code": "rest_post_invalid_page_number"})
    r = (await client.call_tool("gf_reviews", {"page": 99})).structured_content
    assert r["count"] == 0


async def test_popular_counts(client, api):
    api["/popular/"] = page("popular.html")
    r = (await client.call_tool("gf_popular", {"period": "month", "section": "game"})).structured_content
    assert r["articles"][0]["views"] > 0 and r["articles"][0]["id"] > 0
    q = api.calls[0].url.params
    assert q["time"] == "month" and q["cat"] == "1"


async def test_games_list_sorted(client, api):
    api["/games/"] = page("games.html")
    r = (await client.call_tool("gf_games", {"sort": "top_rated", "query": "x"})).structured_content
    g = r["items"][0]
    assert g["gamefa_score"] == 10 and g["user_score"] == 9.6 and g["release"]["date"] == "2026-09-04"
    assert "PC" in g["platforms"] and g["slug"] == "onimusha-way-of-the-sword"
    q = api.calls[0].url.params
    assert q["orderby"] == "score-desc" and q["q"] == "x"


async def test_games_filter_with_sort_scans_and_filters(client, api):
    api["/games/"] = page("games.html")
    r = (await client.call_tool("gf_games", {"platform": "nintendo-switch", "sort": "top_rated"})).structured_content
    assert [x["slug"] for x in r["items"]] == ["animal-well"]


async def test_games_filter_alone_uses_term_archive(client, api):
    api["/platform/pc/page/2/"] = page("games.html")
    r = (await client.call_tool("gf_games", {"platform": "pc", "page": 2})).structured_content
    assert r["count"] == 3


async def test_games_filter_and_query_rejected(client, api):
    assert (await client.call_tool("gf_games", {"platform": "pc", "query": "x"})).is_error


async def test_upcoming_sort(client, api):
    api["/games/"] = page("games.html")
    await client.call_tool("gf_upcoming_games", {})
    assert api.calls[0].url.params["orderby"] == "publish"


async def test_game_profile(client, api):
    api["/games/onimusha-way-of-the-sword/"] = page("game.html")
    r = (await client.call_tool("gf_game", {"slug": "onimusha-way-of-the-sword"})).structured_content
    assert r["gamefa_score"] == 10 and r["user_score"] == 9.6 and r["release"]["jalali"] == "1405/06/13"
    assert {"name": "PC", "slug": "pc"} in r["platforms"] and r["developers"][0]["slug"] == "capcom"
    assert r["review_url"].startswith("https://gamefa.com/")


async def test_film_profile_and_list(client, api):
    api["/film/killers-of-the-flower-moon-2023/"] = page("filmpage.html")
    api["/film/"] = page("films.html")
    f = (await client.call_tool("gf_film", {"slug": "killers-of-the-flower-moon-2023"})).structured_content
    assert f["imdb"] == 9.5 and f["directors"] == ["Martin Scorsese"] and f["runtime_min"] == 206
    assert "gamefa_score" not in f
    r = (await client.call_tool("gf_films", {"sort": "top_rated"})).structured_content
    assert r["items"][0]["director"] and r["items"][0]["imdb"] == 9.5


async def test_unknown_profile_is_an_error(client, api):
    api["/games/zzz/"] = lambda req: httpx.Response(404, text="")
    assert (await client.call_tool("gf_game", {"slug": "zzz"})).is_error


async def test_terms_lookup(client, api):
    api["/wp-json/wp/v2/developer"] = fixture("terms.json")
    r = (await client.call_tool("gf_terms", {"kind": "developer", "query": "capcom"})).structured_content
    assert r["terms"][0] == {"slug": "capcom", "name": "Capcom", "count": 49}
    assert api.calls[0].url.params["search"] == "capcom"


async def test_comments_with_votes_and_replies(client, api):
    api["/wp-json/wp/v2/comments"] = fixture("comments.json")
    r = (await client.call_tool("gf_comments", {"post_id": 928874, "sort": "oldest"})).structured_content
    assert r["count"] == 3 and r["comments"][0]["text"] and "wp_ulike" not in r["comments"][0]["text"]
    assert any(c.get("reply_to") for c in r["comments"]) and r["comments"][0]["likes"] is not None
    q = api.calls[0].url.params
    assert q["post"] == "928874" and q["order"] == "asc"


async def test_related_articles_and_similar(client, api):
    api["/games/elden-ring/"] = lambda req: httpx.Response(
        200, text=page_text("related.html" if req.url.params["section"] == "related-posts" else "similar.html")
    )
    r = (await client.call_tool("gf_related", {"slug": "elden-ring"})).structured_content
    assert len(r["articles"]) == 3 and r["articles"][0]["id"] > 0 and r["articles"][0]["comments"] is not None
    s = (await client.call_tool("gf_related", {"slug": "elden-ring", "what": "similar"})).structured_content
    assert s["similar"][0]["type"] == "game" and s["similar"][0]["title"]


async def test_articles_by_tag_and_year(client, api):
    api["/wp-json/wp/v2/tags"] = [{"id": 61342}]
    api["/wp-json/wp/v2/posts"] = fixture("posts.json")
    await client.call_tool("gf_latest_articles", {"tag": "elden-ring", "year": 2025})
    q = api.calls[-1].url.params
    assert q["tags"] == "61342" and q["after"].startswith("2025-01-01") and q["before"].startswith("2026-01-01")


async def test_small_archive_is_read_completely_and_sorted(client, api):
    api["/wp-json/wp/v2/developer"] = [{"count": 3}]
    api["/developer/capcom/"] = page("games.html")
    r = (await client.call_tool("gf_games", {"developer": "capcom", "sort": "top_rated"})).structured_content
    scores = [x.get("gamefa_score") or -1 for x in r["items"]]
    assert r["complete"] is True and scores == sorted(scores, reverse=True)


async def test_year_filter_scans_sorted_list(client, api):
    api["/games/"] = page("games.html")
    r = (await client.call_tool("gf_games", {"year": 2026, "sort": "top_rated"})).structured_content
    assert r["items"] and all(x["release"]["date"].startswith("2026") for x in r["items"])


async def test_upcoming_month_filter(client, api):
    api["/games/"] = page("games.html")
    r = (await client.call_tool("gf_upcoming_games", {"month": "2026-09"})).structured_content
    assert all(x["release"]["date"].startswith("2026-09") for x in r["items"])


async def test_films_series_archive(client, api):
    api["/wp-json/wp/v2/film_category"] = [{"count": 36}]
    api["/films/tvseries/"] = page("films.html")
    r = (await client.call_tool("gf_films", {"type": "series", "sort": "top_rated"})).structured_content
    assert r["complete"] is True and r["items"][0]["imdb"] is not None


async def test_two_filters_rejected(client, api):
    assert (await client.call_tool("gf_films", {"genre": "drama", "type": "movie"})).is_error


async def test_request_headers_match_the_sites_frontend(api):
    from gamefa_mcp import http

    api["/wp-json/wp/v2/posts"] = []
    api["/popular/"] = []
    await http.fetch(f"{http.REST}/posts")
    h = api.calls[-1].headers
    assert h["accept"] == "*/*" and h["referer"] == "https://gamefa.com/" and "origin" not in h
    assert (h["sec-fetch-site"], h["sec-fetch-mode"], h["sec-fetch-dest"]) == ("same-origin", "cors", "empty")
    assert h["priority"] == "u=1, i" and h["accept-language"].startswith("fa-IR")
    await http.fetch(f"{http.SITE}/popular/", html=True)
    h = api.calls[-1].headers
    assert (
        h["accept"].startswith("text/html") and h["sec-fetch-mode"] == "navigate" and h["sec-fetch-dest"] == "document"
    )

import pytest

pytestmark = [pytest.mark.live, pytest.mark.anyio]


async def test_live_latest_and_article(client):
    r = (await client.call_tool("gf_latest_articles", {"category": "news", "limit": 3})).structured_content
    assert r["count"] == 3
    a = (
        await client.call_tool("gf_article", {"article": str(r["articles"][0]["id"]), "max_chars": 800})
    ).structured_content
    assert a["text"] and a["url"].startswith("https://gamefa.com/")


async def test_live_search_and_reviews(client):
    r = (await client.call_tool("gf_search_articles", {"query": "GTA 6", "limit": 3})).structured_content
    assert r["count"] > 0
    rv = (await client.call_tool("gf_reviews", {"limit": 3})).structured_content
    assert any(x.get("score") for x in rv["reviews"])


async def test_live_popular(client):
    r = (await client.call_tool("gf_popular", {"period": "week", "limit": 5})).structured_content
    assert len(r["articles"]) == 5 and r["articles"][0]["views"]


async def test_live_games_and_profile(client):
    r = (
        await client.call_tool("gf_games", {"query": "elden ring", "sort": "top_rated", "limit": 3})
    ).structured_content
    assert any("Elden Ring" in x["title"] for x in r["items"])
    g = (await client.call_tool("gf_game", {"slug": "onimusha-way-of-the-sword"})).structured_content
    assert g["gamefa_score"] == 10 and g["release"]["date"] == "2026-09-04"


async def test_live_filtered_sorted_games(client):
    r = (
        await client.call_tool("gf_games", {"platform": "playstation-5", "sort": "top_rated", "limit": 5})
    ).structured_content
    assert r["count"] == 5 and all("PlayStation 5" in x["platforms"] for x in r["items"])


async def test_live_upcoming_is_in_the_future(client):
    r = (await client.call_tool("gf_upcoming_games", {"limit": 5})).structured_content
    dates = [x["release"]["date"] for x in r["items"] if x.get("release")]
    assert dates == sorted(dates) and dates[0] >= "2026-10-01"


async def test_live_films(client):
    r = (await client.call_tool("gf_films", {"sort": "top_rated", "limit": 3})).structured_content
    f = (await client.call_tool("gf_film", {"slug": r["items"][0]["slug"]})).structured_content
    assert f["imdb"] and f["directors"]


async def test_live_terms_comments_related(client):
    t = (await client.call_tool("gf_terms", {"kind": "developer", "query": "capcom"})).structured_content
    assert t["terms"][0]["slug"] == "capcom"
    g = (await client.call_tool("gf_game", {"slug": "elden-ring"})).structured_content
    c = (await client.call_tool("gf_comments", {"post_id": g["post_id"], "limit": 3})).structured_content
    assert c["count"] > 0 and c["comments"][0]["text"]
    a = (await client.call_tool("gf_related", {"slug": "elden-ring"})).structured_content
    assert a["articles"] and a["articles"][0]["id"] > 0
    s = (await client.call_tool("gf_related", {"slug": "elden-ring", "what": "similar"})).structured_content
    assert s["similar"]


async def test_live_tag_year_and_developer_sort(client):
    r = (await client.call_tool("gf_latest_articles", {"tag": "elden-ring", "limit": 3})).structured_content
    assert r["count"] == 3
    b = (
        await client.call_tool("gf_latest_articles", {"category": "best-lists", "year": 2025, "limit": 2})
    ).structured_content
    assert b["articles"] and all(x["date"].startswith("2025") for x in b["articles"])
    d = (
        await client.call_tool("gf_games", {"developer": "capcom", "sort": "top_rated", "limit": 3})
    ).structured_content
    assert d["complete"] and d["items"][0]["gamefa_score"] == 10


async def test_live_month_series_and_person(client):
    u = (await client.call_tool("gf_upcoming_games", {"month": "2026-12"})).structured_content
    assert all(x["release"]["date"].startswith("2026-12") for x in u["items"])
    s = (await client.call_tool("gf_films", {"type": "series", "sort": "top_rated", "limit": 3})).structured_content
    assert s["items"][0]["imdb"] >= 9
    n = (await client.call_tool("gf_films", {"person": "christopher-nolan", "limit": 3})).structured_content
    assert n["items"]

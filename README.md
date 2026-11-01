<!-- mcp-name: io.github.sepehr071/gamefa-mcp -->

# gamefa-mcp: Gamefa (گیمفا) game and film news, reviews and release calendar MCP server for AI agents

**gamefa-mcp is an unofficial, read-only MCP server that gives AI agents Gamefa (گیمفا, gamefa.com), the large Persian site for video games, film and tech.**<br>
Its 13 tools search and read articles, list the editors' scored reviews, browse game and film profiles with Gamefa, user and IMDb scores,<br>
show the upcoming release calendar and rank the most read articles. No API key or account is needed. It works in Claude, Cursor, Copilot and any other MCP client.

[![PyPI](https://img.shields.io/pypi/v/gamefa-mcp?color=2563eb)](https://pypi.org/project/gamefa-mcp/)
[![License: MIT](https://img.shields.io/badge/license-MIT-16a34a)](https://github.com/sepehr071/gamefa-mcp/blob/main/LICENSE)

[For AI agents](#for-ai-agents) · [Quick start](#quick-start) · [Tools](#tools) · [فارسی](#فارسی)

---

## For AI agents

- **What:** unofficial MCP server (model context protocol) for gamefa.com: news and review search, full article text, review scores with pros and cons, game profiles (Gamefa score, user score, Metacritic, platforms, genres, publisher, release date), film and series profiles (IMDb, cast, director), upcoming game releases, most read articles.
- **Install:** `uvx gamefa-mcp` or `claude mcp add gamefa -- uvx gamefa-mcp`. Transport: stdio. Needs [uv](https://docs.astral.sh/uv/getting-started/installation/) (Python 3.10+).
- **Auth:** none. Optional `GAMEFA_MCP_PROXY` (HTTP proxy URL, or a comma-separated list); system proxy settings are ignored.
- **Access:** read-only. It cannot log in, comment or rate, so no confirmation is needed before calling any tool.
- **Tools:** 13, all prefixed `gf_`. Typical sequences: `gf_games(query)` -> `gf_game(slug)` -> `gf_article(review id)`; `gf_upcoming_games`; `gf_search_articles` -> `gf_article`.
- **Use when:** the user asks what Gamefa says about a game, its review score, the latest game or film news, what releases next, top rated games of a platform or genre, or what is trending.
- **Do not use when:** the user needs scores from other sites (Metacritic, OpenCritic) beyond what Gamefa lists, or prices and stores.
- **Output:** compact JSON. Article text is Persian; game and film titles are English. Scores are out of 10; release dates come as Jalali and ISO.

## Quick start

```bash
claude mcp add gamefa -- uvx gamefa-mcp
```

Or in any MCP client config: `{"command": "uvx", "args": ["gamefa-mcp"]}`.

## Tools

| Tool | What it does |
|---|---|
| `gf_search_articles` | Search news, reviews and features by keyword, optionally in one section |
| `gf_latest_articles` | Newest articles, optionally for news, reviews, trailers, pc, playstation, cinema... |
| `gf_article` | Full article text by id or slug; reviews include score, label, verdict, pros, cons |
| `gf_reviews` | Latest game reviews with the editors' score out of 10 |
| `gf_popular` | Most viewed articles of the week, month, season or year |
| `gf_games` | Game profiles with Gamefa and user scores; sort, search, filter by platform, genre, developer, publisher, release year |
| `gf_upcoming_games` | Release calendar: unreleased games, soonest first; by month, platform or genre |
| `gf_game` | One game profile: scores, Metacritic, release, platforms, genres, review link |
| `gf_films` | Film and series profiles with IMDb and user scores; filter by movie/series, genre, person, studio, country, language, year |
| `gf_film` | One film or series: cast, director, countries, runtime, scores |
| `gf_terms` | Look up the slug of a platform, genre, developer, publisher, film person or studio, or an article tag |
| `gf_comments` | Reader comments (with likes) under an article or a game/film profile |
| `gf_related` | Articles Gamefa links to a game/film, or similar games/films |

## FAQ

**Does it need an account?** No. **Is it official?** No, it reads the public pages and REST API of gamefa.com.
**Which network?** Both Iranian and foreign connections reach the site; set `GAMEFA_MCP_PROXY` if yours is blocked.

## فارسی

gamefa-mcp یک سرور MCP غیررسمی و فقط‌خواندنی برای سایت گیمفا (gamefa.com) است: جست‌وجوی اخبار و مقالات، متن کامل نقدها همراه با امتیاز، مشخصات و امتیاز بازی‌ها و فیلم‌ها، بازی‌های در راه و پربازدیدترین مطالب. نیازی به کلید API یا حساب کاربری نیست.

---

Made by Sepehr Radmard (سپهر رادمرد): [github.com/sepehr071](https://github.com/sepehr071) · [linkedin.com/in/sepehr-radmard](https://linkedin.com/in/sepehr-radmard). MIT license.

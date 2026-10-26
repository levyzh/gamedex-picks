# rawg calls, with the key read from env instead of shipped to a browser.
# this file is the entire reason this service exists as its own project.
#
# NOTE: this only covers MY rawg usage. the main gamedex app's browse/search/
# home/detail calls are still browser-side with VITE_RAWG_KEY. separate job.

import os

import httpx
from dotenv import load_dotenv
from fastapi import HTTPException, status

load_dotenv()

RAWG_KEY = os.getenv("RAWG_KEY")
RAWG_BASE = "https://api.rawg.io/api"

# rawg caps page_size at 40. asking for more just silently gives 40.
PAGE_SIZE = 40

TIMEOUT_SECONDS = 15.0

# ported verbatim from ADULT_TAGS in the frontend's src/api/rawg.ts. do NOT
# swap this for esrb 18+ or the nudity/sexual-content tags — those catch
# witcher/gta/cyberpunk. keeping the two apps in agreement matters more than
# this being clever.
ADULT_TAGS = {"nsfw", "hentai", "eroge"}


def _is_adult(raw: dict) -> bool:
    tags = raw.get("tags") or []
    return any(t.get("slug") in ADULT_TAGS for t in tags)


def _year(raw: dict) -> int | None:
    # rawg gives "2017-03-03" and sometimes nothing at all. I want the number
    # or None; the card decides what a missing year looks like. the frontend
    # puts an em dash in this slot instead, which makes its `year` a
    # number-or-string — not copying that wart over here.
    released = raw.get("released") or ""
    try:
        return int(released[:4])
    except ValueError:
        return None


def map_game(raw: dict) -> dict:
    # same shape as the frontend's mapGame, minus the fields I don't need
    # (dev/synopsis are detail-page only). keeping the names identical so a
    # candidate and a stored list entry can be compared without translating.
    #
    # year/genre exist only so the picks card has a line under the title —
    # genreSlugs are for the algorithm and look awful on screen
    # ("role-playing-games-rpg").
    #
    # note what is deliberately NOT here: `score`. the frontend derives it
    # (metacritic/10, falling back to rating*2) and re-implementing that
    # formula in python would put one rule in two languages with nothing to
    # stop them drifting. this file only passes through what rawg hands me;
    # anything derived stays on the side that already derives it.
    return {
        "id": raw.get("id"),
        "title": raw.get("name"),
        "cover": raw.get("background_image"),
        "year": _year(raw),
        "genre": [g.get("name") for g in (raw.get("genres") or []) if g.get("name")],
        "userRating": raw.get("rating") or 0,
        "ratingsCount": raw.get("ratings_count") or 0,
        "genreSlugs": [g.get("slug") for g in (raw.get("genres") or [])],
        "tagSlugs": [t.get("slug") for t in (raw.get("tags") or [])],
        "adult": _is_adult(raw),
    }


async def _get(path: str, params: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.get(f"{RAWG_BASE}{path}", params=params)
            response.raise_for_status()
            return response.json()

    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="RAWG took too long to respond.",
        )
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        if code == 401:
            # wrong/missing key. worth its own message because it's the one
            # failure that's purely a .env problem.
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="RAWG rejected the API key — check RAWG_KEY in .env.",
            )
        if code == 429:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="RAWG rate limit hit. Wait a bit.",
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"RAWG returned {code}.",
        )
    except httpx.RequestError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Couldn't reach RAWG.",
        )


async def fetch_candidates(
    genre_slugs: list[str],
    tag_slugs: list[str],
    page: int = 1,
) -> list[dict]:
    # rawg treats comma-separated slugs as OR, which is what I want — a wide
    # net of plausible games, then TF-IDF does the actual discriminating.
    params = {
        "key": RAWG_KEY,
        "page_size": PAGE_SIZE,
        "page": page,
        # -added = most added to people's libraries. same trick the frontend
        # uses to dodge rawg's "-rating" junk problem (1-vote 5.0 games).
        "ordering": "-added",
    }
    if genre_slugs:
        params["genres"] = ",".join(genre_slugs)
    if tag_slugs:
        params["tags"] = ",".join(tag_slugs)

    data = await _get("/games", params)

    # results is the actual list; the rest of the payload is paging metadata.
    return [map_game(raw) for raw in data.get("results", [])]


async def fetch_count(path: str) -> int:
    # every rawg list endpoint reports its total in `count`; one result is enough to read it.
    data = await _get(path, {"key": RAWG_KEY, "page_size": 1})
    return data.get("count", 0)
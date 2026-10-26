import asyncio
import time

from rawg_client import fetch_candidates

# the endpoint is public, so cache or every page view spends RAWG quota.
CACHE_SECONDS = 6 * 60 * 60

# rawg caps a page at 40, so two pages for enough covers to fill a big screen.
PAGES = 2

_cached: list[str] = []
_cached_at = 0.0


async def popular_covers() -> list[str]:
    global _cached, _cached_at

    if _cached and time.monotonic() - _cached_at < CACHE_SECONDS:
        return _cached

    pages = await asyncio.gather(*(fetch_candidates([], [], page=p) for p in range(1, PAGES + 1)))

    covers: list[str] = []
    for games in pages:
        for game in games:
            if game["cover"] and not game["adult"] and game["cover"] not in covers:
                covers.append(game["cover"])

    _cached = covers
    _cached_at = time.monotonic()
    return covers

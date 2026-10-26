import time

from rawg_client import fetch_candidates

# the endpoint is public, so cache or every page view spends RAWG quota.
CACHE_SECONDS = 6 * 60 * 60

_cached: list[str] = []
_cached_at = 0.0


async def popular_covers() -> list[str]:
    global _cached, _cached_at

    if _cached and time.monotonic() - _cached_at < CACHE_SECONDS:
        return _cached

    games = await fetch_candidates([], [])
    covers = [g["cover"] for g in games if g["cover"] and not g["adult"]]

    _cached = covers
    _cached_at = time.monotonic()
    return covers

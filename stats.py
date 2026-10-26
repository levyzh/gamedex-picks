import asyncio
import time

from rawg_client import fetch_count

# public endpoint, and these totals barely move, so a long cache is fine.
CACHE_SECONDS = 6 * 60 * 60

_cached: dict[str, int] = {}
_cached_at = 0.0


async def catalog_stats() -> dict[str, int]:
    global _cached, _cached_at

    if _cached and time.monotonic() - _cached_at < CACHE_SECONDS:
        return _cached

    games, genres, tags = await asyncio.gather(
        fetch_count("/games"),
        fetch_count("/genres"),
        fetch_count("/tags"),
    )

    _cached = {"games": games, "genres": genres, "tags": tags}
    _cached_at = time.monotonic()
    return _cached
import asyncio
import time

from rawg_client import fetch_cover

# public endpoint, same reason as covers.py: cache or every page view spends RAWG quota.
CACHE_SECONDS = 6 * 60 * 60

# must match the slugs in gamedex-picks-web's HowItWorks.tsx.
EXAMPLE_SLUGS = [
    "elden-ring",
    "hollow-knight",
    "dark-souls-iii",
    "destiny-2",
    "lies-of-p",
    "blasphemous",
    "nioh-2",
    "salt-and-sanctuary",
]

_cached: dict[str, str] = {}
_cached_at = 0.0


async def example_covers() -> dict[str, str]:
    global _cached, _cached_at

    if _cached and time.monotonic() - _cached_at < CACHE_SECONDS:
        return _cached

    # return_exceptions so one bad slug just loses its picture instead of failing the lot.
    results = await asyncio.gather(*(fetch_cover(s) for s in EXAMPLE_SLUGS), return_exceptions=True)
    covers = {slug: url for slug, url in zip(EXAMPLE_SLUGS, results) if isinstance(url, str) and url}

    if covers:
        _cached = covers
        _cached_at = time.monotonic()
    return covers
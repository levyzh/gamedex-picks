# talks to the java api. one job: hand me a user's list.
#
# GET /api/users/{userId}/list is PUBLIC — no token needed for this call, even
# though the caller had to be authed to reach my endpoint. that's fine for v1
# and it's why this file has no auth in it at all.
#
# returns ListEntryResponse[]:
#   { userId, gameId, status, score, hours, game, addedAt }
# `game` is the jsonb blob the frontend stored verbatim — genreSlugs/tagSlugs
# already live in there, so nothing needs re-deriving from rawg.

import os

import httpx
from dotenv import load_dotenv
from fastapi import HTTPException, status

load_dotenv()

GAMEDEX_API_BASE = os.getenv("GAMEDEX_API_BASE")

# java's cold-start first request is slow, and this is a localhost call for now
# anyway. generous but not infinite.
TIMEOUT_SECONDS = 10.0


async def fetch_list(user_id: str) -> list[dict]:
    url = f"{GAMEDEX_API_BASE}/api/users/{user_id}/list"

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.get(url)
            # raises on 4xx/5xx so I don't accidentally parse an error page
            response.raise_for_status()
            return response.json()

    except httpx.ConnectError:
        # nearly always: the java api just isn't running. 502 = "the thing
        # upstream of me is down", not my fault, distinct from a 500.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Can't reach the Gamedex API at {GAMEDEX_API_BASE}. Is it running?",
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="The Gamedex API took too long to respond.",
        )
    except httpx.HTTPStatusError as e:
        # it answered, just not with a 200. pass the code through so a 404 here
        # doesn't look like a 500 to me.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"The Gamedex API returned {e.response.status_code}.",
        )
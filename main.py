# fastapi app. right now: proves it's alive, proves who you are, reads my list,
# pulls rawg candidates. recommendations endpoint comes later.

import os

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Query

from auth import current_user_id
from gamedex_client import fetch_list
from rawg_client import fetch_candidates

# must run before the getenv calls below or they come back empty.
load_dotenv()

# three settings, so not worth a config.py yet. move them out if this grows.
RAWG_KEY = os.getenv("RAWG_KEY")
GAMEDEX_API_BASE = os.getenv("GAMEDEX_API_BASE")
SUPABASE_JWKS_URL = os.getenv("SUPABASE_JWKS_URL")

# title/description/version feed the auto-generated /docs page.
app = FastAPI(
    title="Gamedex Picks",
    description="Content-based game recommendations from your Gamedex list.",
    version="0.1.0",
)


@app.get("/health")
def health():
    # booleans only for the secrets — "the key is present" is useful to me,
    # printing the key over http hands it to anyone who hits this.
    # api base is just a url, safe to show, and I want to see which api I'm
    # pointed at.
    return {
        "status": "ok",
        "rawg_key_loaded": RAWG_KEY is not None,
        "gamedex_api_base": GAMEDEX_API_BASE,
        "jwks_url_loaded": SUPABASE_JWKS_URL is not None,
    }


# throwaway, just to prove auth.py works end to end. note there's zero auth
# code in here — that's the point of the Depends.
@app.get("/me")
def me(user_id: str = Depends(current_user_id)):
    return {"user_id": user_id}


# also throwaway — proves the two services talk. summary not raw entries,
# because dumping a full list of jsonb blobs into /docs is unreadable.
# `async def` because fetch_list awaits; a plain def would block the whole
# server for the duration of the call.
@app.get("/my-list")
async def my_list(user_id: str = Depends(current_user_id)):
    entries = await fetch_list(user_id)

    return {
        "count": len(entries),
        "sample": [
            {
                "title": e["game"].get("title"),
                "status": e["status"],
                "score": e["score"],
                # .get not [] — old entries predate these fields and I'd rather
                # see None than a KeyError.
                "genreSlugs": e["game"].get("genreSlugs"),
                "tagSlugs": e["game"].get("tagSlugs"),
            }
            for e in entries[:3]
        ],
    }


# throwaway too. authed on purpose — an open endpoint here would let anyone
# burn my rawg quota.
@app.get("/rawg-test")
async def rawg_test(
    genres: str = Query("action", description="comma-separated genre slugs"),
    tags: str = Query("", description="comma-separated tag slugs"),
    user_id: str = Depends(current_user_id),
):
    # split then filter — "a,,b".split(",") leaves an empty string that rawg
    # would choke on, and "" alone gives [""] not [].
    genre_list = [s.strip() for s in genres.split(",") if s.strip()]
    tag_list = [s.strip() for s in tags.split(",") if s.strip()]

    candidates = await fetch_candidates(genre_list, tag_list)

    return {
        "count": len(candidates),
        "adult_filtered_out": sum(1 for c in candidates if c["adult"]),
        "sample": candidates[:5],
    }
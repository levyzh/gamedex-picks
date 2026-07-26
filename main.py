# fastapi app. two endpoints now that the test ones are gone: is it up, and
# the actual recommendations.

import os

from dotenv import load_dotenv
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from auth import current_user_id
from gamedex_client import fetch_list
from models import HealthResponse, RecommendationsResponse
from recommender import recommend

# must run before the getenv calls below or they come back empty.
load_dotenv()

# four settings now, so still not worth a config.py. move them out if this grows.
RAWG_KEY = os.getenv("RAWG_KEY")
GAMEDEX_API_BASE = os.getenv("GAMEDEX_API_BASE")
SUPABASE_JWKS_URL = os.getenv("SUPABASE_JWKS_URL")

# which browser origins may call this. comma-separated so ONE env var covers
# local dev and the eventual picks.gamedex.com — deploying should be a config
# change, not a code change. falls back to the vite dev port so a fresh clone
# works without me remembering to set it.
CORS_ORIGINS = [
    o.strip()
    for o in (os.getenv("CORS_ORIGINS") or "http://localhost:5173").split(",")
    if o.strip()
]

# title/description/version feed the auto-generated /docs page.
app = FastAPI(
    title="Gamedex Picks",
    description="Content-based game recommendations from your Gamedex list.",
    version="1.0.0",
)

# without this the browser refuses to hand my response to the picks frontend —
# /docs never needed it because that page is served from this same origin.
#
# credentials OFF on purpose: the supabase session sits in localStorage and
# rides along in the Authorization header, not in a cookie. nothing here needs
# cookies, and leaving it off keeps me out of the "can't combine credentials
# with a wildcard origin" corner if I ever loosen the list.
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["Authorization"],
)


# unauthed on purpose — this is what a deploy platform pings to see if the
# process is alive, and it can't hold a token.
@app.get("/health", response_model=HealthResponse)
def health():
    # booleans only for the secrets — "the key is present" is useful to me,
    # printing the key over http hands it to anyone who hits this.
    # api base is just a url, safe to show, and I want to see which api I'm
    # pointed at. it's also the only debugging surface left now that /me and
    # /my-list are gone.
    #
    # cors origins listed in full: not a secret, and a cors failure in the
    # browser console never tells you what the server actually allows. this is
    # where I look first when the frontend says it's blocked.
    return {
        "status": "ok",
        "rawg_key_loaded": RAWG_KEY is not None,
        "gamedex_api_base": GAMEDEX_API_BASE,
        "jwks_url_loaded": SUPABASE_JWKS_URL is not None,
        "cors_origins": CORS_ORIGINS,
    }


# the whole service.
@app.get("/recommendations", response_model=RecommendationsResponse)
async def recommendations(user_id: str = Depends(current_user_id)):
    entries = await fetch_list(user_id)
    return await recommend(entries)
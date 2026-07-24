# fastapi app. two endpoints now that the test ones are gone: is it up, and
# the actual recommendations.

import os

from dotenv import load_dotenv
from fastapi import Depends, FastAPI

from auth import current_user_id
from gamedex_client import fetch_list
from models import HealthResponse, RecommendationsResponse
from recommender import recommend

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
    version="1.0.0",
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
    return {
        "status": "ok",
        "rawg_key_loaded": RAWG_KEY is not None,
        "gamedex_api_base": GAMEDEX_API_BASE,
        "jwks_url_loaded": SUPABASE_JWKS_URL is not None,
    }


# the whole service.
@app.get("/recommendations", response_model=RecommendationsResponse)
async def recommendations(user_id: str = Depends(current_user_id)):
    entries = await fetch_list(user_id)
    return await recommend(entries)
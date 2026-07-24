# fastapi app. right now: proves it's alive, proves who you are.
# recommendations endpoint comes later.

import os

from dotenv import load_dotenv
from fastapi import Depends, FastAPI

from auth import current_user_id

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
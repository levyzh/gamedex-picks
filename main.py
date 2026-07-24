# The FastAPI application for Gamedex Picks. For now it does exactly one thing:
# prove the service starts, reads its config, and serves a page. The
# recommendation endpoint comes later.

import os

from dotenv import load_dotenv
from fastapi import FastAPI

# Read the .env file and copy its contents into the process's environment
# variables. WHY a file instead of hardcoding: the RAWG key is a secret. Keeping
# it in a gitignored file means the code can be public while the key is not.
# This must run BEFORE any os.getenv call below, or those calls see nothing.
load_dotenv()

# Pull the three settings into plain module-level names. os.getenv returns None
# when a variable is missing, which is what the health check below reports on.
# (If this grows, it moves to its own config.py — one concern per file. Three
# lines doesn't earn a file yet.)
RAWG_KEY = os.getenv("RAWG_KEY")
GAMEDEX_API_BASE = os.getenv("GAMEDEX_API_BASE")
SUPABASE_JWKS_URL = os.getenv("SUPABASE_JWKS_URL")

# The application object. FastAPI reads the title/description/version to build
# the auto-generated documentation page at /docs — the page with the Authorize
# button we'll use in step 2 to test tokens by hand.
app = FastAPI(
    title="Gamedex Picks",
    description="Content-based game recommendations from your Gamedex list.",
    version="0.1.0",
)


# @app.get(...) registers the function below as the handler for GET /health.
# The decorator is the routing — there's no separate route table to maintain.
@app.get("/health")
def health():
    """Liveness check plus a safe report on whether config actually loaded."""
    # We return booleans, NOT the values. Saying "the RAWG key is present" is
    # useful for debugging; printing the key itself over HTTP would hand the
    # secret to anyone who hits this endpoint.
    return {
        "status": "ok",
        "rawg_key_loaded": RAWG_KEY is not None,
        "gamedex_api_base": GAMEDEX_API_BASE,
        "jwks_url_loaded": SUPABASE_JWKS_URL is not None,
    }
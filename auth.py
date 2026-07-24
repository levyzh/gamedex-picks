# supabase jwt check. deliberately the same jwks url + ES256 as the java api,
# so one token works against both services and there's one source of truth.

import os
from uuid import UUID

import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# also called in main.py — repeating it here so this file doesn't depend on
# import order.
load_dotenv()

SUPABASE_JWKS_URL = os.getenv("SUPABASE_JWKS_URL")

# hardcoded, not read from the token. the token's own alg field is attacker
# controlled — trust it and "alg: none" walks straight in.
ALGORITHMS = ["ES256"]

# every supabase access token has this. free extra check.
AUDIENCE = "authenticated"

# caches supabase's public keys in memory. without this every request makes an
# outbound https call before doing anything useful.
_jwk_client = jwt.PyJWKClient(SUPABASE_JWKS_URL)

# looks for "Authorization: Bearer <token>". real reason it's here: it puts the
# Authorize button on /docs, which is how I test tokens.
bearer_scheme = HTTPBearer()


def current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> str:
    # any endpoint with `Depends(current_user_id)` in its signature is now
    # authed — fastapi runs this first and the endpoint body never executes
    # without a valid token.
    token = credentials.credentials  # raw string, "Bearer " already stripped

    try:
        signing_key = _jwk_client.get_signing_key_from_jwt(token)

        # checks signature AND expiry.
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=ALGORITHMS,
            audience=AUDIENCE,
        )

    except jwt.ExpiredSignatureError:
        # separate branch so the message actually tells me what to do. supabase
        # tokens die after ~1hr, so this fires constantly during testing and
        # means nothing is wrong.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired — grab a fresh one from the browser.",
        )
    except Exception:
        # bad signature / malformed / wrong aud / jwks unreachable, all one
        # vague message. specific crypto errors just tell an attacker which
        # part of the forgery to fix.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
        )

    # "sub" = the supabase user id. same value java reads via jwt.getSubject(),
    # same value in list.user_id. this is the join between the two services.
    subject = payload.get("sub")
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is missing a subject claim.",
        )

    # parse and discard — only want it to blow up here if it's not a real uuid,
    # instead of two files later when it's already in a url.
    try:
        UUID(subject)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token subject is not a valid user id.",
        )

    return subject
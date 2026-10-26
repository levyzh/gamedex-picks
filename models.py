# response shapes. one concern: what my endpoints promise to return.
#
# these aren't validation for its own sake — fastapi reads them and puts the
# real output shape on /docs, instead of the useless bare "200 successful
# response" it shows now. also fails loudly here if I ever change a dict key
# in recommender.py and forget something downstream depends on it.

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    rawg_key_loaded: bool
    gamedex_api_base: str | None
    jwks_url_loaded: bool
    # full list, not a boolean — a blocked browser request never tells you what
    # the server actually allows, so this is the first thing I want to see.
    cors_origins: list[str]


class Recommendation(BaseModel):
    id: int
    title: str | None
    cover: str | None
    userRating: float
    genreSlugs: list[str]
    # the line under the title on the card. year is None when rawg has no
    # release date, genre can be empty — the card decides what to draw in
    # either case, I don't invent a placeholder here.
    year: int | None
    genre: list[str]
    # only ever true when the adult gate opened for this user. the frontend
    # uses it to blur the cover the same way the main app's GameCard does.
    adult: bool
    # None on the popular/cold-start path — nothing was ranked, so there's no
    # score to report. deliberately not faking it with 0.0.
    similarity: float | None


class RecommendationsResponse(BaseModel):
    # basis tells a future frontend which of the two paths ran, so it can say
    # "based on your list" vs "popular right now" honestly.
    basis: Literal["content", "popular"]

    # did the adult gate open? always false on the cold-start path, where I
    # filter unconditionally. lets the ui explain itself instead of silently
    # changing what it shows.
    adult_included: bool = False

    # everything below is path-dependent, hence the defaults. the query_*/
    # counts fields only exist on the content path; note only shows up when
    # something needs explaining.
    note: str | None = None
    query_genres: list[str] | None = None
    query_tags: list[str] | None = None
    from_entries: int | None = None
    candidates_considered: int | None = None

    results: list[Recommendation]


class CoversResponse(BaseModel):
    covers: list[str]


class StatsResponse(BaseModel):
    games: int
    genres: int
    tags: int
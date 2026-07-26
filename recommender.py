# the actual algorithm. content-based:
#   1. taste vector from my list (genre/tag slugs weighted by status + score)
#   2. pull rawg candidates matching my strongest slugs
#   3. drop what I already own + adult titles, unless my own list says I want them
#   4. rank by tf-idf + cosine against the taste vector
#   5. top 20
# if I ever swap this for embeddings, it goes behind recommend() and nothing
# upstream changes.

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from rawg_client import ADULT_TAGS, fetch_candidates

# how much each status says about my taste. dropped is negative on purpose.
STATUS_WEIGHTS = {
    "Completed": 1.0,
    "Playing": 0.8,
    "Plan to Play": 0.3,
    "On Hold": 0.2,
    "Dropped": -0.8,
}

# how hard the 1-10 score pushes the base weight around. 0.6 => a 10 counts
# 1.6x its base, a 1 counts 0.4x.
SCORE_INFLUENCE = 0.6

# rawg gives 30+ tags per game and the tail is noise (languages, storefronts,
# controller support). roughly popularity-ordered, so the head is the signal.
MAX_TAGS_PER_GAME = 20

# how many slugs go into the rawg query. more = wider net, slower, vaguer.
TOP_GENRES_FOR_QUERY = 3
TOP_TAGS_FOR_QUERY = 5

# below this many usable entries the taste vector is noise -> popular fallback.
MIN_ENTRIES = 3

# the adult gate. hidden by default, but hiding them from someone whose list is
# full of them is just as wrong an answer. BOTH conditions have to pass — a
# share on its own flips on at one game in a three-game list.
# guesses, same as the status weights. 15% is the one I'd move first.
ADULT_MIN_COUNT = 3
ADULT_MIN_SHARE = 0.15

# 40 per page. 2 pages = 80 candidates before filtering.
CANDIDATE_PAGES = 2

RESULT_COUNT = 20


def _tokens(game: dict) -> list[str]:
    # one "document" per game = its slugs, genres and tags pooled together.
    # tf-idf doesn't care which bucket a token came from.
    genres = game.get("genreSlugs") or []
    tags = (game.get("tagSlugs") or [])[:MAX_TAGS_PER_GAME]
    return [s for s in genres + tags if s]


def _is_adult_game(game: dict) -> bool:
    # for entries in MY list. derived from tagSlugs rather than trusting the
    # stored `adult` boolean: one definition (ADULT_TAGS) used on both sides,
    # and older entries may predate that field entirely.
    tags = game.get("tagSlugs") or []
    return any(slug in ADULT_TAGS for slug in tags)


def _weight(status: str, score) -> float | None:
    base = STATUS_WEIGHTS.get(status)
    if base is None:
        return None  # status I don't recognise, skip the entry entirely

    # score 0 / None = the "–" option in the ui = no opinion. base alone.
    if not score:
        return base

    # -1.0 at score 1, 0 at 5.5, +1.0 at score 10
    sentiment = (score - 5.5) / 4.5

    # SIGN HANDLING, don't "simplify" this. plain `base * (1 + k*sentiment)`
    # turns dropped-and-rated-2 into POSITIVE evidence, because two negatives
    # multiply. so instead: a good score strengthens a positive status, and
    # makes a dropped game LESS negative. the sign never flips either way.
    if base >= 0:
        return base * (1 + SCORE_INFLUENCE * sentiment)
    return base * (1 - SCORE_INFLUENCE * sentiment)


def _top_slugs(scores: dict[str, float], limit: int) -> list[str]:
    # positives only — feeding a slug I demonstrably dislike into the rawg
    # query would fetch candidates I'm about to rank down anyway.
    positive = [(slug, w) for slug, w in scores.items() if w > 0]
    positive.sort(key=lambda pair: pair[1], reverse=True)
    return [slug for slug, _ in positive[:limit]]


def build_profile(entries: list[dict]):
    """my list -> (docs, weights, owned ids, genre scores, tag scores, adult count)"""
    docs: list[list[str]] = []
    weights: list[float] = []
    owned: set[int] = set()
    genre_scores: dict[str, float] = {}
    tag_scores: dict[str, float] = {}
    adult_positive = 0

    for entry in entries:
        game = entry.get("game") or {}

        # owned is collected BEFORE any skip below — I don't want a game
        # recommended back to me just because its blob was too old to learn
        # from.
        game_id = entry.get("gameId")
        if game_id is not None:
            owned.add(game_id)

        tokens = _tokens(game)
        if not tokens:
            continue  # pre-slug entry, nothing to learn

        weight = _weight(entry.get("status"), entry.get("score"))
        if weight is None:
            continue

        docs.append(tokens)
        weights.append(weight)

        # positive weight ONLY. a hentai game I dropped and rated 2 is evidence
        # against, and counting it toward "show me more" is the same double
        # negative _weight() has the big warning about.
        if weight > 0 and _is_adult_game(game):
            adult_positive += 1

        # separate genre/tag tallies, only so I can build the rawg query —
        # that endpoint takes genres and tags as different params.
        for slug in game.get("genreSlugs") or []:
            genre_scores[slug] = genre_scores.get(slug, 0.0) + weight
        for slug in (game.get("tagSlugs") or [])[:MAX_TAGS_PER_GAME]:
            tag_scores[slug] = tag_scores.get(slug, 0.0) + weight

    return docs, weights, owned, genre_scores, tag_scores, adult_positive


def _result(game: dict, similarity) -> dict:
    return {
        "id": game["id"],
        "title": game["title"],
        "cover": game["cover"],
        "userRating": game["userRating"],
        "genreSlugs": game["genreSlugs"],
        # genre/year are display-only, the algorithm never touches them.
        "year": game["year"],
        "genre": game["genre"],
        # passed through so the ui can blur a cover. only ever true when the
        # gate below opened, so it should never surprise anyone.
        "adult": game["adult"],
        # rounded because 17 decimal places of cosine is not information
        "similarity": None if similarity is None else round(float(similarity), 4),
    }


async def recommend(entries: list[dict]) -> dict:
    (
        docs,
        weights,
        owned,
        genre_scores,
        tag_scores,
        adult_positive,
    ) = build_profile(entries)

    # --- cold start: empty/tiny list, or every entry too old to have slugs ---
    # adult stays filtered here NO MATTER WHAT. under MIN_ENTRIES I know
    # nothing about this person, and the popular list is not the place to guess.
    if len(docs) < MIN_ENTRIES:
        popular = await fetch_candidates([], [])
        picks = [c for c in popular if not c["adult"] and c["id"] not in owned]
        return {
            "basis": "popular",
            "note": f"Need at least {MIN_ENTRIES} rated games with genre data.",
            "adult_included": False,
            "results": [_result(c, None) for c in picks[:RESULT_COUNT]],
        }

    # --- the adult gate ---
    # measured against the positive-weight entries only, i.e. the same
    # population _top_slugs works from. enough of them AND a real share.
    positive_total = sum(1 for w in weights if w > 0)
    include_adult = (
        adult_positive >= ADULT_MIN_COUNT
        and positive_total > 0
        and adult_positive / positive_total >= ADULT_MIN_SHARE
    )

    top_genres = _top_slugs(genre_scores, TOP_GENRES_FOR_QUERY)
    top_tags = _top_slugs(tag_scores, TOP_TAGS_FOR_QUERY)

    # --- candidates ---
    # sequential on purpose. 2 pages is quick and asyncio.gather here would be
    # cleverness I'd have to re-read later. revisit if pages goes up.
    seen: set[int] = set()
    candidates: list[dict] = []
    for page in range(1, CANDIDATE_PAGES + 1):
        for game in await fetch_candidates(top_genres, top_tags, page=page):
            game_id = game.get("id")
            if game_id is None or game_id in seen:
                continue
            if game_id in owned:
                continue
            # rawg ORs the slugs together, so an adult game can arrive matching
            # `anime` alone. that's why this gate exists instead of just
            # trusting cosine to rank them down.
            if game["adult"] and not include_adult:
                continue
            if not _tokens(game):
                continue  # nothing to compare against
            seen.add(game_id)
            candidates.append(game)

    if not candidates:
        return {
            "basis": "content",
            "note": "No new candidates came back — try widening the query slugs.",
            "adult_included": include_adult,
            "results": [],
        }

    # --- rank ---
    candidate_docs = [_tokens(c) for c in candidates]

    # analyzer=identity because my documents are ALREADY lists of tokens.
    # sklearn's default string tokenizer would shred hyphenated slugs like
    # role-playing-games-rpg into separate words.
    vectorizer = TfidfVectorizer(analyzer=lambda tokens: tokens)

    # fit on mine + theirs together so both land in the same vocabulary and
    # share one set of idf weights. fitting separately makes the two sides
    # non-comparable and cosine returns garbage.
    matrix = vectorizer.fit_transform(docs + candidate_docs).toarray()
    mine = matrix[: len(docs)]
    theirs = matrix[len(docs) :]

    # ONE vector for my whole taste: each game's tf-idf row times its weight,
    # summed. negative weights subtract, which is exactly how dropped games
    # push recommendations away from what they contain.
    weight_column = np.array(weights).reshape(-1, 1)
    taste = (mine * weight_column).sum(axis=0).reshape(1, -1)

    # edge case: weights happen to cancel to exactly zero. cosine divides by
    # the norm, so this would be a divide-by-zero -> nan everywhere.
    # candidates here were already gated above, so nothing leaks on this path.
    if not taste.any():
        return {
            "basis": "popular",
            "note": "Taste vector cancelled out — not enough signal to rank.",
            "adult_included": include_adult,
            "results": [_result(c, None) for c in candidates[:RESULT_COUNT]],
        }

    similarities = cosine_similarity(taste, theirs)[0]

    ranked = sorted(
        zip(candidates, similarities),
        key=lambda pair: pair[1],
        reverse=True,
    )

    return {
        "basis": "content",
        "query_genres": top_genres,
        "query_tags": top_tags,
        "from_entries": len(docs),
        "candidates_considered": len(candidates),
        "adult_included": include_adult,
        "results": [_result(game, sim) for game, sim in ranked[:RESULT_COUNT]],
    }
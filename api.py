"""
Patch Notes API
=================
A thin FastAPI layer over patches.db (built by build_database.py). This
reuses diff_engine.py's logic exactly as-is -- the API's job is just to
fetch the right rows from the database and hand them to diff_champion(),
not to reimplement any of that logic.

Endpoints:
  GET /champions              -> list of every champion name
  GET /patches                -> list of every patch id, in chronological order
  GET /diff?champion=X&start=A&end=B  -> the net-diff for that champion/range

Run locally with:
  uvicorn api:app --reload
Then visit http://127.0.0.1:8000/docs for an interactive test page.

Requires: pip install fastapi uvicorn
"""

import os
import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from diff_engine import diff_champion, patch_sort_key

DB_PATH = Path("patches.db")

# Rate limiting: identifies callers by IP address and caps how often they
# can hit each endpoint. Not needed while this only runs on your own
# machine, but essential once it's public -- without this, one script
# (accidental or malicious) can hammer the API as fast as it wants,
# which on a free/cheap hosting tier can burn through your usage quota
# or slow the site down for everyone else.
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="LoL Patch Notes API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Allows a frontend running on a different port/domain to actually call
# this API from the browser. Reads from an env var so you can lock this
# down to your real deployed frontend URL once you know it, without
# editing code -- e.g. set ALLOWED_ORIGIN=https://your-app.vercel.app
# in Render's dashboard. Defaults to "*" (wide open) for local dev,
# which is a reasonable choice here specifically because this API has
# no auth, no cookies, and no sensitive per-user data -- there's nothing
# for a malicious site to steal by calling it cross-origin.
allowed_origin = os.environ.get("ALLOWED_ORIGIN", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[allowed_origin],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # lets us access columns by name
    return conn


@app.get("/champions")
@limiter.limit("60/minute")
def list_champions(request: Request) -> list[str]:
    conn = get_connection()
    rows = conn.execute("SELECT DISTINCT champion FROM changes ORDER BY champion").fetchall()
    conn.close()
    return [r["champion"] for r in rows]


@app.get("/patches")
@limiter.limit("60/minute")
def list_patches(request: Request) -> list[str]:
    conn = get_connection()
    rows = conn.execute("SELECT DISTINCT patch FROM changes").fetchall()
    conn.close()
    patches = [r["patch"] for r in rows]
    return sorted(patches, key=patch_sort_key)


@app.get("/diff")
@limiter.limit("30/minute")
def get_diff(request: Request, champion: str, start: str, end: str) -> dict:
    # Basic sanity checks -- not a security measure (the SQL query below
    # is already parameterized, so injection isn't possible regardless),
    # just makes sure obviously-bad input fails with a clean 400 instead
    # of an ugly 500 or a confusing empty result.
    for name, value in [("champion", champion), ("start", start), ("end", end)]:
        if not value or not value.strip():
            raise HTTPException(status_code=400, detail=f"'{name}' cannot be empty")
        if len(value) > 50:
            raise HTTPException(status_code=400, detail=f"'{name}' is unexpectedly long")

    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM changes WHERE champion = ?", (champion,)
    ).fetchall()
    conn.close()

    if not rows:
        raise HTTPException(status_code=404, detail=f"No data found for champion '{champion}'")

    records = [dict(r) for r in rows]
    return diff_champion(records, champion, start, end)


@app.get("/")
def root() -> dict:
    return {
        "message": "LoL Patch Notes API",
        "endpoints": ["/champions", "/patches", "/diff?champion=X&start=A&end=B"],
        "docs": "/docs",
    }

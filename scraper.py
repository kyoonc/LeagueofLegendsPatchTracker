"""
League of Legends Patch Notes Scraper (full history)
=======================================================
Downloads the raw HTML for every patch from 9.1 (Jan 2019) through the
current patch, from the official leagueoflegends.com site.

Instead of guessing URLs from a simple (major, minor) number range, this
builds an explicit list of every patch ID that actually exists, based on
the known season structure -- this is what lets it handle the irregular
patches along the way (skipped patch 13.2, the 2025 season's "S1.1"
style IDs before it switched to zero-padded months, etc.) without
tripping over them.

NOTE: the PATCH_26_COUNT constant below will need bumping every couple
of weeks as new 26.x patches release. Everything else here is fixed
history and won't change.

Requires: pip install requests
"""

import json
import time
from pathlib import Path

import requests

# --- Configuration -----------------------------------------------------

OUTPUT_DIR = Path("patch_notes_raw")
OUTPUT_DIR.mkdir(exist_ok=True)

BASE_URL = "https://www.leagueoflegends.com/en-us/news/game-updates/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PatchNotesScraper/0.1; personal project)"
}

REQUEST_DELAY = 1.5  # seconds between requests -- slow and polite beats fast and banned

# How many patches have released so far in the 2026 season, as of when
# this was last touched by hand. You should no longer need to bump this
# yourself within a season -- see PROBE_AHEAD below -- only when Riot
# starts an entirely new numbering era (e.g. season 27), which isn't
# something we can predict or automate given how irregular past season
# transitions have been (see generate_patch_ids for the full history).
PATCH_26_COUNT = 16

# The scraper also probes this many patch numbers beyond PATCH_26_COUNT
# on every run. This is what makes it self-updating within a season:
# once a new patch (e.g. 26.17) actually exists, the probe finds and
# downloads it automatically. Probes for patches that don't exist yet
# just come back "missing", which is harmless -- a few wasted requests,
# nothing more.
PROBE_AHEAD = 6

# Known cases where a patch's real URL doesn't match its sequential
# position -- usually because a hotfix got promoted to its own full
# patch with a letter suffix (e.g. "16b") instead of bumping the next
# patch to the next whole number. We keep OUR patch id sequential (so
# "10.17" sorts and displays predictably downstream) but fetch from the
# real slug Riot actually used.
#
# NOTE: this list is almost certainly incomplete -- we only know about
# entries here because someone ran the scraper and reported a "missing"
# patch that turned out to exist under an unexpected slug. Add more as
# they're discovered.
URL_SLUG_OVERRIDES = {
    "10.17": "10-16b",
}


# --- Building the list of every patch that exists -------------------------

def generate_patch_ids() -> list[str]:
    """
    Return every patch ID from 9.1 through the current patch, in order,
    based on the known season structure. Patches that never existed
    (like 13.2, which was folded into a hotfix instead of its own patch)
    are simply not included.
    """
    ids = []

    ids += [f"9.{m}" for m in range(1, 23)]     # Season 2019: 9.1-9.22
    ids += [f"10.{m}" for m in range(1, 26)]    # Season 2020: 10.1-10.25
    ids += [f"11.{m}" for m in range(1, 25)]    # Season 2021: 11.1-11.24
    ids += [f"12.{m}" for m in range(1, 24)]    # Season 2022: 12.1-12.23

    ids += ["13.1"]                             # Season 2023: 13.1, then 13.2 was skipped
    ids += [f"13.{m}" for m in range(3, 25)]    #   ... 13.3-13.24

    ids += [f"14.{m}" for m in range(1, 25)]    # Season 2024: 14.1-14.24

    ids += [f"25.S1.{n}" for n in range(1, 4)]  # Season 2025: S1.1-S1.3, then...
    ids += [f"25.{m:02d}" for m in range(4, 25)]  # ...zero-padded 25.04-25.24

    ids += [f"26.{m}" for m in range(1, PATCH_26_COUNT + 1)]  # Season 2026: 26.1-current
    ids += [f"26.{m}" for m in range(PATCH_26_COUNT + 1, PATCH_26_COUNT + 1 + PROBE_AHEAD)]  # probe for new patches

    return ids


def build_urls(patch_id: str) -> list[str]:
    """
    Build the candidate URLs for a patch ID. Riot has used a couple of
    different URL naming patterns over the years (with/without a
    "league-of-legends-" prefix), so we try both. A few patches also
    need a manual slug override (see URL_SLUG_OVERRIDES) or a special
    case (the 2025 "S1" patches use the full year in the URL, unlike
    every other patch which uses the two-digit season number).
    """
    if patch_id in URL_SLUG_OVERRIDES:
        slug = URL_SLUG_OVERRIDES[patch_id]
    elif patch_id.startswith("25.S1."):
        slug = "2025-" + patch_id.split(".", 1)[1].replace(".", "-").lower()
    else:
        slug = patch_id.replace(".", "-").lower()

    return [
        BASE_URL + f"patch-{slug}-notes/",
        BASE_URL + f"league-of-legends-patch-{slug}-notes/",
        BASE_URL + f"lol-patch-{slug}-notes/",
    ]


# --- Core functions ------------------------------------------------------

def fetch_patch_page(patch_id: str) -> str | None:
    """Try each candidate URL for a patch until one works. Returns None if none do."""
    for url in build_urls(patch_id):
        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
        except requests.RequestException as error:
            print(f"  ERROR {patch_id}: could not reach {url} ({error})")
            time.sleep(REQUEST_DELAY)
            continue

        if response.status_code == 200:
            print(f"  OK    {patch_id}  <- {url}")
            time.sleep(REQUEST_DELAY)
            return response.text

        if response.status_code == 404:
            continue  # try the next URL pattern, no need to wait

        print(f"  ERROR {patch_id}: HTTP {response.status_code} at {url}")
        time.sleep(REQUEST_DELAY)

    print(f"  MISS  {patch_id}: no URL pattern worked")
    return None


def save_patch_html(patch_id: str, html: str) -> None:
    filepath = OUTPUT_DIR / f"{patch_id}.html"
    filepath.write_text(html, encoding="utf-8")


def scrape_all() -> dict:
    """Walk the full patch-id list, downloading anything not already saved."""
    patch_ids = generate_patch_ids()
    print(f"Built a list of {len(patch_ids)} patches to check (9.1 through 26.{PATCH_26_COUNT}).")

    results = {}
    for patch_id in patch_ids:
        existing_file = OUTPUT_DIR / f"{patch_id}.html"
        if existing_file.exists():
            print(f"  SKIP  {patch_id}: already downloaded")
            results[patch_id] = "cached"
            continue

        html = fetch_patch_page(patch_id)
        if html:
            save_patch_html(patch_id, html)
            results[patch_id] = "downloaded"
        else:
            results[patch_id] = "missing"

    downloaded = sum(1 for v in results.values() if v == "downloaded")
    cached = sum(1 for v in results.values() if v == "cached")
    missing = sum(1 for v in results.values() if v == "missing")
    print(f"\nDone. Downloaded: {downloaded}, already cached: {cached}, missing: {missing}")

    manifest_path = OUTPUT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(results, indent=2))
    print(f"Manifest saved to {manifest_path}")

    return results


if __name__ == "__main__":
    scrape_all()

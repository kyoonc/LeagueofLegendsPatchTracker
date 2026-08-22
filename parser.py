"""
League of Legends Patch Notes Parser (unified: legacy + modern)
===================================================================
Reads the raw HTML files saved by scraper.py and extracts every champion
stat change into the normalized data model:

  - value_change:   a stat went from one value to another
  - new_effect:     a brand new named effect was added
  - removed_effect: a named effect was removed
  - note:           a plain description with no before/after value

Two HTML structures exist across League's patch-note history:

  LEGACY (~2019 - late 2022): each stat change is its own
    <div class="attribute-change"> containing <span> elements for the
    label, old value, arrow, and new value.

  MODERN (~2023 - present): each ability's changes are grouped into one
    <ul>, with each stat change as an <li> like:
    <li><strong>Stat Name</strong>: OLD ⇒ <strong>NEW</strong></li>

Both eras share the same outer scaffolding (<h3 class="change-title">
for the champion name, <h4 class="change-detail-title"> for the ability
name), so this parser walks that shared structure once and dispatches to
the right extraction logic depending on which kind of sibling it finds.

SCOPE FOR NOW: champions only (items/runes/systems are skipped). A
champion block is identified by its <h3> containing a link to a
"/champions/" URL.

Requires: pip install beautifulsoup4
"""

import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

# --- Configuration -----------------------------------------------------

RAW_HTML_DIR = Path("patch_notes_raw")
OUTPUT_PATH = Path("parsed_changes.json")

MARKER_CLASSES = ("new", "removed", "updated")


def strip_marker_span(tag) -> str | None:
    """
    Find and remove a leading marker <span> (new/removed/updated) from a
    tag, if present, returning its class name. "updated" is used to flag
    reworked abilities/champions and needs stripping just like the other
    two -- it just doesn't change what TYPE of record this is.
    """
    for cls in MARKER_CLASSES:
        span = tag.find("span", class_=cls)
        if span:
            span.extract()
            return cls
    return None

# Champion page URLs have used at least three different shapes over the
# years:
#   http://gameinfo.na.leagueoflegends.com/en/game-info/champions/kalista/
#   https://www.leagueoflegends.com/en-us/champions/azir/
#   http://www.leagueoflegends.com/en-us/brand/          (no "/champions/" at all!)
# The third shape is indistinguishable from a generic link by substring
# alone, so we match it structurally: leagueoflegends.com/en-us/ followed
# by exactly one path segment and nothing else (items and runes always
# have an extra path segment like "/items/" or "/how-to-play/").
BARE_SLUG_HREF_RE = re.compile(
    r"^https?://(www\.)?leagueoflegends\.com/en-us/[a-z0-9\-']+/?$", re.IGNORECASE
)

# Some items/runes fall back to a generic placeholder link instead of a
# real product page -- these match the bare-slug shape above but are NOT
# champions, so they need explicit exclusion.
NON_CHAMPION_SLUGS = {"how-to-play", "champions", "items", "runes", "news"}


def is_champion_href(href: str) -> bool:
    if "/champions/" in href:
        return True
    match = BARE_SLUG_HREF_RE.match(href)
    if match:
        slug = href.rstrip("/").rsplit("/", 1)[-1].lower()
        return slug not in NON_CHAMPION_SLUGS
    return False


# --- Legacy-era extraction (one <div class="attribute-change"> per stat) --

def parse_attribute_change_legacy(div, champion: str, ability: str, patch_id: str) -> dict | None:
    attribute_span = div.find("span", class_="attribute")
    if attribute_span is None:
        return None

    marker = strip_marker_span(attribute_span)
    if marker == "updated":
        marker = None  # strip it, but this is still a normal value_change/note, not a distinct type
    stat_label = attribute_span.get_text(strip=True)

    before_span = div.find("span", class_="attribute-before")
    after_span = div.find("span", class_="attribute-after")
    removed_span = div.find("span", class_="attribute-removed")

    if marker == "new":
        return {
            "champion": champion, "ability": ability, "patch": patch_id,
            "effect_name": stat_label,
            "description": after_span.get_text(strip=True) if after_span else "",
            "change_type": "new_effect",
        }
    if marker == "removed":
        return {
            "champion": champion, "ability": ability, "patch": patch_id,
            "effect_name": stat_label,
            "description": removed_span.get_text(strip=True) if removed_span else "",
            "change_type": "removed_effect",
        }
    if before_span and after_span:
        return {
            "champion": champion, "ability": ability, "patch": patch_id,
            "stat": stat_label,
            "old_value": before_span.get_text(strip=True),
            "new_value": after_span.get_text(strip=True),
            "change_type": "value_change",
        }
    if after_span:
        return {
            "champion": champion, "ability": ability, "patch": patch_id,
            "effect_name": stat_label,
            "description": after_span.get_text(strip=True),
            "change_type": "note",
        }
    return None


# --- Modern-era extraction (one <ul> per ability, one <li> per stat) ------

def parse_li_modern(li, champion: str, ability: str, patch_id: str) -> dict | None:
    # A "new"/"removed" marker, if present, is a <span> that is the very
    # first tag inside the <li> (its own styling has changed over the
    # years -- sometimes class="new"/"removed", sometimes an inline
    # background-color style -- so we check its TEXT, not its class).
    marker = None
    for child in list(li.children):
        if getattr(child, "name", None):
            if child.name == "span":
                marker_text = child.get_text(strip=True).upper()
                if marker_text == "NEW":
                    marker = "new"
                    child.extract()
                elif marker_text == "REMOVED":
                    marker = "removed"
                    child.extract()
                elif marker_text == "UPDATED":
                    child.extract()  # strip only -- stays a normal value_change/note
            break  # only the first tag child counts as a marker

    strong = li.find("strong")
    if strong is None:
        return None
    label = strong.get_text(strip=True)

    full_text = li.get_text(separator="", strip=True)
    remainder = full_text[len(label):].strip() if full_text.startswith(label) else full_text
    if remainder.startswith(":"):
        remainder = remainder[1:].strip()

    if marker == "new":
        return {
            "champion": champion, "ability": ability, "patch": patch_id,
            "effect_name": label, "description": remainder, "change_type": "new_effect",
        }
    if marker == "removed":
        return {
            "champion": champion, "ability": ability, "patch": patch_id,
            "effect_name": label, "description": remainder, "change_type": "removed_effect",
        }
    if "⇒" in remainder:
        old_value, new_value = remainder.split("⇒", 1)
        return {
            "champion": champion, "ability": ability, "patch": patch_id,
            "stat": label,
            "old_value": old_value.strip(),
            "new_value": new_value.strip(),
            "change_type": "value_change",
        }
    return {
        "champion": champion, "ability": ability, "patch": patch_id,
        "effect_name": label, "description": remainder, "change_type": "note",
    }


# --- Shared traversal (works for both eras) -------------------------------

def load_container(filepath: Path):
    html = filepath.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    return soup.find(id="patch-notes-container")


def parse_champion_blocks(container, patch_id: str) -> list[dict]:
    """
    Find every champion block (legacy or modern) and extract all of its
    stat changes. A champion block is identified by its <h3> containing
    a link to a "/champions/" page -- this is true in both eras.
    """
    records = []

    for h3 in container.find_all("h3", class_="change-title"):
        link = h3.find("a", href=True)
        if link is None or not is_champion_href(link["href"]):
            continue  # item or rune block, not a champion -- skip for v1

        strip_marker_span(link)  # remove a leading "updated"/"new" marker if present
        champion_name = h3.get_text(strip=True)
        current_ability = "Base Stats"

        for sibling in h3.find_next_siblings():
            if sibling.name == "h3":
                break  # reached the next champion/item/rune block

            if sibling.name == "h4":
                current_ability = sibling.get_text(strip=True)
                continue

            if sibling.name == "div" and "attribute-change" in (sibling.get("class") or []):
                record = parse_attribute_change_legacy(sibling, champion_name, current_ability, patch_id)
                if record:
                    records.append(record)

            if sibling.name == "ul":
                for li in sibling.find_all("li", recursive=False):
                    record = parse_li_modern(li, champion_name, current_ability, patch_id)
                    if record:
                        records.append(record)

            if sibling.name == "li":
                # Some patches have bare <li> elements with no wrapping <ul>
                # at all (a real quirk in Riot's own CMS content) -- handle
                # them the same way as ul-wrapped ones.
                record = parse_li_modern(sibling, champion_name, current_ability, patch_id)
                if record:
                    records.append(record)

    return records


def parse_patch_file(filepath: Path) -> list[dict]:
    patch_id = filepath.stem
    container = load_container(filepath)
    if container is None:
        print(f"  WARNING: could not find patch-notes-container in {filepath.name}, skipping")
        return []
    records = parse_champion_blocks(container, patch_id)
    print(f"  {filepath.name}: extracted {len(records)} records")
    return records


def _patch_sort_key(patch_id: str):
    """Lightweight standalone version of the sort key used in diff_engine.py."""
    key = []
    for part in patch_id.split("."):
        key.append((0, int(part)) if part.isdigit() else (1, part))
    return key


def normalize_champion_names(records: list[dict]) -> list[dict]:
    """
    Champion names have the same apostrophe/casing drift problem as
    ability and stat labels (e.g. "Bel'Veth" vs "Bel'Veth", "Cho'gath"
    vs "Cho'Gath") -- except this one can't be fixed downstream at query
    time the way diff_engine.py fixes abilities/stats, because a direct
    "list every champion" query needs the STORED value to already be
    consistent. So we normalize once here: group records by a
    normalized key, then rewrite every record's champion field to use
    whichever spelling appeared in the most recent patch (the current,
    presumably-correct spelling).
    """
    def norm_key(name: str) -> str:
        name = name.replace("\u2019", "'").replace("\u2018", "'").lower()
        name = name.replace(" and ", " & ")  # "Nunu and Willump" == "Nunu & Willump"
        return name

    canonical: dict[str, tuple] = {}
    for r in records:
        key = norm_key(r["champion"])
        pk = _patch_sort_key(r["patch"])
        if key not in canonical or pk > canonical[key][0]:
            canonical[key] = (pk, r["champion"])

    for r in records:
        r["champion"] = canonical[norm_key(r["champion"])][1]

    return records


def parse_all() -> list[dict]:
    html_files = sorted(RAW_HTML_DIR.glob("*.html"))
    print(f"Found {len(html_files)} patch HTML files in {RAW_HTML_DIR}/")

    all_records = []
    for filepath in html_files:
        all_records.extend(parse_patch_file(filepath))
    return all_records


if __name__ == "__main__":
    records = parse_all()
    records = normalize_champion_names(records)

    OUTPUT_PATH.write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(f"\nSaved {len(records)} total records to {OUTPUT_PATH}")

    print("\nSample records:")
    for record in records[:5]:
        print(f"  {record}")

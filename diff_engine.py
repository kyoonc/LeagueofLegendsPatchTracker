"""
Patch Diff Engine
==================
Given the normalized records from parser.py (parsed_changes.json), this
collapses a range of patches down to the NET change for one champion --
answering "what's actually different now vs. before, regardless of how
many times a stat bounced around in between."

No extra dependencies beyond the standard library.
"""

import json
import re
from collections import defaultdict
from pathlib import Path

INPUT_PATH = Path("parsed_changes.json")


# --- Text normalization ---------------------------------------------------

def display_text(text: str) -> str:
    """Clean up text for display: consistent straight apostrophes everywhere."""
    return text.replace("\u2019", "'").replace("\u2018", "'")


def normalize_key(text: str) -> str:
    """
    Turn ability/stat text into a normalized grouping key. This exists
    because the same stat or ability is written differently across eras:
      - legacy patches use ALL CAPS labels ("ATTACK DAMAGE"), modern
        patches use Title Case ("Attack Damage")
      - legacy patches use a straight apostrophe ("Ranger's Focus"),
        modern patches use a typographic curly one ("Ranger's Focus")
    Without normalizing, the same real-world stat gets bucketed as two
    separate "different" things depending on which era touched it last,
    which silently breaks net-diffing for any champion with history
    spanning both eras -- exactly the champions a returning player is
    most likely to check on.
    """
    text = display_text(text).lower().strip()
    text = text.lstrip("-").strip()       # strip a stray leading bullet-dash artifact
    text = re.sub(r"\s*-\s*", "-", text)  # "W- Vision" and "W - Vision" -> same
    text = re.sub(r"\s*/\s*", "/", text)  # "A/B" and "A / B" -> same
    text = re.sub(r"\s+", " ", text)      # collapse any remaining double spaces
    return text


# --- Core functions ------------------------------------------------------

def patch_sort_key(patch_id: str):
    """
    Turn a patch id like '9.1' or '9.10' into a sortable key. Numeric
    pieces sort numerically (so '9.2' < '9.10', not the other way around
    like plain string sorting would give you). Non-numeric pieces (like
    the 'b' in a hypothetical '13.1b') fall back to string comparison.
    """
    key = []
    for part in patch_id.split("."):
        if part.isdigit():
            key.append((0, int(part)))
        else:
            key.append((1, part))
    return key


def load_records() -> list[dict]:
    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def filter_range(records: list[dict], champion: str, patch_start: str, patch_end: str) -> list[dict]:
    """Keep only records for this champion within [patch_start, patch_end] inclusive."""
    start_key = patch_sort_key(patch_start)
    end_key = patch_sort_key(patch_end)
    result = []
    for r in records:
        if r["champion"] != champion:
            continue
        p_key = patch_sort_key(r["patch"])
        if start_key <= p_key <= end_key:
            result.append(r)
    return result


def sort_by_patch(records: list[dict]) -> list[dict]:
    return sorted(records, key=lambda r: patch_sort_key(r["patch"]))


def diff_champion(records: list[dict], champion: str, patch_start: str, patch_end: str) -> dict:
    """
    Build the full net-diff for one champion across a patch range.
    This is the heart of the whole project.
    """
    scoped = filter_range(records, champion, patch_start, patch_end)

    value_changes = sort_by_patch([r for r in scoped if r["change_type"] == "value_change"])
    new_effects = sort_by_patch([r for r in scoped if r["change_type"] == "new_effect"])
    removed_effects = sort_by_patch([r for r in scoped if r["change_type"] == "removed_effect"])
    notes = sort_by_patch([r for r in scoped if r["change_type"] == "note"])

    # --- collapse value changes by normalized (ability, stat): first old_value, last new_value ---
    groups = defaultdict(list)
    for r in value_changes:
        key = (normalize_key(r["ability"]), normalize_key(r["stat"]))
        groups[key].append(r)

    net_changes = []
    fluctuated_no_net_change = []
    for group in groups.values():
        first, last = group[0], group[-1]
        entry = {
            # Display the most RECENT wording/casing -- that's the
            # current terminology, which is what a returning player
            # actually sees in-game and in the latest patch notes.
            "ability": display_text(last["ability"]),
            "stat": display_text(last["stat"]),
            "old_value": first["old_value"],
            "new_value": last["new_value"],
            "patches_touched": [r["patch"] for r in group],
        }
        if first["old_value"] == last["new_value"]:
            fluctuated_no_net_change.append(entry)
        else:
            net_changes.append(entry)

    # --- pair up new/removed effects by normalized (ability, effect_name) ---
    effect_groups = defaultdict(lambda: {"new": [], "removed": []})
    for r in new_effects:
        key = (normalize_key(r["ability"]), normalize_key(r["effect_name"]))
        effect_groups[key]["new"].append(r)
    for r in removed_effects:
        key = (normalize_key(r["ability"]), normalize_key(r["effect_name"]))
        effect_groups[key]["removed"].append(r)

    surviving_new_effects, surviving_removed_effects, netted_out_effects = [], [], []
    for pair in effect_groups.values():
        if pair["new"] and pair["removed"]:
            netted_out_effects.append({
                "ability": pair["removed"][-1]["ability"],
                "effect_name": pair["removed"][-1]["effect_name"],
                "note": "added then removed within this range -- no net change",
            })
        elif pair["new"]:
            surviving_new_effects.extend(pair["new"])
        elif pair["removed"]:
            surviving_removed_effects.extend(pair["removed"])

    return {
        "champion": champion,
        "patch_range": [patch_start, patch_end],
        "net_changes": net_changes,
        "fluctuated_no_net_change": fluctuated_no_net_change,
        "new_effects": surviving_new_effects,
        "removed_effects": surviving_removed_effects,
        "netted_out_effects": netted_out_effects,
        "notes": notes,
    }


# --- Display helpers -----------------------------------------------------

def print_diff(diff: dict, show_fluctuations: bool = False) -> None:
    champ = diff["champion"]
    start, end = diff["patch_range"]
    print(f"\n=== {champ}: {start} -> {end} ===\n")

    if diff["net_changes"]:
        print("Net stat changes:")
        for c in diff["net_changes"]:
            touched = ", ".join(c["patches_touched"])
            print(f"  [{c['ability']}] {c['stat']}: {c['old_value']} -> {c['new_value']}  (touched in {touched})")
    else:
        print("No net stat changes.")

    if diff["new_effects"]:
        print("\nNew effects:")
        for e in diff["new_effects"]:
            print(f"  [{e['ability']}] {e['effect_name']}: {e['description']}")

    if diff["removed_effects"]:
        print("\nRemoved effects:")
        for e in diff["removed_effects"]:
            print(f"  [{e['ability']}] {e['effect_name']}: {e['description']}")

    if diff["notes"]:
        print("\nOther notes:")
        for n in diff["notes"]:
            print(f"  [{n['ability']}] {n['effect_name']}: {n['description']}")

    hidden_count = len(diff["fluctuated_no_net_change"]) + len(diff["netted_out_effects"])
    if hidden_count and not show_fluctuations:
        print(f"\n({hidden_count} stat(s)/effect(s) changed and reverted within this range -- hidden.)")

    if show_fluctuations:
        if diff["fluctuated_no_net_change"]:
            print("\nFluctuated (no net change):")
            for c in diff["fluctuated_no_net_change"]:
                touched = ", ".join(c["patches_touched"])
                print(f"  [{c['ability']}] {c['stat']}: touched in {touched}, ended back at {c['old_value']}")
        if diff["netted_out_effects"]:
            print("\nNetted-out effects (added then removed):")
            for e in diff["netted_out_effects"]:
                print(f"  [{e['ability']}] {e['effect_name']}")


if __name__ == "__main__":
    records = load_records()

    # Example: what changed for Ornn between patch 9.1 and 9.3, fluctuations included?
    diff = diff_champion(records, "Ornn", "9.1", "9.3")
    print_diff(diff, show_fluctuations=True)

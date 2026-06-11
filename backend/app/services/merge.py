"""Merge parsed roster units with the Wahapedia warscroll DB.

After Gemini turns the roster text into structured JSON, every unit name
is matched against the faction's scraped warscrolls so the simulator has
real Move/Health/Save/weapon data attached to each roster entry.
"""

from __future__ import annotations

import difflib
import re

from ..factions import resolve_faction_slug
from ..models.roster import Roster
from ..scraper.wahapedia import fetch_faction_warscrolls


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", name.lower()).strip()


def find_warscroll(name: str, warscrolls: list[dict]) -> dict | None:
    """Match a roster unit name to a warscroll, tolerating builder-app
    naming differences (punctuation, singular/plural, partial names)."""
    target = _norm(name)
    by_name = {_norm(w["name"]): w for w in warscrolls}
    if target in by_name:
        return by_name[target]
    # singular/plural tolerance
    for cand, w in by_name.items():
        if cand.rstrip("s") == target.rstrip("s"):
            return w
    # substring containment (e.g. "Lord-Celestant on Dracoth" vs "Lord-Celestant")
    contains = [w for cand, w in by_name.items() if target in cand or cand in target]
    if len(contains) == 1:
        return contains[0]
    close = difflib.get_close_matches(target, list(by_name), n=1, cutoff=0.8)
    if close:
        return by_name[close[0]]
    return None


def merge_roster(roster: Roster) -> dict:
    """Return roster dict with a ``warscroll`` object merged into every
    hero/unit entry (None when no match was found)."""
    slug = resolve_faction_slug(roster.faction)
    warscrolls = fetch_faction_warscrolls(slug) if slug else []

    data = roster.model_dump()
    data["faction_slug"] = slug
    unmatched = []

    def attach(entry: dict):
        ws = find_warscroll(entry["name"], warscrolls)
        entry["warscroll"] = ws
        if ws is None:
            unmatched.append(entry["name"])

    for regiment in data["regiments"]:
        attach(regiment["hero"])
        for unit in regiment["units"]:
            attach(unit)
    for unit in data["auxiliaries"]:
        attach(unit)

    data["unmatched_units"] = unmatched
    return data

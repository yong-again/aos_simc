"""Text-to-JSON roster parsing via the Gemini API.

Takes plain text copied from army builders such as New Recruit and
returns a validated ``Roster`` (Pydantic) using Gemini structured
output (``response_schema``), as required by the spec.

Parse results are cached on disk keyed by a hash of the roster text,
so re-parsing the same roster (common while testing) costs no Gemini
calls. Delete ``app/data/roster_cache.json`` to clear the cache.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading

from google import genai
from google.genai import types

from ..models.roster import Roster
from ..scraper.wahapedia import DATA_DIR

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")

ROSTER_CACHE_FILE = DATA_DIR / "roster_cache.json"
_cache_lock = threading.Lock()

PARSE_PROMPT = """\
You are a parser for Warhammer Age of Sigmar 4th edition army rosters.
The input is plain text copied from an army builder app (e.g. New Recruit).

Extract the roster into the requested JSON schema:
- Each regiment is led by exactly one hero; the units that follow the hero
  in the same regiment block belong to that regiment.
- is_general is true for the hero marked as General.
- is_reinforced is true when a unit is marked Reinforced (or has doubled
  unit size / points).
- options: copy EVERY bullet line ("•", "-", "*") listed under a hero or
  unit, verbatim minus the bullet character. This includes weapon/wargear
  choices with counts (e.g. "2x Privateer Heavy Weapon", "1x Skypike"),
  champion/standard bearer/musician upgrades, "A or B" choices, and
  enhancements/artefacts/heroic traits/spells with their point costs.
  Only two bullet lines are NOT options: the "General" marker (sets
  is_general) and the "Reinforced" marker (sets is_reinforced) — all
  OTHER bullets of that same unit still go into options.
  A unit with no bullet lines has options: [].

  Example input:
    Skywardens (260)
    • Reinforced
    • 2x Aethermatic Volley Gun and Gun Butt
    • 2x Skyrigger Heavy Weapon and Gun Butt
  Example output for that unit:
    {{"name": "Skywardens", "points": 260, "is_reinforced": true,
      "options": ["2x Aethermatic Volley Gun and Gun Butt",
                  "2x Skyrigger Heavy Weapon and Gun Butt"]}}
- faction_terrain is the faction terrain feature name, or "" if absent.
- total_points is the army total; if absent, sum the unit points.
- Ignore army-builder footers (e.g. "Created with ...", "Data Version"),
  battle tactic cards and manifestation lore lines.

Roster text:
---
{roster_text}
---
"""

GENERATE_PROMPT = """\
You are building a Warhammer Age of Sigmar 4th edition opponent army.
Create a plausible {points}-point roster for the faction "{faction}" using
ONLY unit names from this list (with their points cost):

{unit_catalog}

Rules of thumb:
- 1 to 4 regiments, each led by exactly one HERO unit; mark one hero as
  the general (is_general = true).
- Non-hero units go in the regiment "units" list.
- Stay at or under {points} total points, as close to it as possible.
- Set total_points to the actual sum.
- faction must be "{faction}". Pick a fitting army_name.
"""


_client_instance: genai.Client | None = None


def _client() -> genai.Client:
    # cached singleton: a throwaway Client can be garbage-collected while
    # a request is in flight, closing its underlying httpx client
    global _client_instance
    if _client_instance is None:
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY environment variable is not set")
        _client_instance = genai.Client(api_key=api_key)
    return _client_instance


def _structured_call(prompt: str) -> Roster:
    response = _client().models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=Roster,
            temperature=0.2,
        ),
    )
    parsed = response.parsed
    if isinstance(parsed, Roster):
        return parsed
    return Roster.model_validate_json(response.text)


def _roster_cache_key(roster_text: str) -> str:
    """Hash of the roster text, insensitive to whitespace differences so
    re-pasting the same roster hits the cache."""
    normalized = re.sub(r"\s+", " ", roster_text).strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]


def _load_roster_cache() -> dict:
    if ROSTER_CACHE_FILE.exists():
        return json.loads(ROSTER_CACHE_FILE.read_text(encoding="utf-8"))
    return {}


def parse_roster_text(roster_text: str, use_cache: bool = True) -> Roster:
    """Parse free-form army builder text into a validated Roster.

    Identical roster text is served from the disk cache without calling
    Gemini; pass ``use_cache=False`` to force a fresh parse.
    """
    key = _roster_cache_key(roster_text)
    if use_cache:
        with _cache_lock:
            cached = _load_roster_cache().get(key)
        if cached is not None:
            return Roster.model_validate(cached)

    roster = _structured_call(PARSE_PROMPT.format(roster_text=roster_text))

    with _cache_lock:
        cache = _load_roster_cache()
        cache[key] = roster.model_dump()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        ROSTER_CACHE_FILE.write_text(
            json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    return roster


def generate_opponent_roster(
    faction: str, unit_catalog: list[dict], points: int = 2000
) -> Roster:
    """Have Gemini compose an AI opponent roster from real warscroll data."""
    catalog = "\n".join(
        f"- {w['name']} ({w['points']} pts){' [HERO]' if 'HERO' in w.get('keywords', []) else ''}"
        for w in unit_catalog
        if w.get("points")
    )
    return _structured_call(
        GENERATE_PROMPT.format(points=points, faction=faction, unit_catalog=catalog)
    )

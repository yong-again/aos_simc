"""Text-to-JSON roster parsing via the Gemini API.

Takes plain text copied from army builders such as New Recruit and
returns a validated ``Roster`` (Pydantic) using Gemini structured
output (``response_schema``), as required by the spec.
"""

from __future__ import annotations

import os

from google import genai
from google.genai import types

from ..models.roster import Roster

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")

PARSE_PROMPT = """\
You are a parser for Warhammer Age of Sigmar 4th edition army rosters.
The input is plain text copied from an army builder app (e.g. New Recruit).

Extract the roster into the requested JSON schema:
- Each regiment is led by exactly one hero; the units that follow the hero
  in the same regiment block belong to that regiment.
- is_general is true for the hero marked as General.
- is_reinforced is true when a unit is marked Reinforced (or has doubled
  unit size / points).
- options collects enhancements, artefacts, heroic traits, spells, marks
  and wargear choices listed under the hero/unit.
- faction_terrain is the faction terrain feature name, or "" if absent.
- total_points is the army total; if absent, sum the unit points.

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


def parse_roster_text(roster_text: str) -> Roster:
    """Parse free-form army builder text into a validated Roster."""
    return _structured_call(PARSE_PROMPT.format(roster_text=roster_text))


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

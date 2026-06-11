"""Plain-text ability → structured parameters via Gemini.

Converts scraped warscroll ability text (name/timing/declare/effect)
into the machine-readable ``StructuredAbility`` schema so the combat
engine can apply buffs/debuffs automatically.

Warscrolls are batched (several per API call) to keep request counts —
and therefore rate-limit pressure — low when structuring whole factions.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from ..models.ability import StructuredAbility

# allow standalone use (e.g. `python -m app.scraper.wahapedia`)
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

SYSTEM_PROMPT = (
    "You are a rules engine parser for a Warhammer Age of Sigmar 4th "
    "edition battle simulator. Convert the plain text ability description "
    "into a strict, machine-readable JSON format based on the provided "
    "schema. Lowering a target roll (e.g., 4+ to 3+) for hit/wound/save "
    "should be represented as a 'subtract' modifier."
)

USER_PROMPT = """\
Convert every ability of every warscroll below. Return one entry per
warscroll, with `warscroll_id` copied verbatim and the abilities in the
same order as given. If an ability changes no stats (pure movement,
summoning, etc.), return it with an empty `modifiers` list.

{payload}
"""

# seconds to sleep between Gemini calls (free-tier RPM safety)
GEMINI_DELAY_S = float(os.environ.get("GEMINI_DELAY_S", "2.0"))
# how many warscrolls to convert per API call
BATCH_SIZE = int(os.environ.get("ABILITY_BATCH_SIZE", "8"))


class _WarscrollAbilities(BaseModel):
    warscroll_id: str = Field(description="입력에서 받은 warscroll_id 그대로")
    abilities: list[StructuredAbility]


def _structure_batch(items: list[dict]) -> dict[str, list[dict]]:
    """One Gemini call: items = [{warscroll_id, name, abilities: [...]}].
    Returns {warscroll_id: [structured ability dicts]}."""
    from google.genai import types

    from .roster_parser import GEMINI_MODEL, _client

    payload = json.dumps(
        [
            {
                "warscroll_id": it["warscroll_id"],
                "unit_name": it["name"],
                "abilities": [
                    {
                        "name": a["name"].strip(),
                        "timing": a["timing"],
                        "declare": a["declare"],
                        "effect": a["effect"],
                    }
                    for a in it["abilities"]
                ],
            }
            for it in items
        ],
        ensure_ascii=False,
        indent=1,
    )
    response = _client().models.generate_content(
        model=GEMINI_MODEL,
        contents=USER_PROMPT.format(payload=payload),
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=list[_WarscrollAbilities],
            temperature=0.0,
        ),
    )
    parsed = response.parsed
    if parsed is None:
        parsed = [
            _WarscrollAbilities.model_validate(x) for x in json.loads(response.text)
        ]
    return {w.warscroll_id: [a.model_dump() for a in w.abilities] for w in parsed}


def structure_warscroll_abilities(warscrolls: list[dict]) -> bool:
    """Attach a ``structured`` object to every ability of every warscroll
    that doesn't have one yet (merge — original text is kept for the UI).

    Mutates ``warscrolls`` in place; returns True if anything changed.
    Individual batch failures are skipped so one bad response doesn't
    abort a whole faction.
    """
    pending = [
        ws
        for ws in warscrolls
        if ws.get("abilities")
        and any("structured" not in a for a in ws["abilities"])
    ]
    if not pending:
        return False
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        print("[ability_parser] GEMINI_API_KEY not set — skipping structuring")
        return False

    changed = False
    for start in range(0, len(pending), BATCH_SIZE):
        batch = pending[start : start + BATCH_SIZE]
        items = [
            {"warscroll_id": ws["id"], "name": ws["name"], "abilities": ws["abilities"]}
            for ws in batch
        ]
        try:
            results = _structure_batch(items)
        except Exception as e:  # rate limit / malformed response: skip batch
            print(f"[ability_parser] batch failed ({e}); skipping {len(batch)} warscrolls")
            time.sleep(GEMINI_DELAY_S)
            continue
        for ws in batch:
            structured = results.get(ws["id"])
            if not structured:
                continue
            for i, ability in enumerate(ws["abilities"]):
                if i < len(structured):
                    ability["structured"] = structured[i]
                    changed = True
        if start + BATCH_SIZE < len(pending):
            time.sleep(GEMINI_DELAY_S)
    return changed

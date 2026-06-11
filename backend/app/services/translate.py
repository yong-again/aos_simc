"""Korean translation of warscroll abilities via Gemini.

Translations are requested lazily (one warscroll at a time, when the
user opens a unit panel in Korean mode) and cached permanently in
``app/data/translations_ko.json`` so each warscroll is only ever
translated once.
"""

from __future__ import annotations

import json
import threading

from pydantic import BaseModel, Field

from ..scraper.wahapedia import DATA_DIR, fetch_faction_warscrolls

CACHE_FILE = DATA_DIR / "translations_ko.json"
_lock = threading.Lock()


class AbilityKo(BaseModel):
    name: str
    timing: str = ""
    declare: str = ""
    effect: str = ""


class WarscrollKo(BaseModel):
    abilities: list[AbilityKo] = Field(default_factory=list)


TRANSLATE_PROMPT = """\
You are translating Warhammer Age of Sigmar 4th edition warscroll rules
text from English to Korean for Korean players.

Rules:
- Translate naturally into Korean rules language (존댓말 불필요, 규칙서 문체).
- Keep game keywords in UPPERCASE English as-is: HERO, SHOOT, CHARGE,
  RUN, RETREAT, WARD, unit keywords, faction names, unit names.
- Keep dice notation (D6, 2D6, 3+) and distances (12") unchanged.
- Translate ability names into Korean, appending nothing.
- Keep the same number of abilities, in the same order.

Translate the abilities of the warscroll "{name}":

{abilities_json}
"""


def _load_cache() -> dict:
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    return {}


def _save_cache(cache: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(
        json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def translate_warscroll_ko(faction_slug: str, warscroll_id: str) -> dict:
    """Return {'abilities': [...ko...]} for one warscroll, cached on disk."""
    key = f"{faction_slug}:{warscroll_id}"
    with _lock:
        cache = _load_cache()
        if key in cache:
            return cache[key]

    warscrolls = fetch_faction_warscrolls(faction_slug)
    ws = next((w for w in warscrolls if w["id"] == warscroll_id), None)
    if ws is None:
        raise ValueError(f"Unknown warscroll: {warscroll_id}")
    if not ws.get("abilities"):
        return {"abilities": []}

    # local import so the scraper/sim stack works without the genai package
    from google.genai import types

    from .roster_parser import GEMINI_MODEL, _client

    abilities_json = json.dumps(
        [
            {
                "name": a["name"].strip(),
                "timing": a["timing"],
                "declare": a["declare"],
                "effect": a["effect"],
            }
            for a in ws["abilities"]
        ],
        ensure_ascii=False,
        indent=1,
    )
    response = _client().models.generate_content(
        model=GEMINI_MODEL,
        contents=TRANSLATE_PROMPT.format(name=ws["name"], abilities_json=abilities_json),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=WarscrollKo,
            temperature=0.1,
        ),
    )
    parsed = response.parsed
    if not isinstance(parsed, WarscrollKo):
        parsed = WarscrollKo.model_validate_json(response.text)
    result = parsed.model_dump()

    with _lock:
        cache = _load_cache()
        cache[key] = result
        _save_cache(cache)
    return result

"""Wahapedia AoS4 warscroll crawler & parser.

URL structure
-------------
Warscrolls per faction live at a single static-HTML page:

    https://wahapedia.ru/aos4/factions/{slug}/warscrolls.html

Every warscroll is one ``div.datasheet`` block whose internal layout is
stable across factions:

    a[name=<Unit-Anchor>]              unit anchor (also used by regiment
                                       option links between warscrolls)
    .wsHeaderIn                        unit name (+ optional .wsAddName)
    .AoS_profile                       core stats:
        .wsMove / .wsWounds / .wsSave / .wsBravery   (bravery == Control)
    table.wTable                       weapon tables; section header rows
                                       (tr.wsHeaderRow) say RANGED/MELEE
                                       WEAPONS, data rows are tr.wsDataRow
                                       with td.wsCell values in the order
                                       Rng, Atk, Hit, Wnd, Rnd, Dmg
    .PitchedBattleProfile              Unit Size / Points / Base size /
                                       Can be reinforced / Regiment Options
    .abHeader + .abBody                abilities (timing in header,
                                       name/declare/effect in body)
    .wsKeywordLine1 / .wsKeywordLine2  unit keywords / faction keywords
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup, Tag

from ..factions import FACTIONS

BASE_URL = "https://wahapedia.ru/aos4/factions/{slug}/warscrolls.html"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
DATA_DIR = Path(__file__).resolve().parents[1] / "data"
REQUEST_DELAY_S = 1.0  # be polite between faction fetches


def _text(node: Tag | None) -> str:
    if node is None:
        return ""
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()


def _parse_stat(value: str) -> str:
    """Keep stats as display strings ('14\"', '3+', '8'); sim layer
    converts them numerically and handles '-' / 'D6' style values."""
    return value.replace("”", '"').strip()


def _parse_weapons(datasheet: Tag) -> tuple[list[dict], list[dict]]:
    ranged: list[dict] = []
    melee: list[dict] = []
    table = datasheet.select_one("table.wTable")
    if table is None:
        return ranged, melee

    current = None
    for tr in table.find_all("tr"):
        classes = tr.get("class") or []
        if "wsHeaderRow" in classes:
            header = _text(tr).upper()
            if "RANGED" in header:
                current = ranged
            elif "MELEE" in header:
                current = melee
            continue
        if "wsDataRow" in classes and "wsDataRow_short" not in classes:
            cells = [td for td in tr.find_all("td") if "wsCell" in (td.get("class") or [])]
            # several td.wsDataCell_long exist per row; the weapon name is
            # in the first one that has text (others are layout spacers)
            name = ""
            abilities = []
            for name_td in tr.select("td.wsDataCell_long"):
                for ab in name_td.select(".wsWeaponAbility"):
                    ab_text = _text(ab)
                    if ab_text:
                        abilities.append(ab_text)
                    ab.extract()
                name = _text(name_td)
                if name:
                    break
            if current is None or not name:
                continue
            values = [_parse_stat(_text(td)) for td in cells]
            # ranged rows: [Rng, Atk, Hit, Wnd, Rnd, Dmg]; melee rows have
            # an empty leading range cell
            if current is ranged and len(values) >= 6:
                rng, atk, hit, wnd, rnd, dmg = values[:6]
            elif len(values) >= 6:
                _, atk, hit, wnd, rnd, dmg = values[:6]
                rng = ""
            elif len(values) == 5:
                atk, hit, wnd, rnd, dmg = values
                rng = ""
            else:
                continue
            current.append(
                {
                    "name": name,
                    "range": rng,
                    "attacks": atk,
                    "hit": hit,
                    "wound": wnd,
                    "rend": rnd,
                    "damage": dmg,
                    "abilities": abilities,
                }
            )
    return ranged, melee


def _parse_battle_profile(datasheet: Tag) -> dict:
    profile = {
        "unit_size": None,
        "points": None,
        "base_size": "",
        "can_be_reinforced": False,
        "regiment_options": "",
    }
    box = datasheet.select_one(".PitchedBattleProfile")
    if box is None:
        return profile
    text = _text(box)
    m = re.search(r"Unit Size\s*:?\s*(\d+)", text)
    if m:
        profile["unit_size"] = int(m.group(1))
    m = re.search(r"Points\s*:?\s*(\d+)", text)
    if m:
        profile["points"] = int(m.group(1))
    m = re.search(r"Base size\s*:?\s*([\d×x.\s]+mm)", text)
    if m:
        profile["base_size"] = m.group(1).strip()
    m = re.search(r"Can be reinforced\s*:?\s*(Yes|No)", text, re.I)
    if m:
        profile["can_be_reinforced"] = m.group(1).lower() == "yes"
    m = re.search(r"Regiment Options\s*:?\s*(.+)$", text)
    if m:
        profile["regiment_options"] = m.group(1).strip()
    return profile


def _parse_abilities(datasheet: Tag) -> list[dict]:
    abilities = []
    for body in datasheet.select(".abBody"):
        header_td = None
        # the timing header sits in the sibling table just before the body
        prev = body.find_previous("td", class_="abHeader")
        if prev is not None:
            header_td = prev
        name_tag = body.find("b")
        name = _text(name_tag).rstrip(":") if name_tag else ""
        full = _text(body)
        declare = ""
        effect = ""
        m = re.search(r"Declare\s*:\s*(.*?)(?:Effect\s*:|$)", full, re.S)
        if m:
            declare = m.group(1).strip()
        m = re.search(r"Effect\s*:\s*(.*)$", full, re.S)
        if m:
            effect = m.group(1).strip()
        abilities.append(
            {
                "name": name,
                "timing": _text(header_td),
                "declare": declare,
                "effect": effect or full,
            }
        )
    return abilities


def _parse_keywords(datasheet: Tag) -> list[str]:
    keywords: list[str] = []
    for line in datasheet.select(".wsKeywordLine1, .wsKeywordLine2"):
        # keyword phrases are comma-separated; each phrase is one or more
        # adjacent span.kwb words ("STORMCAST ETERNALS" is two spans)
        for phrase in _text(line).split(","):
            phrase = phrase.strip()
            if phrase:
                keywords.append(phrase)
    return keywords


def parse_warscrolls(html: str, faction_slug: str) -> list[dict]:
    """Parse one faction warscrolls page into a list of warscroll dicts."""
    soup = BeautifulSoup(html, "html.parser")
    faction = FACTIONS[faction_slug]
    warscrolls = []

    for ds in soup.select("div.datasheet"):
        header = ds.select_one(".wsHeaderIn")
        if header is None:
            continue
        # name may contain a subtitle div (.wsAddName), e.g. "on Dracoth"
        add = header.select_one(".wsAddName")
        add_name = _text(add) if add else ""
        if add:
            add.extract()
        # drop the image-search icon
        for icon in header.select(".picSearch"):
            icon.extract()
        name = _text(header)
        if add_name:
            name = f"{name} {add_name}"

        # units with a Ward save use .AoS_profile_Ward (extra .wsWard div)
        stats = ds.select_one(".AoS_profile, .AoS_profile_Ward")
        anchor = ds.find("a", attrs={"name": True})
        ranged, melee = _parse_weapons(ds)
        ws = {
            "id": anchor["name"] if anchor else re.sub(r"\W+", "-", name),
            "name": name,
            "faction": faction["name"],
            "faction_slug": faction_slug,
            "grand_alliance": faction["alliance"],
            "move": _parse_stat(_text(stats.select_one(".wsMove")) if stats else ""),
            "health": _parse_stat(_text(stats.select_one(".wsWounds")) if stats else ""),
            "save": _parse_stat(_text(stats.select_one(".wsSave")) if stats else ""),
            "control": _parse_stat(_text(stats.select_one(".wsBravery")) if stats else ""),
            "ward": _parse_stat(_text(stats.select_one(".wsWard")) if stats else ""),
            "ranged_weapons": ranged,
            "melee_weapons": melee,
            "abilities": _parse_abilities(ds),
            "keywords": _parse_keywords(ds),
        }
        ws.update(_parse_battle_profile(ds))
        warscrolls.append(ws)

    return warscrolls


def fetch_faction_warscrolls(faction_slug: str, force: bool = False) -> list[dict]:
    """Fetch + parse one faction, with a JSON file cache in app/data."""
    if faction_slug not in FACTIONS:
        raise ValueError(f"Unknown faction slug: {faction_slug}")
    cache_file = DATA_DIR / f"{faction_slug}.json"
    if cache_file.exists() and not force:
        return json.loads(cache_file.read_text(encoding="utf-8"))

    resp = requests.get(
        BASE_URL.format(slug=faction_slug),
        headers={"User-Agent": USER_AGENT},
        timeout=60,
    )
    resp.raise_for_status()
    warscrolls = parse_warscrolls(resp.text, faction_slug)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        json.dumps(warscrolls, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return warscrolls


def fetch_all_factions(force: bool = False) -> dict[str, list[dict]]:
    db = {}
    for slug in FACTIONS:
        cached = (DATA_DIR / f"{slug}.json").exists()
        db[slug] = fetch_faction_warscrolls(slug, force=force)
        if force or not cached:
            time.sleep(REQUEST_DELAY_S)
    return db


if __name__ == "__main__":
    import sys

    slugs = sys.argv[1:] or list(FACTIONS)
    for slug in slugs:
        scrolls = fetch_faction_warscrolls(slug)
        print(f"{slug}: {len(scrolls)} warscrolls")

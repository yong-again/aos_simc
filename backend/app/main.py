"""FastAPI backend for the AoS 2D battle simulator."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles

# load backend/.env (GEMINI_API_KEY etc.) regardless of the cwd
load_dotenv(Path(__file__).resolve().parents[1] / ".env")
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .factions import FACTIONS, faction_list, resolve_faction_slug
from .scraper.wahapedia import fetch_faction_warscrolls
from .services.merge import merge_roster
from .services.roster_parser import generate_opponent_roster, parse_roster_text
from .sim.engine import (
    BOARD_H,
    BOARD_W,
    auto_deploy,
    build_sim_units,
    simulate,
    unit_payload,
)

app = FastAPI(title="AoS 2D Simulator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class RosterText(BaseModel):
    text: str


class GenerateRequest(BaseModel):
    faction_slug: str
    points: int = 2000


class SimulateRequest(BaseModel):
    player_roster: dict
    enemy_roster: dict
    deployment: list[dict] | None = None
    seed: int | None = None


@app.get("/api/factions")
def get_factions():
    return faction_list()


@app.get("/api/factions/{slug}/warscrolls")
def get_warscrolls(slug: str, force: bool = False):
    if slug not in FACTIONS:
        raise HTTPException(404, f"Unknown faction: {slug}")
    try:
        return fetch_faction_warscrolls(slug, force=force)
    except Exception as e:  # network/scrape failure
        raise HTTPException(502, f"Failed to fetch warscrolls: {e}")


@app.get("/api/factions/{slug}/warscrolls/{ws_id}/ko")
def get_warscroll_ko(slug: str, ws_id: str):
    """Korean translation of one warscroll's abilities (Gemini, disk-cached)."""
    if slug not in FACTIONS:
        raise HTTPException(404, f"Unknown faction: {slug}")
    from .services.translate import translate_warscroll_ko

    try:
        return translate_warscroll_ko(slug, ws_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except RuntimeError as e:
        raise HTTPException(500, str(e))


@app.post("/api/roster/parse")
def parse_roster(body: RosterText):
    if not body.text.strip():
        raise HTTPException(400, "Empty roster text")
    try:
        roster = parse_roster_text(body.text)
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    return merge_roster(roster)


@app.post("/api/roster/parse-file")
async def parse_roster_file(file: UploadFile = File(...)):
    text = (await file.read()).decode("utf-8", errors="replace")
    return parse_roster(RosterText(text=text))


@app.post("/api/roster/generate")
def generate_roster(body: GenerateRequest):
    if body.faction_slug not in FACTIONS:
        raise HTTPException(404, f"Unknown faction: {body.faction_slug}")
    catalog = fetch_faction_warscrolls(body.faction_slug)
    try:
        roster = generate_opponent_roster(
            FACTIONS[body.faction_slug]["name"], catalog, body.points
        )
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    roster.faction = FACTIONS[body.faction_slug]["name"]
    return merge_roster(roster)


class SetupRequest(BaseModel):
    player_roster: dict
    enemy_roster: dict


@app.post("/api/setup")
def setup_battle(body: SetupRequest):
    """Returns sim units with stable uids and default deployment
    positions so the frontend can run the drag-and-drop deployment UI."""
    units = []
    for side, roster in (("player", body.player_roster), ("enemy", body.enemy_roster)):
        side_units = build_sim_units(roster, side)
        auto_deploy(side_units, side)
        units.extend(unit_payload(u) for u in side_units)
    return {"board": {"width": BOARD_W, "height": BOARD_H, "zone_depth": 12},
            "units": units}


@app.post("/api/simulate")
def run_simulation(body: SimulateRequest):
    """Runs the full battle and returns the event stream + result.

    Mode A (frontend) plays events back phase by phase; Mode B jumps
    straight to the result/log — both use this one response.
    """
    result = simulate(
        body.player_roster, body.enemy_roster, body.deployment, body.seed
    )
    return result


# Serve the built frontend (frontend/dist) from the same origin, so the
# whole app can be shared through a single port/tunnel. API routes above
# take precedence; everything else falls through to the SPA files.
_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="frontend")

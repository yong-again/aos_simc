"""Pydantic models for the roster JSON schema defined in the project spec.

These models double as the Gemini ``response_schema`` so the LLM output
is always returned in this exact shape.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RosterHero(BaseModel):
    name: str
    points: int = 0
    is_general: bool = False
    options: list[str] = Field(default_factory=list)


class RosterUnit(BaseModel):
    name: str
    points: int = 0
    options: list[str] = Field(default_factory=list)
    is_reinforced: bool = False


class Regiment(BaseModel):
    hero: RosterHero
    units: list[RosterUnit] = Field(default_factory=list)


class Roster(BaseModel):
    army_name: str
    faction: str
    total_points: int = 0
    regiments: list[Regiment] = Field(default_factory=list)
    auxiliaries: list[RosterUnit] = Field(default_factory=list)
    faction_terrain: str = ""

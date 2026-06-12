"""Terrain and line-of-sight system (AoS4 core rules).

Terrain pieces are circles on the 60"x44" battlefield with a height and
a set of traits:

- Cover:          -1 to hit for shots at units behind / wholly on it
                  (ignored if the target charged this turn or can FLY)
- Obscuring:      blocks shooting visibility through or onto it
                  (ignored if the target can FLY or is within 3" of the
                  attacker; terrain parts within 3" of the attacker are
                  always ignored)
- Impassable:     cannot be moved through or ended on
- Unstable:       cannot end a move above 1" height (we treat the whole
                  footprint as >1" when height > 1)
- Place of Power: heroes within 3" roll a D6 at the start of any turn —
                  1: D3 mortal damage; 2+: +1 to casting/chanting (not
                  unbinding) for WIZARD/PRIEST, other heroes count as
                  WIZARD (1) for the turn (may unbind/banish)

Faction terrain additionally exists as a targetable SimUnit; the
Terrain piece here only provides its footprint for visibility checks.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class Terrain:
    tid: str
    name: str
    x: float
    y: float
    radius: float
    height: float
    traits: set = field(default_factory=set)
    is_faction: bool = False
    side: str = ""  # owner, for faction terrain
    unit_uid: str = ""  # linked SimUnit when targetable (faction terrain)

    def contains(self, x: float, y: float) -> bool:
        return math.hypot(self.x - x, self.y - y) <= self.radius

    def distance_to(self, x: float, y: float) -> float:
        return max(0.0, math.hypot(self.x - x, self.y - y) - self.radius)

    def payload(self) -> dict:
        return {
            "tid": self.tid, "name": self.name,
            "x": self.x, "y": self.y,
            "radius": self.radius, "height": self.height,
            "traits": sorted(self.traits),
            "is_faction": self.is_faction, "side": self.side,
        }


def _segment_hits_circle(x1, y1, x2, y2, cx, cy, r) -> bool:
    """True if the segment (x1,y1)-(x2,y2) passes through the circle."""
    dx, dy = x2 - x1, y2 - y1
    seg_len2 = dx * dx + dy * dy
    if seg_len2 == 0:
        return math.hypot(cx - x1, cy - y1) <= r
    t = max(0.0, min(1.0, ((cx - x1) * dx + (cy - y1) * dy) / seg_len2))
    px, py = x1 + t * dx, y1 + t * dy
    return math.hypot(cx - px, cy - py) <= r


def _ignored_for_attacker(attacker, t: Terrain) -> bool:
    """Terrain parts within 3" of the attacking unit are ignored when
    judging whether the target is behind terrain (core rules)."""
    return t.distance_to(attacker.x, attacker.y) <= 3.0


def can_see(attacker, target, terrains: list[Terrain]) -> tuple[bool, str]:
    """Shooting visibility. Returns (visible, blocking terrain name)."""
    if attacker.distance(target) <= 3.0:
        return True, ""
    flies = any("FLY" == k or k.startswith("FLY") for k in target.keywords)
    if flies:
        return True, ""
    for t in terrains:
        if "Obscuring" not in t.traits:
            continue
        if _ignored_for_attacker(attacker, t):
            continue
        # target standing on obscuring terrain cannot be targeted either
        if t.contains(target.x, target.y):
            return False, t.name
        if _segment_hits_circle(attacker.x, attacker.y, target.x, target.y,
                                t.x, t.y, t.radius):
            return False, t.name
    return True, ""


def cover_applies(attacker, target, terrains: list[Terrain]) -> str:
    """Returns the covering terrain's name if the target benefits from
    Cover (-1 to hit), else ''. Charging units and flyers gain nothing."""
    if getattr(target, "charged_this_turn", False):
        return ""
    if any("FLY" == k or k.startswith("FLY") for k in target.keywords):
        return ""
    for t in terrains:
        if "Cover" not in t.traits:
            continue
        if _ignored_for_attacker(attacker, t):
            continue
        # wholly on the terrain, or behind it (LoS crosses the footprint)
        if t.contains(target.x, target.y):
            return t.name
        if _segment_hits_circle(attacker.x, attacker.y, target.x, target.y,
                                t.x, t.y, t.radius):
            return t.name
    return ""


def adjust_move_for_terrain(
    unit, nx: float, ny: float, step: float, terrains: list[Terrain]
) -> tuple[float, float, float, list[str]]:
    """Applies terrain movement rules to a straight move toward (nx, ny).

    - climbing terrain taller than 1" costs its height in extra movement
      (we shorten the move by that much)
    - Impassable terrain can't be entered: the move stops at its edge
    - moves may not end inside Unstable terrain taller than 1": the
      endpoint is pulled back to its edge

    Returns (nx, ny, effective_step, notes)."""
    notes: list[str] = []
    sx, sy = unit.x, unit.y

    # climb tax for tall terrain crossed by the path
    climb_cost = 0.0
    for t in terrains:
        if t.height > 1.0 and "Impassable" not in t.traits:
            if _segment_hits_circle(sx, sy, nx, ny, t.x, t.y, t.radius):
                climb_cost += t.height
    if climb_cost > 0:
        new_step = max(0.0, step - climb_cost)
        if new_step < step:
            ratio = new_step / step if step else 0.0
            nx = sx + (nx - sx) * ratio
            ny = sy + (ny - sy) * ratio
            step = new_step
            notes.append(f"climb -{climb_cost:.0f}\"")

    # impassable: stop at the edge
    for t in terrains:
        if "Impassable" not in t.traits:
            continue
        if _segment_hits_circle(sx, sy, nx, ny, t.x, t.y, t.radius):
            # walk the path until just before the terrain edge
            full = math.hypot(nx - sx, ny - sy) or 0.001
            lo, hi = 0.0, 1.0
            for _ in range(20):
                mid = (lo + hi) / 2
                px, py = sx + (nx - sx) * mid, sy + (ny - sy) * mid
                if math.hypot(px - t.x, py - t.y) <= t.radius + 0.5:
                    hi = mid
                else:
                    lo = mid
            nx, ny = sx + (nx - sx) * lo, sy + (ny - sy) * lo
            step = full * lo
            notes.append(f"blocked by {t.name}")

    # unstable: cannot end the move on terrain taller than 1"
    for t in terrains:
        if "Unstable" in t.traits and t.height > 1.0 and t.contains(nx, ny):
            d = math.hypot(nx - t.x, ny - t.y) or 0.001
            push = (t.radius + 0.3) / d
            nx, ny = t.x + (nx - t.x) * push, t.y + (ny - t.y) * push
            notes.append(f"can't stop on {t.name}")

    return nx, ny, step, notes


def generate_battlefield_terrain(rng, board_w: float, board_h: float) -> list[Terrain]:
    """A small seeded set of neutral terrain in the middle band."""
    presets = [
        ("Wyldwood", 2.5, 2.0, {"Cover", "Obscuring"}),
        ("Ancient Rocks", 1.6, 3.0, {"Impassable"}),
        ("Crumbling Ruins", 2.2, 2.0, {"Cover", "Unstable"}),
        ("Nexus of Power", 1.2, 0.5, {"Place of Power"}),
    ]
    terrains: list[Terrain] = []
    for i, (name, radius, height, traits) in enumerate(presets):
        for _ in range(30):  # rejection sampling against overlaps
            x = rng.uniform(10, board_w - 10)
            y = rng.uniform(15, board_h - 15)
            if all(
                math.hypot(t.x - x, t.y - y) > t.radius + radius + 3.0
                for t in terrains
            ):
                terrains.append(Terrain(
                    tid=f"terrain-{i}", name=name, x=round(x, 1), y=round(y, 1),
                    radius=radius, height=height, traits=set(traits),
                ))
                break
    return terrains

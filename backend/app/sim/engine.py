"""Battle simulation engine.

Runs a full game on a 60" x 44" battlefield (standard AoS matched play
size) over at most 5 battle rounds. Each player turn walks the core
phase order: Movement -> Shooting -> Charge -> Combat. Every state
change is appended to an event list so the frontend can either play it
back phase by phase (Mode A) or jump straight to the result (Mode B).

Both armies are driven by the same heuristic AI required by the spec:
move toward the nearest enemy, shoot anything in range, charge when
possible, fight in combat.
"""

from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass, field

from .combat import expected_damage, roll_value, unit_attack

BOARD_W = 60.0  # inches
BOARD_H = 44.0
COMBAT_RANGE = 3.0  # units within 3" are in combat
MAX_ROUNDS = 5


@dataclass
class SimUnit:
    uid: str
    name: str
    side: str  # "player" | "enemy"
    x: float
    y: float
    move: float
    save: str
    ward: str
    control: int
    models: int
    health_per_model: int
    wounds_taken: int = 0
    points: int = 0
    faction: str = ""
    is_hero: bool = False
    is_monster: bool = False
    is_war_machine: bool = False
    base_w: float = 1.0  # base width in inches (per model)
    base_h: float = 1.0  # base depth in inches (per model)
    ranged: list = field(default_factory=list)
    melee: list = field(default_factory=list)

    @property
    def total_health(self) -> int:
        return self.models * self.health_per_model - self.wounds_taken

    @property
    def models_alive(self) -> int:
        if self.health_per_model <= 0:
            return 0
        return max(0, math.ceil(self.total_health / self.health_per_model))

    @property
    def alive(self) -> bool:
        return self.total_health > 0

    def distance(self, other: "SimUnit") -> float:
        return math.hypot(self.x - other.x, self.y - other.y)


def _num(stat: str, default: float = 0.0) -> float:
    m = re.search(r"\d+", stat or "")
    return float(m.group()) if m else default


def _base_size_in(base_size: str) -> tuple[float, float]:
    """Parse Wahapedia base size ('32mm', '120 × 92mm') into inches.
    Round bases return (d, d); ovals return (length, width)."""
    nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", base_size or "")]
    if not nums:
        return (1.0, 1.0)
    w = nums[0] / 25.4
    h = nums[1] / 25.4 if len(nums) > 1 else w
    return (round(w, 2), round(h, 2))


def build_sim_units(merged_roster: dict, side: str) -> list[SimUnit]:
    """Flatten a merged roster (with warscroll data) into sim units."""
    units: list[SimUnit] = []

    def add(entry: dict, idx: int):
        ws = entry.get("warscroll")
        if not ws:
            return
        models = ws.get("unit_size") or 1
        if entry.get("is_reinforced"):
            models *= 2
        keywords = ws.get("keywords", [])
        base_w, base_h = _base_size_in(ws.get("base_size", ""))
        units.append(
            SimUnit(
                uid=f"{side}-{idx}-{re.sub(r'[^A-Za-z0-9]+', '-', entry['name'])}",
                name=entry["name"],
                side=side,
                x=0.0,
                y=0.0,
                move=_num(ws.get("move", ""), 5.0),
                save=ws.get("save", "6+"),
                ward=ws.get("ward", ""),
                control=int(_num(ws.get("control", ""), 1)),
                models=models,
                health_per_model=int(_num(ws.get("health", ""), 1)),
                points=entry.get("points") or ws.get("points") or 0,
                faction=ws.get("faction", ""),
                is_hero="HERO" in keywords,
                is_monster="MONSTER" in keywords,
                is_war_machine="WAR MACHINE" in keywords,
                base_w=base_w,
                base_h=base_h,
                ranged=ws.get("ranged_weapons", []),
                melee=ws.get("melee_weapons", []),
            )
        )

    i = 0
    for reg in merged_roster.get("regiments", []):
        add(reg["hero"], i)
        i += 1
        for u in reg.get("units", []):
            add(u, i)
            i += 1
    for u in merged_roster.get("auxiliaries", []):
        add(u, i)
        i += 1
    return units


def auto_deploy(units: list[SimUnit], side: str) -> None:
    """Spread units along the owner's long table edge (12" deployment zone)."""
    n = len(units)
    for i, u in enumerate(units):
        u.x = BOARD_W * (i + 1) / (n + 1)
        u.y = 6.0 if side == "enemy" else BOARD_H - 6.0


class BattleSimulator:
    def __init__(self, player_units, enemy_units, seed: int | None = None):
        self.units = list(player_units) + list(enemy_units)
        self.rng = random.Random(seed)
        self.events: list[dict] = []
        self.log: list[str] = []
        self.round = 0

    # -- helpers -------------------------------------------------------
    def side_units(self, side: str, alive_only: bool = True):
        return [
            u for u in self.units if u.side == side and (u.alive or not alive_only)
        ]

    def enemies_of(self, unit: SimUnit):
        return [u for u in self.units if u.side != unit.side and u.alive]

    def emit(self, **event):
        event["round"] = self.round
        self.events.append(event)
        if event.get("text"):
            self.log.append(f"[R{self.round}] {event['text']}")

    def snapshot(self):
        return [
            {
                "uid": u.uid,
                "x": round(u.x, 2),
                "y": round(u.y, 2),
                "models": u.models_alive,
                "health": u.total_health,
                "alive": u.alive,
            }
            for u in self.units
        ]

    # -- phases --------------------------------------------------------
    def movement_phase(self, side: str):
        self.emit(type="phase", side=side, phase="movement")
        for u in self.side_units(side):
            enemies = self.enemies_of(u)
            if not enemies:
                return
            target = min(enemies, key=u.distance)
            dist = u.distance(target)
            if dist <= COMBAT_RANGE:
                continue  # already in combat; hold
            # stop just outside combat range so the charge phase decides
            step = min(u.move, max(dist - (COMBAT_RANGE - 0.5), 0))
            # don't walk into melee if we'd rather shoot from range
            if u.ranged and not u.melee:
                shoot_rng = max(_num(w.get("range", "")) for w in u.ranged)
                step = min(step, max(dist - shoot_rng + 1, 0))
            if step <= 0:
                continue
            nx = u.x + (target.x - u.x) / dist * step
            ny = u.y + (target.y - u.y) / dist * step
            nx = min(max(nx, 0.5), BOARD_W - 0.5)
            ny = min(max(ny, 0.5), BOARD_H - 0.5)
            self.emit(
                type="move", uid=u.uid, target=target.uid,
                dist=round(step, 1),
                frm=[round(u.x, 2), round(u.y, 2)],
                to=[round(nx, 2), round(ny, 2)],
                text=f"{u.name} moves {step:.1f}\" toward {target.name}",
            )
            u.x, u.y = nx, ny

    def shooting_phase(self, side: str):
        self.emit(type="phase", side=side, phase="shooting")
        for u in self.side_units(side):
            if not u.ranged:
                continue
            in_combat = any(
                u.distance(e) <= COMBAT_RANGE for e in self.enemies_of(u)
            )
            usable = [
                w for w in u.ranged
                if not in_combat or any("Shoot in Combat" in a for a in w.get("abilities", []))
            ]
            if not usable:
                continue
            max_range = max(_num(w.get("range", "")) for w in usable)
            targets = [e for e in self.enemies_of(u) if u.distance(e) <= max_range]
            if not targets:
                continue
            target = max(
                targets,
                key=lambda e: expected_damage(usable, u.models_alive, e.save),
            )
            weapons = [w for w in usable if u.distance(target) <= _num(w.get("range", ""))]
            dmg = unit_attack(weapons, u.models_alive, target.save, self.rng, target.ward)
            self.apply_damage(u, target, dmg, "shoots", "shoot")

    def charge_phase(self, side: str):
        self.emit(type="phase", side=side, phase="charge")
        for u in self.side_units(side):
            if not u.melee:
                continue
            enemies = self.enemies_of(u)
            if not enemies:
                return
            target = min(enemies, key=u.distance)
            dist = u.distance(target)
            if dist <= COMBAT_RANGE or dist > 12 + COMBAT_RANGE:
                continue
            charge_roll = self.rng.randint(1, 6) + self.rng.randint(1, 6)
            if charge_roll >= dist - COMBAT_RANGE + 0.5:
                travel = dist - 1.0
                nx = u.x + (target.x - u.x) / dist * travel
                ny = u.y + (target.y - u.y) / dist * travel
                self.emit(
                    type="charge", uid=u.uid, target=target.uid, roll=charge_roll,
                    frm=[round(u.x, 2), round(u.y, 2)], to=[round(nx, 2), round(ny, 2)],
                    text=f"{u.name} charges {target.name} (rolled {charge_roll})",
                )
                u.x, u.y = nx, ny
            else:
                self.emit(
                    type="charge_failed", uid=u.uid, roll=charge_roll,
                    text=f"{u.name} fails its charge (rolled {charge_roll})",
                )

    def combat_phase(self, side: str):
        self.emit(type="phase", side=side, phase="combat")
        # both sides fight in the combat phase, active player's units first
        order = self.side_units(side) + self.side_units(
            "enemy" if side == "player" else "player"
        )
        for u in order:
            if not u.alive or not u.melee:
                continue
            targets = [e for e in self.enemies_of(u) if u.distance(e) <= COMBAT_RANGE]
            if not targets:
                continue
            target = max(
                targets,
                key=lambda e: expected_damage(u.melee, u.models_alive, e.save),
            )
            dmg = unit_attack(u.melee, u.models_alive, target.save, self.rng, target.ward)
            self.apply_damage(u, target, dmg, "hits", "melee")

    def apply_damage(self, attacker: SimUnit, target: SimUnit, dmg: int, verb: str, kind: str):
        if dmg <= 0:
            self.emit(
                type="attack", kind=kind, uid=attacker.uid, target=target.uid, damage=0,
                text=f"{attacker.name} {verb} {target.name} but deals no damage",
            )
            return
        target.wounds_taken += dmg
        slain = not target.alive
        self.emit(
            type="attack", kind=kind, uid=attacker.uid, target=target.uid, damage=dmg,
            slain=slain,
            text=f"{attacker.name} {verb} {target.name} for {dmg} damage"
            + (f" — {target.name} is destroyed!" if slain else ""),
        )

    # -- game loop -----------------------------------------------------
    def run(self) -> dict:
        self.emit(type="deploy", units=self.snapshot(), text="Armies deployed")
        first = "player" if self.rng.random() < 0.5 else "enemy"
        for rnd in range(1, MAX_ROUNDS + 1):
            self.round = rnd
            # roll-off for priority each battle round
            first = "player" if self.rng.random() < 0.5 else "enemy"
            second = "enemy" if first == "player" else "player"
            self.emit(type="round", round_no=rnd, first=first,
                      text=f"Battle round {rnd} begins — {first} goes first")
            for side in (first, second):
                if not self.side_units("player") or not self.side_units("enemy"):
                    break
                self.emit(type="turn", side=side)
                self.movement_phase(side)
                self.shooting_phase(side)
                self.charge_phase(side)
                self.combat_phase(side)
                self.emit(type="state", units=self.snapshot())
            if not self.side_units("player") or not self.side_units("enemy"):
                break

        p_alive = self.side_units("player")
        e_alive = self.side_units("enemy")
        p_points = sum(u.points for u in p_alive)
        e_points = sum(u.points for u in e_alive)
        if bool(p_alive) != bool(e_alive):
            winner = "player" if p_alive else "enemy"
        elif p_points != e_points:
            winner = "player" if p_points > e_points else "enemy"
        else:
            winner = "draw"
        self.emit(
            type="end", winner=winner, player_points=p_points, enemy_points=e_points,
            text=f"Battle ends — winner: {winner} "
            f"(player {p_points} pts vs enemy {e_points} pts surviving)",
        )
        return {
            "winner": winner,
            "rounds_played": self.round,
            "survivors": {
                "player": [
                    {"uid": u.uid, "name": u.name, "models": u.models_alive,
                     "health": u.total_health} for u in p_alive
                ],
                "enemy": [
                    {"uid": u.uid, "name": u.name, "models": u.models_alive,
                     "health": u.total_health} for u in e_alive
                ],
            },
            "events": self.events,
            "log": self.log,
        }


def simulate(
    player_roster: dict,
    enemy_roster: dict,
    deployment: list[dict] | None = None,
    seed: int | None = None,
) -> dict:
    """Entry point used by the API. ``deployment`` carries the player's
    drag-and-drop unit positions: [{uid, x, y}] in inches."""
    player_units = build_sim_units(player_roster, "player")
    enemy_units = build_sim_units(enemy_roster, "enemy")
    auto_deploy(player_units, "player")
    auto_deploy(enemy_units, "enemy")
    if deployment:
        pos = {d["uid"]: d for d in deployment}
        for u in player_units:
            if u.uid in pos:
                u.x = float(pos[u.uid]["x"])
                u.y = float(pos[u.uid]["y"])
    sim = BattleSimulator(player_units, enemy_units, seed=seed)
    result = sim.run()
    result["units"] = [unit_payload(u) for u in sim.units]
    return result


def unit_payload(u: SimUnit) -> dict:
    """Frontend-facing unit descriptor (shared by /api/setup and results)."""
    return {
        "uid": u.uid, "name": u.name, "side": u.side, "faction": u.faction,
        "x": u.x, "y": u.y,
        "models": u.models, "health_per_model": u.health_per_model,
        "is_hero": u.is_hero, "is_monster": u.is_monster,
        "is_war_machine": u.is_war_machine,
        "base_w": u.base_w, "base_h": u.base_h,
        "points": u.points,
    }

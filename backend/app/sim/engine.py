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

from .combat import expected_damage, roll_value, unit_attack, ward_roll
from .effects import (
    apply_turn_mortal_wounds,
    collect_mods,
    collect_mods_detailed,
    describe_effect,
    effective_ward,
)

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
    abilities_raw: list = field(default_factory=list)
    keywords: list = field(default_factory=list)

    @property
    def wizard_level(self) -> int:
        """X from the 'WIZARD ( X )' keyword: casts/unbinds per phase."""
        for k in self.keywords:
            m = re.match(r"WIZARD\s*\(\s*(\d+)\s*\)", k)
            if m:
                return int(m.group(1))
        return 0

    @property
    def has_musician(self) -> bool:
        return any(k.startswith("MUSICIAN") for k in self.keywords)

    @property
    def strike_first(self) -> bool:
        return any("STRIKE-FIRST" in k for k in self.keywords)

    @property
    def strike_last(self) -> bool:
        return any("STRIKE-LAST" in k for k in self.keywords)

    @property
    def untargetable_by_covering_fire(self) -> bool:
        """Manifestations and faction terrain can't be shot by Covering Fire."""
        return any(k in ("MANIFESTATION", "FACTION TERRAIN") for k in self.keywords)

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
                abilities_raw=ws.get("abilities", []),
                keywords=keywords,
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
        self._last_effects: dict[str, tuple] = {}
        self.cp = {"player": 0, "enemy": 0}  # command points (4/round, AoS4)
        # Rules of One bookkeeping, reset at every phase marker:
        self._unit_commands: set[str] = set()   # uids that used a command
        self._army_commands = {"player": set(), "enemy": set()}  # command names

    # -- helpers -------------------------------------------------------
    def side_units(self, side: str, alive_only: bool = True):
        return [
            u for u in self.units if u.side == side and (u.alive or not alive_only)
        ]

    def enemies_of(self, unit: SimUnit):
        return [u for u in self.units if u.side != unit.side and u.alive]

    def emit(self, **event):
        """Appends a structured event. Every event carries a ``category``
        (PHASE/HERO/MOVE/SHOOT/CHARGE/COMBAT/DEFENSE/EFFECT/SYSTEM) so the
        frontend can render log lines by kind without parsing text."""
        event.setdefault("category", "SYSTEM")
        event["round"] = self.round
        self.events.append(event)
        if event.get("text"):
            self.log.append(f"[R{self.round}] {event['text']}")

    def phase_marker(self, side: str, phase: str):
        """Explicit separator logged at the start of every phase. Also
        resets the Rules-of-One command limits (per unit / per army)."""
        self._unit_commands.clear()
        self._army_commands = {"player": set(), "enemy": set()}
        label = phase.replace("_", " ").title()
        self.emit(
            type="phase", category="PHASE", side=side, phase=phase,
            text=f"=== [R{self.round}] {side} {label} Phase ===",
        )

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

    # -- command abilities (AoS4 core) ----------------------------------
    def use_command(self, side: str, command: str, unit: SimUnit, cost: int = 1) -> bool:
        """Spends CP subject to the Rules of One: a unit may use only one
        command per phase, and each command may be used only once per
        army per phase."""
        if self.cp[side] < cost:
            return False
        if unit.uid in self._unit_commands:
            return False
        if command in self._army_commands[side]:
            return False
        self.cp[side] -= cost
        self._unit_commands.add(unit.uid)
        self._army_commands[side].add(command)
        return True

    def emit_command(self, side: str, command: str, unit: SimUnit,
                     category: str, detail: str, healed: int = 0, **extra):
        self.emit(
            type="command", category=category, side=side, command=command,
            uid=unit.uid, cp_left=self.cp[side], healed=healed, **extra,
            text=f"{unit.name} uses '{command}' — {detail} "
            f"(CP left: {self.cp[side]})",
        )

    @staticmethod
    def _other(side: str) -> str:
        return "enemy" if side == "player" else "player"

    def _in_combat(self, unit: SimUnit) -> bool:
        return any(unit.distance(e) <= COMBAT_RANGE for e in self.enemies_of(unit))

    def try_all_out_attack(self, side: str, attacker: SimUnit,
                           atk_mods: dict, category: str) -> None:
        """All-out Attack (1 CP): +1 to hit for this unit's attacks."""
        if atk_mods.get("hit", 0) <= -1:
            return  # hit roll already at the +1 cap
        if not self.use_command(side, "All-out Attack", attacker):
            return
        atk_mods["hit"] = max(-1, atk_mods.get("hit", 0) - 1)
        self.emit_command(side, "All-out Attack", attacker, category, "+1 to hit")

    def try_all_out_defence(self, defender: SimUnit, def_mods: dict,
                            category: str) -> None:
        """All-out Defence (1 CP, reaction): +1 to save for the target.
        The AI saves it for valuable targets (heroes / 200+ pts)."""
        side = defender.side
        if not (defender.is_hero or defender.points >= 200):
            return
        if def_mods.get("save", 0) <= -1:
            return
        if not self.use_command(side, "All-out Defence", defender):
            return
        def_mods["save"] = max(-1, def_mods.get("save", 0) - 1)
        self.emit_command(side, "All-out Defence", defender, category, "+1 to save")

    # -- reactive commands (opponent's turn, AoS4 advanced reactions) ----
    def reaction_redeploy(self, side: str):
        """Redeploy (1 CP): right after the opponent's movement phase, any
        friendly unit not in combat may fall back D6". The AI uses it for
        shooting-focused units threatened by a strong melee charge."""
        if self.cp[side] <= 0:
            return
        for u in self.side_units(side):
            if not u.ranged or self._in_combat(u):
                continue
            # melee units hold their ground; only shooters back off
            shooter = expected_damage(u.ranged, u.models_alive, "4+") >= \
                expected_damage(u.melee, u.models_alive, "4+")
            if not shooter:
                continue
            # heuristic: a strong melee unit within charge threat (15")
            threats = [
                e for e in self.enemies_of(u)
                if e.melee and u.distance(e) <= 12.0 + COMBAT_RANGE
                and expected_damage(e.melee, e.models_alive, u.save) >= 3.0
            ]
            if not threats:
                continue
            threat = max(
                threats,
                key=lambda e: expected_damage(e.melee, e.models_alive, u.save),
            )
            if not self.use_command(side, "Redeploy", u):
                return
            roll = self.rng.randint(1, 6)
            dist = u.distance(threat) or 0.1
            nx = min(max(u.x + (u.x - threat.x) / dist * roll, 0.5), BOARD_W - 0.5)
            ny = min(max(u.y + (u.y - threat.y) / dist * roll, 0.5), BOARD_H - 0.5)
            self.emit_command(
                side, "Redeploy", u, "MOVE",
                f"falls back {roll}\" away from {threat.name}", roll=roll,
            )
            # silent move event: animates on the canvas without a log line
            self.emit(
                type="move", category="MOVE", uid=u.uid, target=threat.uid,
                dist=float(roll), silent=True,
                frm=[round(u.x, 2), round(u.y, 2)], to=[round(nx, 2), round(ny, 2)],
            )
            u.x, u.y = nx, ny
            return  # one Redeploy per reaction window

    def reaction_covering_fire(self, side: str):
        """Covering Fire (1 CP): shoot during the opponent's shooting
        phase at -1 to hit. Used only with spare CP (2+) so All-out
        Defence / Counter-charge stay affordable."""
        if self.cp[side] < 2:
            return
        for u in self.side_units(side):
            if not u.ranged or self._in_combat(u):
                continue
            max_range = max(_num(w.get("range", "")) for w in u.ranged)
            # rule: Covering Fire may only target the CLOSEST enemy unit,
            # and never manifestations or faction terrain
            candidates = [
                e for e in self.enemies_of(u)
                if not e.untargetable_by_covering_fire
            ]
            if not candidates:
                continue
            target = min(candidates, key=u.distance)
            if u.distance(target) > max_range:
                continue
            # not worth a CP if the volley barely scratches at -1 to hit
            if expected_damage(u.ranged, u.models_alive, target.save) < 2.0:
                continue
            if not self.use_command(side, "Covering Fire", u):
                return
            atk_mods, atk_details = collect_mods_detailed(u, self.units, "shooting")
            atk_mods["hit"] = min(1, atk_mods.get("hit", 0) + 1)  # -1 to hit
            def_mods, _ = collect_mods_detailed(target, self.units, "shooting")
            ward = effective_ward(target, def_mods)
            self.emit_command(
                side, "Covering Fire", u, "SHOOT",
                f"shoots its closest enemy {target.name} at -1 to hit",
            )
            dmg, warded = unit_attack(u.ranged, u.models_alive, target.save,
                                      self.rng, ward, atk_mods, def_mods)
            self.apply_damage(u, target, dmg, "shoots", "shoot",
                              warded=warded, ward=ward, applied_details=atk_details)
            return  # one Covering Fire per reaction window

    def reaction_counter_charge(self, side: str):
        """Counter-charge (1 CP): right after the opponent's charge phase,
        a strong melee unit (MONSTER/HERO) within 12" intercepts a charger
        that reached one of our fragile units. Costs 2 CP."""
        if self.cp[side] < 2:
            return
        for ally in self.side_units(side):
            # fragile: weak in melee (wizards, artillery, shooters)
            fragile = (
                ally.is_war_machine
                or expected_damage(ally.melee, ally.models_alive, "4+") < 3.0
            )
            if not fragile:
                continue
            chargers = [
                e for e in self.enemies_of(ally)
                if e.melee and ally.distance(e) <= COMBAT_RANGE
            ]
            if not chargers:
                continue
            charger = max(
                chargers,
                key=lambda e: expected_damage(e.melee, e.models_alive, ally.save),
            )
            interceptors = [
                u for u in self.side_units(side)
                if u is not ally and (u.is_monster or u.is_hero) and u.melee
                and not self._in_combat(u)
                and COMBAT_RANGE < u.distance(charger) <= 12.0 + COMBAT_RANGE
                # only intercept when the hit actually hurts: meaningful
                # absolute damage, or a real dent in the charger's health
                and expected_damage(u.melee, u.models_alive, charger.save)
                >= min(2.0, charger.total_health * 0.25)
            ]
            if not interceptors:
                continue
            u = max(
                interceptors,
                key=lambda x: expected_damage(x.melee, x.models_alive, charger.save),
            )
            if not self.use_command(side, "Counter-charge", u, cost=2):
                return
            roll = self.rng.randint(1, 6) + self.rng.randint(1, 6)
            dist = u.distance(charger)
            self.emit_command(
                side, "Counter-charge", u, "CHARGE",
                f"counter-charges {charger.name} to protect {ally.name} (2D6={roll})",
                roll=roll,
            )
            if roll >= dist - COMBAT_RANGE + 0.5:
                travel = dist - 1.0
                nx = u.x + (charger.x - u.x) / dist * travel
                ny = u.y + (charger.y - u.y) / dist * travel
                self.emit(
                    type="charge", category="CHARGE", uid=u.uid,
                    target=charger.uid, roll=roll, silent=True,
                    frm=[round(u.x, 2), round(u.y, 2)],
                    to=[round(nx, 2), round(ny, 2)],
                )
                u.x, u.y = nx, ny
            else:
                self.emit(
                    type="charge_failed", category="CHARGE", uid=u.uid, roll=roll,
                    text=f"{u.name}'s counter-charge falls short (rolled {roll})",
                )
            return  # one Counter-charge per reaction window

    # -- phases --------------------------------------------------------
    def hero_phase(self, side: str):
        """Hero phase: start-of-turn abilities, Rally and casting."""
        self.phase_marker(side, "hero")
        apply_turn_mortal_wounds(self, side)
        self._rally(side)
        self.magic_actions(side)

    def _rally(self, side: str):
        """Rally (1 CP): a unit not in combat rolls 6 dice (+1 with a
        MUSICIAN), each 4+ is a rally point. Points heal 1 damage each,
        or revive a slain model for points equal to its Health."""
        wounded = [
            u for u in self.side_units(side)
            if u.wounds_taken > 0 and not self._in_combat(u)
        ]
        if not wounded or self.cp[side] <= 0:
            return
        target = max(wounded, key=lambda u: u.wounds_taken)
        if not self.use_command(side, "Rally", target):
            return
        dice = 6 + (1 if target.has_musician else 0)
        rally_points = sum(1 for _ in range(dice) if self.rng.randint(1, 6) >= 4)
        # slain models cost their Health in rally points to return
        models_lost = target.models - target.models_alive
        revived = 0
        while (
            models_lost - revived > 0
            and target.health_per_model > 0
            and rally_points >= target.health_per_model
        ):
            rally_points -= target.health_per_model
            revived += 1
        revived_damage = revived * target.health_per_model
        healed = min(target.wounds_taken - revived_damage, rally_points)
        total_restored = revived_damage + healed
        target.wounds_taken -= total_restored
        detail = f"rolled {dice} dice"
        if target.has_musician:
            detail += " (incl. MUSICIAN bonus die)"
        if revived:
            detail += f", revives {revived} slain model(s)"
        if healed:
            detail += f", heals {healed} damage"
        if not revived and not healed:
            detail += ", no effect"
        self.emit_command(
            side, "Rally", target, "HERO", detail,
            healed=total_restored, revived=revived,
        )

    def magic_actions(self, side: str):
        """Casting in the hero phase. Each WIZARD (X) unit has X actions
        this phase — the active side spends them casting, the defending
        side spends them unbinding. Generic spell: Arcane Bolt (casting
        value 5, range 12", D3 mortal damage).

        Core-rule constraints implemented here:
        - miscast: a casting roll containing two or more 1s fails
          immediately, deals D3 mortal damage to the caster and locks
          them out of casting for the rest of the phase
        - only ONE unbind attempt may be made per spell, army-wide
        """
        casters = [u for u in self.side_units(side) if u.wizard_level > 0]
        if not casters:
            return
        # per-phase action budget for every wizard on the board
        budget = {u.uid: u.wizard_level for u in self.units if u.wizard_level > 0}
        CV = 5  # Arcane Bolt casting value

        for caster in casters:
            while caster.alive and budget.get(caster.uid, 0) > 0:
                targets = [
                    e for e in self.enemies_of(caster)
                    if caster.distance(e) <= 12.0
                ]
                if not targets:
                    break
                target = min(targets, key=caster.distance)
                budget[caster.uid] -= 1
                d1, d2 = self.rng.randint(1, 6), self.rng.randint(1, 6)
                total = d1 + d2

                if (d1 == 1) + (d2 == 1) >= 2:
                    # miscast: instant fail, D3 mortal, no more casting
                    penalty = self.rng.randint(1, 3)
                    dmg, warded = ward_roll(penalty, caster.ward, self.rng)
                    if warded:
                        self.emit_defense(caster, caster.ward, warded, dmg)
                    caster.wounds_taken += dmg
                    slain = not caster.alive
                    self.emit(
                        type="miscast", category="MAGIC", uid=caster.uid,
                        dice=[d1, d2], damage=dmg, slain=slain,
                        text=f"MISCAST! {caster.name} rolls a double 1 — "
                        f"suffers {dmg} mortal damage and cannot cast again "
                        f"this phase"
                        + (f" — {caster.name} is destroyed!" if slain else ""),
                    )
                    break  # locked out for the rest of the phase

                if total < CV:
                    self.emit(
                        type="cast", category="MAGIC", uid=caster.uid,
                        target=target.uid, roll=total, needed=CV, success=False,
                        text=f"{caster.name} fails to cast Arcane Bolt "
                        f"(rolled {total}, needs {CV}+)",
                    )
                    continue

                # unbind window: at most ONE attempt per spell, army-wide
                unbinders = [
                    e for e in self.enemies_of(caster)
                    if e.wizard_level > 0 and budget.get(e.uid, 0) > 0
                    and caster.distance(e) <= 30.0
                ]
                unbound = False
                if unbinders:
                    ub = min(unbinders, key=caster.distance)
                    budget[ub.uid] -= 1
                    ub_roll = self.rng.randint(1, 6) + self.rng.randint(1, 6)
                    unbound = ub_roll > total
                    self.emit(
                        type="unbind", category="MAGIC", uid=ub.uid,
                        target=caster.uid, roll=ub_roll, against=total,
                        success=unbound,
                        text=f"{ub.name} attempts to unbind "
                        f"({ub_roll} vs {total}) — "
                        + ("the spell is unbound!" if unbound else "and fails"),
                    )
                self.emit(
                    type="cast", category="MAGIC", uid=caster.uid,
                    target=target.uid, roll=total, needed=CV,
                    success=not unbound,
                    text=f"{caster.name} casts Arcane Bolt at {target.name} "
                    f"(rolled {total})" + (" — unbound" if unbound else ""),
                )
                if unbound:
                    continue
                # D3 mortal damage joins the damage pool, then Ward rolls
                pool = self.rng.randint(1, 3)
                ward = effective_ward(target, collect_mods(target, self.units, None))
                dmg, warded = ward_roll(pool, ward, self.rng)
                self.apply_damage(caster, target, dmg, "blasts", "spell",
                                  warded=warded, ward=ward)

    def end_phase(self, side: str):
        """End phase: AoS4 has no battleshock — expiring effects resolve
        here; for now we report the side's remaining command points."""
        self.phase_marker(side, "end")
        self.emit(
            type="cp_status", category="PHASE", side=side, cp=self.cp[side],
            text=f"{side} ends the turn with {self.cp[side]} CP remaining",
        )

    def movement_phase(self, side: str):
        self.phase_marker(side, "movement")
        self._movement_actions(side)
        # reaction hook: the inactive player may Redeploy
        self.reaction_redeploy(self._other(side))

    def _retreat(self, u: SimUnit, threat: SimUnit):
        """Retreat: leave combat, suffering D3 mortal damage before the
        move (core rules). Ward saves apply to the mortal damage."""
        penalty = self.rng.randint(1, 3)
        dmg, warded = ward_roll(penalty, u.ward, self.rng)
        if warded:
            self.emit_defense(u, u.ward, warded, dmg)
        u.wounds_taken += dmg
        dist = u.distance(threat) or 0.1
        step = max(0.0, u.move)
        nx = min(max(u.x + (u.x - threat.x) / dist * step, 0.5), BOARD_W - 0.5)
        ny = min(max(u.y + (u.y - threat.y) / dist * step, 0.5), BOARD_H - 0.5)
        slain = not u.alive
        self.emit(
            type="retreat", category="MOVE", uid=u.uid, target=threat.uid,
            damage=dmg, dist=round(step, 1),
            frm=[round(u.x, 2), round(u.y, 2)], to=[round(nx, 2), round(ny, 2)],
            text=f"{u.name} retreats from combat, suffering {dmg} mortal damage"
            + (f" — {u.name} is destroyed!" if slain else ""),
            slain=slain,
        )
        if u.alive:
            u.x, u.y = nx, ny

    def _movement_actions(self, side: str):
        for u in self.side_units(side):
            enemies = self.enemies_of(u)
            if not enemies:
                return
            target = min(enemies, key=u.distance)
            dist = u.distance(target)
            if dist <= COMBAT_RANGE:
                # in combat: shooters retreat (paying D3 mortal damage),
                # melee units hold their ground
                shooter = u.ranged and expected_damage(
                    u.ranged, u.models_alive, "4+"
                ) > expected_damage(u.melee, u.models_alive, "4+")
                if shooter:
                    self._retreat(u, target)
                continue
            move_mods, move_details = collect_mods_detailed(u, self.units, "movement")
            move_mod = move_mods.get("move", 0)
            if move_mod:
                self.emit_effects(u, [d for d in move_details if d["stat"] == "move"], "mover")
            eff_move = max(0.0, u.move + move_mod)
            # core rules: normal moves cannot enter combat range — stop
            # just outside (3.5") and let the charge phase close the gap
            step = min(eff_move, max(dist - (COMBAT_RANGE + 0.5), 0))
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
                type="move", category="MOVE", uid=u.uid, target=target.uid,
                dist=round(step, 1),
                frm=[round(u.x, 2), round(u.y, 2)],
                to=[round(nx, 2), round(ny, 2)],
                text=f"{u.name} moves {step:.1f}\" toward {target.name}",
            )
            u.x, u.y = nx, ny

    def shooting_phase(self, side: str):
        self.phase_marker(side, "shooting")
        self._shooting_actions(side)
        # reaction hook: the inactive player may use Covering Fire
        self.reaction_covering_fire(self._other(side))

    def _shooting_actions(self, side: str):
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
            atk_mods, atk_details = collect_mods_detailed(u, self.units, "shooting")
            def_mods, def_details = collect_mods_detailed(target, self.units, "shooting")
            self.emit_effects(u, atk_details, "attacker")
            self.emit_effects(target, def_details, "defender")
            self.try_all_out_attack(side, u, atk_mods, "SHOOT")
            self.try_all_out_defence(target, def_mods, "SHOOT")
            ward = effective_ward(target, def_mods)
            dmg, warded = unit_attack(weapons, u.models_alive, target.save, self.rng,
                                      ward, atk_mods, def_mods)
            self.apply_damage(u, target, dmg, "shoots", "shoot",
                              warded=warded, ward=ward, applied_details=atk_details)

    def charge_phase(self, side: str):
        self.phase_marker(side, "charge")
        self._charge_actions(side)
        # reaction hook: the inactive player may Counter-charge
        self.reaction_counter_charge(self._other(side))

    def _charge_actions(self, side: str):
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
                    type="charge", category="CHARGE", uid=u.uid, target=target.uid, roll=charge_roll,
                    frm=[round(u.x, 2), round(u.y, 2)], to=[round(nx, 2), round(ny, 2)],
                    text=f"{u.name} charges {target.name} (rolled {charge_roll})",
                )
                u.x, u.y = nx, ny
            else:
                self.emit(
                    type="charge_failed", category="CHARGE", uid=u.uid, roll=charge_roll,
                    text=f"{u.name} fails its charge (rolled {charge_roll})",
                )
                # Forward to Victory (1 CP): re-roll the failed charge
                if self.use_command(side, "Forward to Victory", u):
                    reroll = self.rng.randint(1, 6) + self.rng.randint(1, 6)
                    self.emit_command(side, "Forward to Victory", u, "CHARGE",
                                      f"re-rolls the charge ({reroll})")
                    if reroll >= dist - COMBAT_RANGE + 0.5:
                        travel = dist - 1.0
                        nx = u.x + (target.x - u.x) / dist * travel
                        ny = u.y + (target.y - u.y) / dist * travel
                        self.emit(
                            type="charge", category="CHARGE", uid=u.uid,
                            target=target.uid, roll=reroll,
                            frm=[round(u.x, 2), round(u.y, 2)],
                            to=[round(nx, 2), round(ny, 2)],
                            text=f"{u.name} charges {target.name} on the re-roll! ({reroll})",
                        )
                        u.x, u.y = nx, ny

    def combat_phase(self, side: str):
        self.phase_marker(side, "combat")
        # both sides fight; STRIKE-FIRST units go first and STRIKE-LAST
        # last (a unit with both keywords cancels out to normal order),
        # with the active player's units leading inside each bracket
        def strike_bracket(u: SimUnit) -> int:
            first, last = u.strike_first, u.strike_last
            if first and last:
                return 1  # keywords cancel out
            if first:
                return 0
            if last:
                return 2
            return 1

        base = self.side_units(side) + self.side_units(self._other(side))
        order = sorted(base, key=strike_bracket)
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
            atk_mods, atk_details = collect_mods_detailed(u, self.units, "combat")
            def_mods, def_details = collect_mods_detailed(target, self.units, "combat")
            self.emit_effects(u, atk_details, "attacker")
            self.emit_effects(target, def_details, "defender")
            self.try_all_out_attack(u.side, u, atk_mods, "COMBAT")
            self.try_all_out_defence(target, def_mods, "COMBAT")
            ward = effective_ward(target, def_mods)
            dmg, warded = unit_attack(u.melee, u.models_alive, target.save, self.rng,
                                      ward, atk_mods, def_mods)
            self.apply_damage(u, target, dmg, "hits", "melee",
                              warded=warded, ward=ward, applied_details=atk_details)

    def emit_effects(self, unit: SimUnit, details: list, role: str):
        """Logs which abilities are affecting ``unit`` and who cast them.
        Repeats are suppressed until the unit's effect set changes."""
        if not details:
            return
        key = tuple(sorted(
            (d["source_uid"], d["ability"], d["stat"], d["amount"], d["mode"])
            for d in details
        ))
        if self._last_effects.get(unit.uid) == key:
            return
        self._last_effects[unit.uid] = key
        summary = "; ".join(describe_effect(d) for d in details)
        self.emit(
            type="effects", category="EFFECT", uid=unit.uid, role=role, effects=details,
            text=f"{unit.name} is affected by: {summary}",
        )

    @staticmethod
    def _attack_effect_brief(details: list) -> tuple[list, str]:
        """Filters effect details down to the stats that influence an
        attack roll and renders a short suffix for the log line, e.g.
        "(applied: 'Aether-gold' hit+1)". Roll-stat signs are flipped
        for display: an internal -1 on the target number is shown +1."""
        relevant = [d for d in details if d["stat"] in ("hit", "wound", "rend", "damage")]
        if not relevant:
            return [], ""
        parts = []
        for d in relevant:
            shown = -d["amount"] if d["stat"] in ("hit", "wound") else d["amount"]
            parts.append(f"'{d['ability']}' {d['stat']}{shown:+d}")
        return relevant, f" (applied: {', '.join(parts)})"

    def emit_defense(self, target: SimUnit, ward: str, warded: int, final: int):
        """Explicit log when a Ward save negates damage."""
        self.emit(
            type="defense", category="DEFENSE", uid=target.uid,
            ward=ward, negated=warded, final_damage=final,
            text=f"{target.name} negates {warded} damage with its "
            f"'Ward {ward}' save! (final damage: {final})",
        )

    def apply_damage(
        self, attacker: SimUnit, target: SimUnit, dmg: int, verb: str, kind: str,
        warded: int = 0, ward: str = "", applied_details: list | None = None,
    ):
        category = {
            "shoot": "SHOOT", "melee": "COMBAT", "mortal": "HERO",
            "spell": "MAGIC",
        }.get(kind, "COMBAT")
        applied, suffix = self._attack_effect_brief(applied_details or [])
        if warded > 0:
            self.emit_defense(target, ward, warded, dmg)
        if dmg <= 0:
            self.emit(
                type="attack", category=category, kind=kind,
                uid=attacker.uid, target=target.uid, damage=0, applied=applied,
                text=f"{attacker.name} {verb} {target.name} but deals no damage{suffix}",
            )
            return
        target.wounds_taken += dmg
        slain = not target.alive
        self.emit(
            type="attack", category=category, kind=kind,
            uid=attacker.uid, target=target.uid, damage=dmg, applied=applied,
            slain=slain,
            text=f"{attacker.name} {verb} {target.name} for {dmg} damage{suffix}"
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
            self.cp = {"player": 4, "enemy": 4}  # AoS4: 4 CP per round
            # the underdog (fewer surviving points) gains 1 extra CP
            p_pts = sum(u.points for u in self.side_units("player"))
            e_pts = sum(u.points for u in self.side_units("enemy"))
            underdog = ""
            if p_pts != e_pts:
                underdog = "player" if p_pts < e_pts else "enemy"
                self.cp[underdog] += 1
            self.emit(type="round", category="PHASE", round_no=rnd, first=first,
                      underdog=underdog,
                      text=f"Battle round {rnd} begins — {first} goes first "
                      f"(both sides gain 4 CP"
                      + (f"; underdog {underdog} gains 1 extra CP)" if underdog else ")"))
            for side in (first, second):
                if not self.side_units("player") or not self.side_units("enemy"):
                    break
                self.emit(type="turn", category="PHASE", side=side)
                self.hero_phase(side)
                self.movement_phase(side)
                self.shooting_phase(side)
                self.charge_phase(side)
                self.combat_phase(side)
                self.end_phase(side)
                self.emit(type="state", units=self.snapshot())
            lost = {s: self.cp[s] for s in ("player", "enemy")}
            self.cp = {"player": 0, "enemy": 0}  # unspent CP is lost
            self.emit(
                type="cp_reset", category="PHASE", round_no=rnd,
                text=f"Battle round {rnd} ends — unspent CP discarded "
                f"(player {lost['player']}, enemy {lost['enemy']})",
            )
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

"""Applies structured ability parameters (buffs/debuffs) in battle.

Reads the machine-readable ``structured`` data attached to warscroll
abilities by services.ability_parser and turns it into stat modifiers
and mortal wounds during the simulation.

V1 scope (deterministic, no player decisions):
- Only unconditional modifiers (``condition`` is null) are applied —
  free-text conditions can't be evaluated reliably yet.
- ``passive``/``any_phase`` modifiers apply continuously; ``active``
  abilities are assumed to be used every time their phase comes up.
- Roll modifiers (hit/wound/save) are capped at ±1 per the AoS4 core
  rules; rend/damage/move stack uncapped.
- ``inflict mortal_wound`` abilities trigger once per turn at the start
  of the owner's turn (hero-phase style abilities).
"""

from __future__ import annotations

import random

from .combat import roll_value, target_number

AURA_RANGE = {
    "friendly_within_12": 12.0,
    "enemy_within_12": 12.0,
    "enemy_in_combat": 3.0,
}

# stats whose roll modifiers are capped at +/-1 by the core rules
ROLL_STATS = {"hit", "wound", "save"}

PHASE_TIMING = {
    "movement": "movement_phase",
    "shooting": "shooting_phase",
    "charge": "charge_phase",
    "combat": "combat_phase",
}


def _structured_abilities(unit) -> list[dict]:
    return [
        a["structured"]
        for a in getattr(unit, "abilities_raw", [])
        if isinstance(a, dict) and a.get("structured")
    ]


def _timing_applies(ability: dict, phase: str | None) -> bool:
    timing = ability.get("timing", "any_phase")
    if ability.get("activation_type") == "passive" or timing == "any_phase":
        return True
    if phase is None:
        return False
    return timing == PHASE_TIMING.get(phase)


def collect_mods(unit, all_units, phase: str | None) -> dict[str, int]:
    """Effective stat deltas for ``unit`` in the given phase.

    Aggregates self buffs, friendly auras and enemy debuffs from every
    unconditional structured modifier on the board, then caps roll
    modifiers at +/-1. Sign convention follows the schema: for roll
    stats 'subtract' improves the roll (4+ -> 3+), so the returned
    delta is added to the target number.
    """
    totals: dict[str, float] = {}

    for src in all_units:
        if not src.alive:
            continue
        friendly = src.side == unit.side
        for ability in _structured_abilities(src):
            if not _timing_applies(ability, phase):
                continue
            for mod in ability.get("modifiers", []):
                if mod.get("condition"):
                    continue  # free-text conditions not evaluable yet
                if mod.get("modifier_type") == "inflict":
                    continue  # handled by apply_turn_mortal_wounds
                stat = mod.get("stat")
                tt = mod.get("target_type", "self")
                if tt == "self":
                    if src is not unit:
                        continue
                elif tt == "friendly_within_12":
                    if not friendly or src.distance(unit) > AURA_RANGE[tt]:
                        continue
                elif tt in ("enemy_within_12", "enemy_in_combat"):
                    if friendly or src.distance(unit) > AURA_RANGE[tt]:
                        continue
                else:
                    continue
                value = roll_value(mod.get("value", "1"), random.Random(0)) or 1
                if mod.get("modifier_type") == "set":
                    # 'set' applies absolute values (e.g. gain WARD 5+)
                    tn = target_number(mod.get("value", "")) or value
                    totals[f"set_{stat}"] = tn
                    continue
                sign = -1 if mod.get("modifier_type") == "subtract" else 1
                totals[stat] = totals.get(stat, 0) + sign * value

    out: dict[str, int] = {}
    for stat, v in totals.items():
        v = int(v)
        if stat in ROLL_STATS:
            v = max(-1, min(1, v))  # core rules: roll modifiers cap at +/-1
        out[stat] = v
    return out


def effective_ward(unit, mods: dict[str, int]) -> str:
    """Best ward save after 'set ward' effects (lower target is better)."""
    own = target_number(unit.ward)
    granted = mods.get("set_ward")
    candidates = [t for t in (own, granted) if t]
    return f"{min(candidates)}+" if candidates else ""


def apply_turn_mortal_wounds(sim, side: str) -> None:
    """Start-of-turn mortal wounds from unconditional 'inflict' abilities."""
    for u in sim.side_units(side):
        for ability in _structured_abilities(u):
            if ability.get("timing") not in ("hero_phase", "any_phase"):
                continue
            for mod in ability.get("modifiers", []):
                if (
                    mod.get("modifier_type") != "inflict"
                    or mod.get("stat") != "mortal_wound"
                    or mod.get("condition")
                ):
                    continue
                tt = mod.get("target_type", "")
                rng_in = AURA_RANGE.get(tt)
                if tt not in ("enemy_within_12", "enemy_in_combat") or rng_in is None:
                    continue
                targets = [e for e in sim.enemies_of(u) if u.distance(e) <= rng_in]
                if not targets:
                    continue
                target = min(targets, key=u.distance)
                dmg = roll_value(mod.get("value", "1"), sim.rng) or 1
                target.wounds_taken += dmg
                slain = not target.alive
                sim.emit(
                    type="attack", kind="mortal", uid=u.uid, target=target.uid,
                    damage=dmg, slain=slain, ability=ability.get("name", ""),
                    text=f"{u.name} inflicts {dmg} mortal wound(s) on {target.name}"
                    f" [{ability.get('name', '')}]"
                    + (f" — {target.name} is destroyed!" if slain else ""),
                )

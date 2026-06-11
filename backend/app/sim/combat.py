"""Dice and attack-sequence math based on the AoS4 core rules.

The attack sequence per the core rules: for each attack roll to Hit,
then to Wound, then the defender makes a Save roll modified by Rend;
unsaved attacks inflict Damage. Stats parsed from Wahapedia are display
strings ("3+", "D6", "2D6+1", "-") and are resolved here, either by
actual dice rolls (Monte Carlo, used by the simulator) or as expected
values (used by the AI to pick targets).
"""

from __future__ import annotations

import random
import re


def roll_value(stat: str, rng: random.Random) -> int:
    """Resolve a stat like '2', 'D6', '2D3+1' to a rolled value."""
    s = (stat or "").strip().upper().replace(" ", "")
    if not s or s in {"-", "—"}:
        return 0
    m = re.fullmatch(r"(?:(\d*)D(\d+))?([+-]\d+)?(\d+)?", s)
    if not m:
        return 0
    count, die, mod, flat = m.groups()
    total = 0
    if die:
        n = int(count) if count else 1
        total += sum(rng.randint(1, int(die)) for _ in range(n))
    if flat and not die:
        total += int(flat)
    if mod:
        total += int(mod)
    return max(total, 0)


def expected_value(stat: str) -> float:
    """Expected value of a stat expression, for AI heuristics."""
    s = (stat or "").strip().upper().replace(" ", "")
    if not s or s in {"-", "—"}:
        return 0.0
    m = re.fullmatch(r"(?:(\d*)D(\d+))?([+-]\d+)?(\d+)?", s)
    if not m:
        return 0.0
    count, die, mod, flat = m.groups()
    total = 0.0
    if die:
        n = int(count) if count else 1
        total += n * (int(die) + 1) / 2
    if flat and not die:
        total += int(flat)
    if mod:
        total += int(mod)
    return max(total, 0.0)


def target_number(stat: str) -> int | None:
    """'3+' -> 3. Returns None for '-' (auto-fail / no roll)."""
    m = re.match(r"(\d)\+", (stat or "").strip())
    return int(m.group(1)) if m else None


def rend_value(stat: str) -> int:
    m = re.search(r"\d+", stat or "")
    return int(m.group()) if m else 0


def roll_attacks(weapon: dict, models: int, rng: random.Random) -> int:
    """Total damage from one unit's attacks with one weapon profile."""
    hit_t = target_number(weapon["hit"])
    wound_t = target_number(weapon["wound"])
    if hit_t is None or wound_t is None:
        return 0
    total = 0
    attacks = sum(roll_value(weapon["attacks"], rng) for _ in range(models))
    crit_two_hits = any("2 Hits" in a for a in weapon.get("abilities", []))
    for _ in range(attacks):
        roll = rng.randint(1, 6)
        if roll < hit_t:
            continue
        hits = 2 if (roll == 6 and crit_two_hits) else 1
        for _ in range(hits):
            if rng.randint(1, 6) >= wound_t:
                total += 1
    return total  # number of wounding hits; saves applied by caller


def resolve_damage(
    wounding_hits: int,
    weapon: dict,
    save_stat: str,
    rng: random.Random,
    ward_stat: str = "",
) -> int:
    """Apply save rolls (modified by Rend), roll damage, then ward rolls."""
    save_t = target_number(save_stat)
    ward_t = target_number(ward_stat)
    rend = rend_value(weapon["rend"])
    damage = 0
    for _ in range(wounding_hits):
        if save_t is not None:
            needed = save_t + rend
            if needed <= 6 and rng.randint(1, 6) >= needed:
                continue  # saved
        for _ in range(roll_value(weapon["damage"], rng) or 1):
            if ward_t is not None and rng.randint(1, 6) >= ward_t:
                continue  # warded
            damage += 1
    return damage


def unit_attack(
    attacker_weapons: list[dict],
    models: int,
    defender_save: str,
    rng: random.Random,
    defender_ward: str = "",
) -> int:
    """Full attack sequence for all of a unit's weapon profiles."""
    total = 0
    for weapon in attacker_weapons:
        wounds = roll_attacks(weapon, models, rng)
        total += resolve_damage(wounds, weapon, defender_save, rng, defender_ward)
    return total


def expected_damage(weapons: list[dict], models: int, defender_save: str) -> float:
    """Expected damage output, used by the AI to rank targets."""
    save_t = target_number(defender_save)
    total = 0.0
    for w in weapons:
        hit_t = target_number(w["hit"])
        wound_t = target_number(w["wound"])
        if hit_t is None or wound_t is None:
            continue
        p_hit = (7 - hit_t) / 6
        p_wound = (7 - wound_t) / 6
        rend = rend_value(w["rend"])
        if save_t is None or save_t + rend > 6:
            p_unsaved = 1.0
        else:
            p_unsaved = (save_t + rend - 1) / 6
        dmg = expected_value(w["damage"]) or 1.0
        total += expected_value(w["attacks"]) * models * p_hit * p_wound * p_unsaved * dmg
    return total
